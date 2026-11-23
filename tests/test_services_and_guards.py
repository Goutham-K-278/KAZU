"""Unit tests for lifecycle, navigation, autofit, clipboard send, shortcuts, and infra guards."""

from __future__ import annotations

import logging
import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

from kazu.controllers.autofit import AutoFitZoomService
from kazu.controllers.lifecycle import LifecycleTier, TieredLifecycleService
from kazu.controllers.navigation import (
    BlockDetector,
    DownloadService,
    NavigationAction,
    NavigationPolicy,
    extract_registrable_domain,
    is_oauth_url,
)
from kazu.controllers.send import SendService
from kazu.controllers.shortcuts import ShortcutRegistry
from kazu.domain.models import ZoomMode
from kazu.domain.providers import ProviderPresetRegistry
from kazu.infra.geometry import (
    FrameMargins,
    Rect,
    clamp_window_rect,
    compute_initial_window_rect,
)
from kazu.infra.logging_setup import PrivacyRedactingFilter
from kazu.infra.memory import MemoryMonitor
from kazu.infra.paths import AppPaths, validate_account_id
from kazu.infra.shutdown import ShutdownCoordinator
from kazu.infra.snapshots import SnapshotCache
from kazu.infra.updater import build_broken_site_report, is_engine_stale
from kazu.ui.theme.tokens import DARK_TOKENS, build_qss


class _FakeClipboard:
    def __init__(self, initial: str) -> None:
        self.text = initial

    def get_text(self) -> str:
        return self.text

    def set_text(self, text: str) -> None:
        self.text = text


class _FakePaneTarget:
    def __init__(self, pane_id: str, can_focus: bool) -> None:
        self.pane_id = pane_id
        self._can_focus = can_focus
        self.pasted_count = 0

    def focus_input(self) -> bool:
        return self._can_focus

    def trigger_paste(self) -> None:
        self.pasted_count += 1


