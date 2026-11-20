"""Unit tests for SQLite migrations, AccountController, SpaceController, and app assets."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from kazu.app import resolve_app_icon_path
from kazu.controllers.accounts import AccountController
from kazu.controllers.spaces import SpaceController
from kazu.domain.layout import iter_panes
from kazu.domain.models import EngineKind, ThemeMode
from kazu.domain.providers import ProviderPresetRegistry
from kazu.infra.db import CURRENT_SCHEMA_VERSION, Database
from kazu.infra.paths import AppPaths

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class DatabaseAndControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.paths = AppPaths(
            data_dir=root / "data",
            cache_dir=root / "cache",
            log_dir=root / "logs",
        )
        self.paths.ensure_base_dirs()
        self.db = Database(self.paths.db_path)
        self.presets = ProviderPresetRegistry()
        self.accounts = AccountController(self.db, self.paths, self.presets)
        self.spaces = SpaceController(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self._tmp.cleanup()

    def test_schema_version_and_settings_roundtrip(self) -> None:
        self.assertEqual(self.db.schema_version, CURRENT_SCHEMA_VERSION)
        settings = self.db.load_settings()
        self.assertTrue(settings.confirm_delete_space)
        settings.theme = ThemeMode.DARK
        settings.freeze_after_minutes = 12
        settings.discard_after_minutes = 45
        settings.confirm_delete_space = False
        self.db.save_settings(settings)

        reloaded = self.db.load_settings()
        self.assertEqual(reloaded.theme, ThemeMode.DARK)
        self.assertEqual(reloaded.freeze_after_minutes, 12)
        self.assertEqual(reloaded.discard_after_minutes, 45)
        self.assertFalse(reloaded.confirm_delete_space)

    def test_account_auto_color_switch_engine_and_wipe(self) -> None:
        a1 = self.accounts.create_account("claude")
        a2 = self.accounts.create_account("claude")
        self.assertEqual(a1.label, "Claude")
        self.assertEqual(a2.label, "Claude 2")
        self.assertNotEqual(a1.color, a2.color)

        storage = self.paths.profile_storage(a1.id)
        (storage / "cookies.sqlite").write_text("dummy", encoding="utf-8")
        self.assertTrue((storage / "cookies.sqlite").exists())

        switched = self.accounts.switch_engine(a1.id, EngineKind.COMPANION)
        self.assertIsNotNone(switched)
        assert switched is not None
        self.assertEqual(switched.engine, EngineKind.COMPANION)

        self.assertTrue(self.accounts.delete_and_wipe(a1.id))
        self.assertIsNone(self.accounts.get_account(a1.id))
        self.assertFalse(storage.exists())

    def test_delete_middle_space_preserves_accounts_and_guards_last_space(self) -> None:
        acc = self.accounts.create_account("claude")
        s1 = self.spaces.create_space("Space 1")
        s2 = self.spaces.create_space("Space 2")
        s3 = self.spaces.create_space("Space 3")

        self.assertTrue(self.spaces.delete_space(s2.id))
        remaining = self.spaces.list_spaces()
        self.assertEqual([s.name for s in remaining], ["Space 1", "Space 3"])
        self.assertEqual([s.order_index for s in remaining], [0, 1])
        self.assertIsNotNone(self.accounts.get_account(acc.id))

        # Delete s3 -> only s1 remains; attempting to delete s1 must fail cleanly.
        self.assertTrue(self.spaces.delete_space(s3.id))
        self.assertFalse(self.spaces.delete_space(s1.id))
        self.assertEqual(len(self.spaces.list_spaces()), 1)

    def test_space_undo_close_duplicate_detection_and_sync_folder(self) -> None:
        acc = self.accounts.create_account("chatgpt")
        space = self.spaces.ensure_default_space()
        panes = iter_panes(self.spaces.get_layout(space.id))
        self.assertEqual(len(panes), 2)

        self.spaces.assign_account(space.id, panes[0].pane_id, acc.id)
        open_locs = self.spaces.find_open_account_locations(acc.id)
        self.assertEqual(len(open_locs), 1)
        self.assertEqual(open_locs[0][0].id, space.id)

        snap = self.spaces.close_pane_in_space(space.id, panes[0].pane_id)
        self.assertIsNotNone(snap)
        self.assertEqual(len(iter_panes(self.spaces.get_layout(space.id))), 1)

        restored = self.spaces.undo_last_close()
        self.assertIsNotNone(restored)
        self.assertEqual(len(iter_panes(self.spaces.get_layout(space.id))), 2)

        sync_dir = Path(self._tmp.name) / "sync"
        written = self.spaces.write_sync_folder(sync_dir)
        self.assertTrue(written.exists())
        parsed = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(parsed["v"], 1)
        # Write a second time to verify .bak creation
        self.spaces.write_sync_folder(sync_dir)
        self.assertTrue((sync_dir / "kazu-layouts.json.bak").exists())

    def test_app_logo_and_native_icons_exist(self) -> None:
        runtime_icon = resolve_app_icon_path()
        self.assertIsNotNone(runtime_icon)
        assert runtime_icon is not None
        self.assertGreater(runtime_icon.stat().st_size, 0)

        icons_dir = PROJECT_ROOT / "packaging" / "icons"
        for filename in ("kazu.ico", "kazu.icns", "kazu-256.png", "kazu-512.png"):
            icon_file = icons_dir / filename
            self.assertTrue(icon_file.exists(), f"Missing icon: {filename}")
            self.assertGreater(icon_file.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
