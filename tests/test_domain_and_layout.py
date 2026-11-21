"""Unit tests for domain models, layout tree operations, and provider presets."""

from __future__ import annotations

import json
import unittest

from kazu.domain.layout import (
    PaneNode,
    SplitNode,
    assign_account_to_pane,
    clear_account_references,
    close_pane,
    default_four_up_layout,
    default_side_by_side_layout,
    deserialize_layout,
    iter_panes,
    recommended_max_panes,
    serialize_layout,
    split_pane,
    swap_panes,
)
from kazu.domain.models import ACCOUNT_COLOR_KEYS, Account, AppSettings, EngineKind, Orientation
from kazu.domain.providers import ProviderPresetRegistry


class DomainAndLayoutTests(unittest.TestCase):
    def test_account_clamps_zoom_and_defaults_invalid_color(self) -> None:
        acc = Account(
            id="a1",
            label="  Work Claude  ",
            provider_key="CLAUDE",
            home_url="https://claude.ai",
            color="not-a-color",
            zoom=5.0,
        )
        self.assertEqual(acc.label, "Work Claude")
        self.assertEqual(acc.provider_key, "claude")
        self.assertEqual(acc.color, ACCOUNT_COLOR_KEYS[0])
        self.assertEqual(acc.zoom, 2.0)

    def test_settings_enforces_discard_greater_than_freeze(self) -> None:
        s = AppSettings(freeze_after_minutes=20, discard_after_minutes=10)
        self.assertEqual(s.freeze_after_minutes, 20)
        self.assertGreater(s.discard_after_minutes, s.freeze_after_minutes)

    def test_layout_roundtrip_and_corrupted_json_fallback(self) -> None:
        tree = default_four_up_layout(["a1", "a2", "a3", "a4"])
        raw = serialize_layout(tree)
        restored = deserialize_layout(raw)
        self.assertEqual([p.account_id for p in iter_panes(restored)], ["a1", "a2", "a3", "a4"])

        # Corrupted JSON must never crash — returns single empty pane.
        fallback = deserialize_layout("{corrupted json!!!")
        self.assertIsInstance(fallback, PaneNode)
        assert isinstance(fallback, PaneNode)
        self.assertIsNone(fallback.account_id)

    def test_split_swap_close_and_clear_references(self) -> None:
        tree = default_side_by_side_layout("acc_left", "acc_right")
        panes = iter_panes(tree)
        left_id, right_id = panes[0].pane_id, panes[1].pane_id

        self.assertTrue(swap_panes(tree, left_id, right_id))
        self.assertEqual([p.account_id for p in iter_panes(tree)], ["acc_right", "acc_left"])

        updated, new_pane = split_pane(tree, right_id, Orientation.VERTICAL, "acc_bottom")
        self.assertIsNotNone(new_pane)
        self.assertEqual(len(iter_panes(updated)), 3)

        assert new_pane is not None
        self.assertTrue(assign_account_to_pane(updated, new_pane.pane_id, "acc_extra"))
        self.assertEqual(clear_account_references(updated, "acc_extra"), 1)

        pruned, removed = close_pane(updated, new_pane.pane_id)
        self.assertTrue(removed)
        self.assertEqual(len(iter_panes(pruned)), 2)
        self.assertIsInstance(pruned, SplitNode)

    def test_recommended_max_panes_breakpoints(self) -> None:
        self.assertEqual(recommended_max_panes(1024), 2)
        self.assertEqual(recommended_max_panes(1440), 3)
        self.assertEqual(recommended_max_panes(2560), 4)

    def test_provider_presets_default_gemini_to_companion_and_merge_remote(self) -> None:
        registry = ProviderPresetRegistry()
        self.assertEqual(registry.get("gemini").pane_type, EngineKind.COMPANION)
        self.assertEqual(registry.get("claude").pane_type, EngineKind.EMBEDDED)

        remote_payload = json.dumps(
            {
                "providers": {
                    "claude": {
                        "name": "Claude",
                        "url": "https://claude.ai",
                        "pane_type": "embedded",
                        "target_css_width": 980,
                    },
                    "invalid": {"name": "Bad", "url": "javascript:alert(1)"},
                }
            }
        )
        updated_count = registry.apply_verified_json(remote_payload)
        self.assertEqual(updated_count, 1)
        self.assertEqual(registry.get("claude").target_css_width, 980)
        self.assertNotIn("invalid", registry.presets)


if __name__ == "__main__":
    unittest.main()