class ServicesAndGuardsTests(unittest.TestCase):
    def test_tiered_lifecycle_with_activity_guard_pin_and_live_threshold_update(self) -> None:
        svc = TieredLifecycleService(freeze_after_seconds=600, discard_after_seconds=1800)
        svc.register_pane("p1", "s1", visible=True, now=0.0)
        svc.register_pane("p2", "s1", visible=True, keep_running=True, now=0.0)
        svc.register_pane("p3", "s2", visible=False, now=0.0)

        svc.activate_space("s2", now=100.0)
        self.assertEqual(svc.get_record("p1").tier, LifecycleTier.HIDDEN_ACTIVE)  # type: ignore[union-attr]

        self.assertTrue(svc.record_activity("p1", now=500.0))
        self.assertTrue(svc.space_has_unread_activity("s1"))
        self.assertEqual(svc.evaluate_transitions(now=900.0), {})

        svc.update_thresholds(freeze_after_seconds=300, discard_after_seconds=1800)
        self.assertEqual(svc.evaluate_transitions(now=900.0), {"p1": LifecycleTier.FROZEN})
        self.assertEqual(svc.get_record("p2").tier, LifecycleTier.HIDDEN_ACTIVE)  # type: ignore[union-attr]

        self.assertEqual(svc.evaluate_transitions(now=2400.0), {"p1": LifecycleTier.DISCARDED})

        waking = svc.activate_space("s1", now=2500.0)
        self.assertEqual(waking, ["p1"])
        self.assertFalse(svc.space_has_unread_activity("s1"))

    def test_navigation_policy_oauth_redirects_custom_subdomains_and_google_400(self) -> None:
        presets = ProviderPresetRegistry()
        claude = presets.get("claude")
        custom = presets.get("custom")
        policy = NavigationPolicy()

        self.assertEqual(
            policy.decide("https://claude.ai/chat/123", claude, claude.url),
            NavigationAction.ALLOW_IN_PANE,
        )
        self.assertEqual(
            policy.decide("https://github.com/openai", claude, claude.url),
            NavigationAction.OPEN_EXTERNAL,
        )
        self.assertEqual(
            policy.decide("https://claude.ai/chat/123", claude, claude.url, ctrl_clicked=True),
            NavigationAction.OPEN_EXTERNAL,
        )
        self.assertEqual(
            policy.decide("file:///etc/passwd", claude, claude.url),
            NavigationAction.BLOCK_UNSAFE,
        )
        self.assertEqual(
            policy.decide("about:blank", custom, "https://app.pomaroo.ai"),
            NavigationAction.ALLOW_IN_PANE,
        )
        self.assertEqual(extract_registrable_domain("app.pomaroo.ai"), "pomaroo.ai")
        self.assertEqual(extract_registrable_domain("app.service.co.uk"), "service.co.uk")
        self.assertEqual(extract_registrable_domain("localhost"), "localhost")
        self.assertEqual(
            policy.decide("https://auth.pomaroo.ai/callback", custom, "https://app.pomaroo.ai"),
            NavigationAction.ALLOW_IN_PANE,
        )
        self.assertTrue(is_oauth_url("https://xyz.supabase.co/auth/v1/authorize"))
        self.assertEqual(
            policy.decide(
                "https://sso.some-custom-broker.io/authorize",
                custom,
                "https://app.pomaroo.ai",
                is_user_link_click=False,
            ),
            NavigationAction.ALLOW_IN_PANE,
        )

        detector = BlockDetector()
        self.assertTrue(
            detector.is_google_blocked(
                "https://accounts.google.com/o/oauth2?error=disallowed_useragent"
            )
        )
        self.assertTrue(
            detector.is_google_blocked(
                "https://accounts.google.com/signin/oauth/v2/consent?authuser=0",
                "Error 400 (Bad Request)!!1",
            )
        )
        self.assertTrue(detector.is_signed_out_url("https://claude.ai/login", claude))

        with tempfile.TemporaryDirectory() as tmp:
            dl = DownloadService()
            first = dl.resolve_unique_path(Path(tmp), "report.pdf")
            first.write_bytes(b"pdf1")
            second = dl.resolve_unique_path(Path(tmp), "report.pdf")
            self.assertEqual(second.name, "report (1).pdf")

    def test_autofit_zoom_clamping_and_suggestion(self) -> None:
        svc = AutoFitZoomService()
        wide = svc.compute(1200, 950, ZoomMode.FIT_DESKTOP)
        self.assertEqual(wide.zoom, 1.0)
        self.assertFalse(wide.suggest_new_space)

        narrow = svc.compute(500, 950, ZoomMode.FIT_DESKTOP)
        self.assertEqual(narrow.zoom, 0.67)
        self.assertTrue(narrow.suggest_new_space)

        native = svc.compute(500, 950, ZoomMode.NATIVE_NARROW, manual_zoom=1.1)
        self.assertEqual(native.zoom, 1.1)
        self.assertFalse(native.suggest_new_space)

    def test_clipboard_safe_send_service_restores_clipboard(self) -> None:
        cb = _FakeClipboard("my important code snippet")
        send = SendService(cb)
        t1 = _FakePaneTarget("p1", can_focus=True)
        t2 = _FakePaneTarget("p2", can_focus=False)

        result = send.send_text("hello\u2029world", [t1, t2])
        self.assertEqual(result.pasted_pane_ids, ("p1",))
        self.assertEqual(result.needs_manual_click_pane_ids, ("p2",))
        self.assertEqual(t1.pasted_count, 1)
        self.assertEqual(t2.pasted_count, 0)
        self.assertEqual(cb.text, "my important code snippet")

    def test_shortcuts_pass_through_and_provider_conflicts(self) -> None:
        reg = ShortcutRegistry.default()
        self.assertTrue(reg.should_intercept("command_palette"))
        self.assertFalse(
            reg.should_intercept("command_palette", active_provider_quirks=("uses_ctrl_k",))
        )
        reg.pass_through_mode = True
        self.assertFalse(reg.should_intercept("new_space"))

    def test_window_geometry_guard_respects_frame_margins_and_hidpi_laptop(self) -> None:
        # 1920x1080 @ 150% Windows DPI scaling -> 1280x680 availableGeometry
        hidpi_laptop = Rect(0, 0, 1280, 680)
        margins = FrameMargins(left=8, top=36, right=8, bottom=8)

        initial = compute_initial_window_rect(hidpi_laptop, margins=margins)
        self.assertGreaterEqual(initial.x - margins.left, hidpi_laptop.x)
        self.assertGreaterEqual(initial.y - margins.top, hidpi_laptop.y)
        self.assertLessEqual(initial.right + margins.right, hidpi_laptop.right)
        self.assertLessEqual(initial.bottom + margins.bottom, hidpi_laptop.bottom)

        # Oversized window (1360x860) clamped strictly inside screen including title bar
        oversized = Rect(0, 0, 1360, 860)
        clamped = clamp_window_rect(oversized, [hidpi_laptop], margins=margins)
        self.assertLessEqual(clamped.bottom + margins.bottom, hidpi_laptop.bottom)
        self.assertGreaterEqual(clamped.y - margins.top, hidpi_laptop.y)

        # Ghost window on unplugged monitor recovers to primary screen
        primary = Rect(0, 0, 1920, 1080)
        ghost = Rect(2400, 100, 1200, 800)
        recovered = clamp_window_rect(ghost, [primary], margins=margins)
        self.assertGreaterEqual(recovered.x - margins.left, 0)
        self.assertLessEqual(recovered.right + margins.right, 1920)
        self.assertLessEqual(recovered.bottom + margins.bottom, 1080)

    def test_qss_cache_and_snapshot_shutdown_order(self) -> None:
        self.assertIs(build_qss(DARK_TOKENS), build_qss(DARK_TOKENS))

        cache = SnapshotCache(max_entries=2)
        self.assertTrue(cache.put("p1", b"png1"))
        self.assertTrue(cache.put("p2", b"png2"))
        self.assertEqual(cache.get("p1"), b"png1")
        self.assertTrue(cache.put("p3", b"png3"))
        self.assertIsNone(cache.get("p2"))
        self.assertEqual(cache.get("p1"), b"png1")

        order: list[str] = []
        coord = ShutdownCoordinator()
        coord.register_hide_views(lambda: order.append("hide"))
        coord.register_destroy_views_and_pages(lambda: order.append("destroy_views"))
        coord.set_event_processor(lambda: order.append("process_events"))
        coord.register_destroy_profiles(lambda: order.append("destroy_profiles"))
        coord.register_checkpoint_storage(lambda: order.append("checkpoint_db"))
        coord.execute()
        coord.execute()
        self.assertEqual(
            order,
            ["hide", "destroy_views", "process_events", "destroy_profiles", "checkpoint_db"],
        )

    def test_paths_traversal_protection_permissions_and_privacy_filter(self) -> None:
        with self.assertRaises(ValueError):
            validate_account_id("../escape")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = AppPaths(root / "d", root / "c", root / "l")
            storage = paths.profile_storage("acc_123")
            if os.name == "posix":
                self.assertEqual(storage.stat().st_mode & 0o777, 0o700)

        filt = PrivacyRedactingFilter()
        rec = logging.LogRecord(
            name="kazu",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Navigated to https://claude.ai/chat/secret-id",
            args=(),
            exc_info=None,
        )
        filt.filter(rec)
        self.assertNotIn("claude.ai", rec.msg)
        self.assertIn("[redacted-url]", rec.msg)

        sample = MemoryMonitor().sample()
        self.assertGreaterEqual(sample.total_rss_bytes, 0)
        self.assertTrue(is_engine_stale(date(2026, 1, 1), today=date(2026, 6, 1)))
        report = build_broken_site_report("Claude", "6.12.0")
        self.assertEqual(report.provider_key, "claude")


if __name__ == "__main__":
    unittest.main()
