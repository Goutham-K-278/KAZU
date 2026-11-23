"""MainWindow integrating TopBar, SpaceStack, DraftComposer, ToastBanner, and services."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from kazu.controllers.accounts import AccountController
from kazu.controllers.lifecycle import LifecycleTier, TieredLifecycleService
from kazu.controllers.send import SendService
from kazu.controllers.shortcuts import ShortcutRegistry
from kazu.controllers.spaces import SpaceController
from kazu.domain.layout import PaneNode, iter_panes
from kazu.domain.models import AppSettings, EngineKind, Orientation, ThemeMode
from kazu.domain.providers import ProviderPresetRegistry
from kazu.infra.db import Database
from kazu.infra.geometry import ensure_widget_on_screen
from kazu.infra.memory import MemoryMonitor
from kazu.infra.paths import AppPaths
from kazu.infra.shutdown import ShutdownCoordinator
from kazu.infra.snapshots import SnapshotCache
from kazu.ui.account_picker import AccountPicker
from kazu.ui.command_palette import CommandPalette, PaletteCommand
from kazu.ui.draft_composer import DraftComposer
from kazu.ui.engine_companion import BrowserAppEngine
from kazu.ui.focus_guard import FocusGuard
from kazu.ui.onboarding import OnboardingDialog
from kazu.ui.pane_frame import PaneFrame
from kazu.ui.settings_page import SettingsDialog
from kazu.ui.space_stack import SpaceStack
from kazu.ui.theme.tokens import DARK_TOKENS, LIGHT_TOKENS, ThemeTokens, build_qss
from kazu.ui.toast import ToastBanner
from kazu.ui.top_bar import TopBar

LIFECYCLE_POLL_MS: int = 15_000
STAGGER_PANE_MS: int = 150
ZOOM_STEP: float = 0.1
RAM_CHECK_EVERY_N_TICKS: int = 4  # Every 60s


class _QtClipboardAdapter:
    """Thin adapter connecting QApplication.clipboard() to SendService."""

    def get_text(self) -> str:
        cb = QApplication.clipboard()
        return cb.text() if cb is not None else ""

    def set_text(self, text: str) -> None:
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(text)


class MainWindow(QMainWindow):
    """Kazu's calm primary window: slim TopBar + adaptive split panes."""

    def __init__(
        self,
        *,
        db: Database,
        paths: AppPaths,
        settings: AppSettings,
        presets: ProviderPresetRegistry,
        shutdown: ShutdownCoordinator,
    ) -> None:
        super().__init__()
        self._db = db
        self._paths = paths
        self._settings = settings
        self._presets = presets
        self._shutdown = shutdown

        self._accounts = AccountController(db, paths, presets)
        self._spaces = SpaceController(db)
        self._lifecycle = TieredLifecycleService(
            freeze_after_seconds=settings.freeze_after_minutes * 60,
            discard_after_seconds=settings.discard_after_minutes * 60,
        )
        self._snapshots = SnapshotCache()
        self._memory = MemoryMonitor()
        self._shortcuts = ShortcutRegistry.default(pass_through_mode=settings.pass_through_mode)
        self._send_service = SendService(_QtClipboardAdapter())
        self._companion = BrowserAppEngine(paths=paths)
        self._qt_engine_factory: Any = None  # Deferred import until after first paint (C3)

        self._active_space_id: str = ""
        self._active_pane_id: str = ""
        self._last_pane_by_space: dict[str, str] = {}
        self._focus_mode: bool = False
        self._maximized_pane_id: str | None = None
        self._tokens: ThemeTokens = DARK_TOKENS
        self._screen_hooked: bool = False
        self._lifecycle_tick_count: int = 0
        self._ram_warned: bool = False

        self.setWindowTitle("Kazu")
        self._restore_geometry()
        self._apply_theme()

        central = QWidget()
        central.setMinimumSize(0, 0)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._top_bar = TopBar(
            on_select_space=self.switch_space,
            on_delete_space=self.request_delete_space,
            on_new_space=self.create_new_space,
            on_open_palette=self.open_command_palette,
            on_open_settings=self.open_settings,
            on_rename_space=self._handle_rename_space,
        )
        self._stack = SpaceStack(on_layout_resized=self._handle_layout_resized)
        self._draft_composer = DraftComposer(
            on_send=self._handle_broadcast_send,
            on_close=lambda: self._focus_guard.schedule_focus_active_pane(),
        )
        # Floating overlay toast (never added to QVBoxLayout so it never shifts viewport height).
        self._toast = ToastBanner(self)

        layout.addWidget(self._top_bar)
        layout.addWidget(self._stack, stretch=1)
        layout.addWidget(self._draft_composer)
        self.setCentralWidget(central)

        self._focus_guard = FocusGuard(self._focus_active_pane, parent=self)
        self._register_shortcuts()
        self._register_shutdown_hooks()

        self._lifecycle_timer = QTimer(self)
        self._lifecycle_timer.timeout.connect(self._tick_lifecycle)
        self._lifecycle_timer.start(LIFECYCLE_POLL_MS)

        QTimer.singleShot(0, self._bootstrap_workspace)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        # Re-clamp once OS window frame/titlebar margins are realized so bottom never clips.
        QTimer.singleShot(0, self._clamp_to_active_screen)
        if not self._screen_hooked and self.windowHandle() is not None:
            self._screen_hooked = True
            self.windowHandle().screenChanged.connect(lambda _s: self._clamp_to_active_screen())

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._toast.isVisible():
            self._toast.reposition()

    def _clamp_to_active_screen(self) -> None:
        ensure_widget_on_screen(self)
        if self._toast.isVisible():
            self._toast.reposition()

    def _get_qt_factory(self) -> Any:
        if self._qt_engine_factory is None:
            from kazu.ui.engine_qt import QtWebEngineFactory

            self._qt_engine_factory = QtWebEngineFactory(
                paths=self._paths,
                bg_hex=self._tokens.bg,
                presets=self._presets,
                download_dir=self._settings.download_dir,
                on_download_started=self._handle_download_started,
            )
        return self._qt_engine_factory

    def _bootstrap_workspace(self) -> None:
        if not self._settings.onboarding_completed:
            dialog = OnboardingDialog(window_width_px=self.width(), parent=self)
            if dialog.exec():
                self._spaces.create_space_from_preset("Workspace", dialog.selected_layout)
            self._settings.onboarding_completed = True
            self._db.save_settings(self._settings)

        default_space = self._spaces.ensure_default_space()
        target_id = (
            self._settings.last_space_id
            if self._settings.restore_last_session
            and self._spaces.get_space(self._settings.last_space_id) is not None
            else default_space.id
        )
        self.switch_space(target_id)

    def switch_space(self, space_id: str) -> None:
        space = self._spaces.get_space(space_id)
        if space is None:
            return
        self._active_space_id = space.id
        self._maximized_pane_id = None
        self._settings.last_space_id = space.id
        self._db.save_settings(self._settings)

        waking_panes = set(self._lifecycle.activate_space(space.id))
        if not self._stack.show_space(space.id):
            tree = self._spaces.get_layout(space.id)
            self._stack.set_space_tree(space.id, tree, self._build_pane_frame)

        # Always restore active pane inside the target Space (even when cached in SpaceStack).
        space_panes = self._stack.panes_in_space(space.id)
        remembered = self._last_pane_by_space.get(space.id)
        valid_ids = {p.pane_id for p in space_panes}
        if remembered in valid_ids:
            self._set_active_pane(remembered)
        elif space_panes:
            self._set_active_pane(space_panes[0].pane_id)

        # Wake any Frozen or Discarded panes cleanly.
        for frame in space_panes:
            if frame._engine is not None and hasattr(frame._engine, "set_lifecycle_tier"):
                frame._engine.set_lifecycle_tier(LifecycleTier.LIVE)
            if frame.pane_id in waking_panes:
                snap = self._snapshots.get(frame.pane_id)
                if snap:
                    frame.show_snapshot_preview(snap)
                frame.reload(keep_snapshot=bool(snap))

        self._refresh_top_bar()
        self._focus_guard.schedule_focus_active_pane()

    def _switch_space_relative(self, delta: int) -> None:
        spaces = self._spaces.list_spaces()
        if len(spaces) < 2:
            return
        ids = [s.id for s in spaces]
        current_idx = ids.index(self._active_space_id) if self._active_space_id in ids else 0
        self.switch_space(ids[(current_idx + delta) % len(ids)])

    def _switch_space_by_index(self, index: int) -> None:
        spaces = self._spaces.list_spaces()
        if 0 <= index < len(spaces):
            self.switch_space(spaces[index].id)

    def create_new_space(self) -> None:
        count = len(self._spaces.list_spaces()) + 1
        space = self._spaces.create_space(f"Space {count}")
        self.switch_space(space.id)

    def request_delete_space(self, space_id: str) -> None:
        spaces = self._spaces.list_spaces()
        if len(spaces) <= 1:
            self._toast.show_message("You need at least one Space.")
            return

        target = self._spaces.get_space(space_id)
        if target is None:
            return

        if (
            self._settings.confirm_delete_space
            and not self._confirm_delete_space_dialog(target.name)
        ):
            return

        next_space_id = self._active_space_id
        if space_id == self._active_space_id:
            remaining = [s for s in spaces if s.id != space_id]
            next_space_id = remaining[0].id

        disposed_pane_ids = self._stack.remove_space(space_id)
        self._last_pane_by_space.pop(space_id, None)
        for pane_id in disposed_pane_ids:
            self._lifecycle.unregister_pane(pane_id)
            self._snapshots.remove(pane_id)

        if not self._spaces.delete_space(space_id):
            return

        if space_id == self._active_space_id:
            self.switch_space(next_space_id)
        else:
            self._refresh_top_bar()
        self._toast.show_message(f'Deleted Space "{target.name}".')

    def _confirm_delete_space_dialog(self, space_name: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle("Delete Space")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f'Are you sure you want to delete "{space_name}"?')
        box.setInformativeText(
            "Your saved accounts and logins stay safe and are not deleted."
        )

        dont_ask_cb = QCheckBox("Do not show this again")
        box.setCheckBox(dont_ask_cb)

        yes_btn = box.addButton("Yes, delete", QMessageBox.ButtonRole.DestructiveRole)
        no_btn = box.addButton("No, don't delete", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(no_btn)
        box.exec()

        if box.clickedButton() != yes_btn:
            return False

        if dont_ask_cb.isChecked():
            self._settings.confirm_delete_space = False
            self._db.save_settings(self._settings)
        return True

    def _build_pane_frame(self, node: PaneNode) -> PaneFrame:
        account = self._accounts.get_account(node.account_id) if node.account_id else None
        preset = self._presets.get(account.provider_key) if account else self._presets.get("custom")

        frame = PaneFrame(
            pane_id=node.pane_id,
            account=account,
            target_css_width=preset.target_css_width,
            zoom_mode=self._settings.zoom_mode,
            on_activate=self._set_active_pane,
            on_split=self._handle_split_pane,
            on_close=self._handle_close_pane,
            on_toggle_keep_running=self._handle_toggle_keep_running,
            on_switch_engine=self._switch_pane_engine,
            on_rename_account=self._handle_rename_account,
            on_zoom_changed=self._handle_zoom_changed,
        )
        frame.set_header_visible(not self._focus_mode)

        if account is None:
            picker = AccountPicker(
                presets=self._presets.list_enabled(),
                existing_accounts=self._accounts.list_accounts(),
                open_locations=self._spaces.find_open_account_locations,
                on_pick_new_provider=lambda key, url, pid=node.pane_id: self._assign_new_provider(
                    pid, key, url
                ),
                on_pick_existing_account=lambda aid, move, pid=node.pane_id: self._assign_existing(
                    pid, aid, move
                ),
            )
            frame.set_content_widget(picker)
        elif account.engine == EngineKind.COMPANION:
            card = self._companion.create_pane_widget(
                account=account,
                on_switch_embedded=lambda pid=node.pane_id: self._switch_pane_engine(
                    pid, EngineKind.EMBEDDED
                ),
            )
            frame.set_content_widget(card, engine=self._companion)
            if not self._companion.is_running(account.id):
                self._companion.launch(account)
        else:
            factory = self._get_qt_factory()
            pane_engine = factory.create_pane(
                account=account,
                on_activity=lambda pid=node.pane_id: self._on_pane_activity(pid),
                on_google_blocked=frame.show_google_block_card,
                on_crashed=frame.show_crash_card,
                on_signed_out_changed=frame.set_signed_out_hint,
                on_load_finished=frame.handle_load_finished,
            )
            frame.set_content_widget(pane_engine.widget, engine=pane_engine)
            self._lifecycle.register_pane(
                node.pane_id,
                self._active_space_id,
                visible=True,
                keep_running=account.keep_alive,
            )
            delay = STAGGER_PANE_MS * (len(self._stack.all_panes()) % 4)
            QTimer.singleShot(delay, lambda eng=pane_engine, u=account.home_url: eng.load_url(u))

        return frame

    def _assign_new_provider(self, pane_id: str, provider_key: str, custom_url: str | None) -> None:
        try:
            account = self._accounts.create_account(
                provider_key=provider_key, custom_url=custom_url
            )
        except ValueError as exc:
            self._toast.show_message(str(exc))
            return
        self._spaces.assign_account(self._active_space_id, pane_id, account.id)
        self._rebuild_space(self._active_space_id)

    def _assign_existing(self, pane_id: str, account_id: str, move_from_other: bool) -> None:
        if move_from_other:
            for space, other_pane_id in self._spaces.find_open_account_locations(account_id):
                self._spaces.assign_account(space.id, other_pane_id, None)
        self._spaces.assign_account(self._active_space_id, pane_id, account_id)
        self._rebuild_space(self._active_space_id)

    def _switch_pane_engine(self, pane_id: str, engine: EngineKind) -> None:
        frame = self._stack.get_pane(pane_id)
        if frame is None or frame.account is None:
            return
        self._accounts.switch_engine(frame.account.id, engine)
        self._rebuild_space(self._active_space_id)

    def _handle_rename_space(self, space_id: str, new_name: str) -> None:
        updated = self._spaces.rename_space(space_id, new_name)
        if updated is not None:
            self._refresh_top_bar()
            self._toast.show_message(f'Renamed Space to "{updated.name}".')

    def _handle_rename_account(self, account_id: str, new_label: str) -> None:
        self._accounts.rename_account(account_id, new_label)

    def _handle_zoom_changed(self, account_id: str, zoom: float) -> None:
        self._accounts.set_zoom(account_id, zoom)

    def _handle_split_pane(self, pane_id: str, orientation: Orientation) -> None:
        created = self._spaces.split_pane_in_space(self._active_space_id, pane_id, orientation)
        if created is not None:
            self._rebuild_space(self._active_space_id)
            self._set_active_pane(created.pane_id)

    def _handle_close_pane(self, pane_id: str) -> None:
        frame = self._stack.get_pane(pane_id)
        label = frame.account.label if (frame and frame.account) else "Pane"
        snapshot = self._spaces.close_pane_in_space(self._active_space_id, pane_id)
        if snapshot is None:
            return
        self._lifecycle.unregister_pane(pane_id)
        self._snapshots.remove(pane_id)
        self._rebuild_space(self._active_space_id)
        self._toast.show_message(
            f"Closed {label}",
            action_label="Undo (Ctrl+Shift+T)",
            on_action=self._undo_close_pane,
        )

    def _undo_close_pane(self) -> None:
        restored = self._spaces.undo_last_close()
        if restored is None:
            return
        self._rebuild_space(restored.space_id)
        if restored.space_id != self._active_space_id:
            self.switch_space(restored.space_id)

    def _handle_toggle_keep_running(self, pane_id: str, keep_running: bool) -> None:
        frame = self._stack.get_pane(pane_id)
        if frame is not None and frame.account is not None:
            self._accounts.set_keep_alive(frame.account.id, keep_running)
        self._lifecycle.set_keep_running(pane_id, keep_running)

    def _handle_layout_resized(self, space_id: str, root: Any) -> None:
        self._spaces.save_layout(space_id, root)

    def _rebuild_space(self, space_id: str) -> None:
        tree = self._spaces.get_layout(space_id)
        self._stack.set_space_tree(space_id, tree, self._build_pane_frame)
        if space_id == self._active_space_id:
            panes = iter_panes(tree)
            if panes:
                self._set_active_pane(panes[0].pane_id)

    def _set_active_pane(self, pane_id: str) -> None:
        self._active_pane_id = pane_id
        if self._active_space_id:
            self._last_pane_by_space[self._active_space_id] = pane_id
        for frame in self._stack.panes_in_space(self._active_space_id):
            frame.set_active(frame.pane_id == pane_id)

    def _focus_active_pane(self) -> bool:
        frame = self._stack.get_pane(self._active_pane_id)
        return frame.focus_input() if frame is not None else False

    def _active_provider_quirks(self) -> tuple[str, ...]:
        frame = self._stack.get_pane(self._active_pane_id)
        if frame is None or frame.account is None:
            return ()
        return self._presets.get(frame.account.provider_key).quirks

    def _on_pane_activity(self, pane_id: str) -> None:
        if self._lifecycle.record_activity(pane_id):
            self._refresh_top_bar()

    def _tick_lifecycle(self) -> None:
        transitions = self._lifecycle.evaluate_transitions()
        for pane_id, tier in transitions.items():
            frame = self._stack.get_pane(pane_id)
            if frame is None or frame._engine is None:
                continue
            if tier == LifecycleTier.DISCARDED and hasattr(frame._engine, "grab_snapshot_png"):
                self._snapshots.put(pane_id, frame._engine.grab_snapshot_png())
            if hasattr(frame._engine, "set_lifecycle_tier"):
                frame._engine.set_lifecycle_tier(tier)

        self._lifecycle_tick_count += 1
        if self._lifecycle_tick_count % RAM_CHECK_EVERY_N_TICKS == 0:
            sample = self._memory.sample()
            if self._memory.should_warn(sample) and not self._ram_warned:
                self._ram_warned = True
                self._toast.show_message(
                    f"Using {sample.total_rss_mb:.0f} MB RAM",
                    action_label="Freeze other Spaces",
                    on_action=self._freeze_other_spaces,
                    duration_ms=8000,
                )
            elif not self._memory.should_warn(sample):
                self._ram_warned = False

    def _freeze_other_spaces(self) -> None:
        transitions = self._lifecycle.freeze_other_spaces(self._active_space_id)
        for pane_id, tier in transitions.items():
            frame = self._stack.get_pane(pane_id)
            if frame is not None and frame._engine is not None:
                frame._engine.set_lifecycle_tier(tier)
        self._toast.show_message(f"Froze {len(transitions)} background pane(s) to save memory.")

    def _refresh_top_bar(self) -> None:
        spaces = self._spaces.list_spaces()
        unread = {
            s.id for s in spaces if self._lifecycle.space_has_unread_activity(s.id)
        }
        self._top_bar.render_spaces(spaces, self._active_space_id, unread)

    def open_command_palette(self) -> None:
        commands: list[PaletteCommand] = [
            PaletteCommand("New Space", "Ctrl+T", self.create_new_space),
            PaletteCommand(
                "Delete current Space",
                "",
                lambda: self.request_delete_space(self._active_space_id),
            ),
            PaletteCommand(
                "Split Right",
                "Ctrl+\\",
                lambda: self._handle_split_pane(self._active_pane_id, Orientation.HORIZONTAL),
            ),
            PaletteCommand(
                "Split Down",
                "Ctrl+Shift+\\",
                lambda: self._handle_split_pane(self._active_pane_id, Orientation.VERTICAL),
            ),
            PaletteCommand(
                "Maximize / Restore Pane", "Ctrl+Shift+Enter", self.toggle_maximize_pane
            ),
            PaletteCommand("Toggle Focus Mode", "", self.toggle_focus_mode),
            PaletteCommand("Open Draft Composer", "Ctrl+Shift+B", self.open_draft_composer),
            PaletteCommand("Paste Clipboard to All Panes", "Ctrl+Shift+V", self._paste_to_all),
            PaletteCommand("Freeze other Spaces", "", self._freeze_other_spaces),
            PaletteCommand("Undo Close Pane", "Ctrl+Shift+T", self._undo_close_pane),
            PaletteCommand("Open Settings", "Ctrl+,", self.open_settings),
        ]
        for space in self._spaces.list_spaces():
            commands.append(
                PaletteCommand(
                    f"Switch to Space: {space.name}",
                    "",
                    lambda sid=space.id: self.switch_space(sid),
                )
            )
        palette = CommandPalette(commands, parent=self)
        palette.exec()
        self._focus_guard.schedule_focus_active_pane()

    def open_draft_composer(self) -> None:
        targets = [
            (f.pane_id, f.account.label)
            for f in self._stack.panes_in_space(self._active_space_id)
            if f.account is not None
        ]
        self._draft_composer.open_composer(targets)

    def _paste_to_all(self) -> None:
        cb = QApplication.clipboard()
        text = cb.text().strip() if cb is not None else ""
        if not text:
            self._toast.show_message("Clipboard is empty.")
            return
        frames = [
            f
            for f in self._stack.panes_in_space(self._active_space_id)
            if f.account is not None
        ]
        if not frames:
            return
        result = self._send_service.send_text(text, frames)  # type: ignore[arg-type]
        self._toast.show_message(f"Pasted to {len(result.pasted_pane_ids)} pane(s).")

    def _handle_broadcast_send(self, text: str, pane_ids: list[str]) -> None:
        frames = [
            frame for pid in pane_ids if (frame := self._stack.get_pane(pid)) is not None
        ]
        result = self._send_service.send_text(text, frames)  # type: ignore[arg-type]
        if result.needs_manual_click_pane_ids:
            self._draft_composer.set_status(
                f"Pasted to {len(result.pasted_pane_ids)} pane(s); "
                f"{len(result.needs_manual_click_pane_ids)} needed a click in the chat box."
            )
        else:
            self._draft_composer.set_status(
                f"Pasted to {len(result.pasted_pane_ids)} pane(s). Clipboard restored."
            )

    def toggle_maximize_pane(self) -> None:
        """Temporarily hide sibling panes in the active Space to focus on one pane."""
        panes = self._stack.panes_in_space(self._active_space_id)
        if len(panes) <= 1:
            return
        if self._maximized_pane_id == self._active_pane_id:
            self._maximized_pane_id = None
            for frame in panes:
                frame.setVisible(True)
        else:
            self._maximized_pane_id = self._active_pane_id
            for frame in panes:
                frame.setVisible(frame.pane_id == self._active_pane_id)

    def toggle_focus_mode(self) -> None:
        self._focus_mode = not self._focus_mode
        self._top_bar.setVisible(not self._focus_mode)
        for frame in self._stack.all_panes():
            frame.set_header_visible(not self._focus_mode)

    def open_settings(self) -> None:
        dialog = SettingsDialog(
            settings=self._settings,
            memory_monitor=self._memory,
            on_freeze_other_spaces=self._freeze_other_spaces,
            parent=self,
        )
        if dialog.exec():
            self._db.save_settings(self._settings)
            self._shortcuts.pass_through_mode = self._settings.pass_through_mode
            self._lifecycle.update_thresholds(
                freeze_after_seconds=self._settings.freeze_after_minutes * 60,
                discard_after_seconds=self._settings.discard_after_minutes * 60,
            )
            for frame in self._stack.all_panes():
                frame.set_zoom_mode(self._settings.zoom_mode)
            self._apply_theme()
            if self._qt_engine_factory is not None:
                self._qt_engine_factory.set_download_dir(self._settings.download_dir)

    def _handle_download_started(self, filename: str, folder: str) -> None:
        self._toast.show_message(f'Downloading "{filename}" to {folder}', duration_ms=7000)

    def _apply_theme(self) -> None:
        if self._settings.theme == ThemeMode.LIGHT:
            self._tokens = LIGHT_TOKENS
        elif self._settings.theme == ThemeMode.DARK:
            self._tokens = DARK_TOKENS
        else:
            scheme = QApplication.styleHints().colorScheme()
            self._tokens = LIGHT_TOKENS if scheme == Qt.ColorScheme.Light else DARK_TOKENS
        self.setStyleSheet(build_qss(self._tokens))
        if self._qt_engine_factory is not None:
            self._qt_engine_factory.set_background_hex(self._tokens.bg)

    def _register_shortcuts(self) -> None:
        bindings = {
            "command_palette": self.open_command_palette,
            "new_space": self.create_new_space,
            "next_space": lambda: self._switch_space_relative(1),
            "prev_space": lambda: self._switch_space_relative(-1),
            "maximize_pane": self.toggle_maximize_pane,
            "close_pane": lambda: self._handle_close_pane(self._active_pane_id),
            "undo_close_pane": self._undo_close_pane,
            "draft_composer": self.open_draft_composer,
            "paste_to_all": self._paste_to_all,
            "settings": self.open_settings,
            "find_in_page": self._open_active_find,
            "reload_pane": self._reload_active_pane,
            "zoom_in": lambda: self._zoom_active_pane(ZOOM_STEP),
            "zoom_out": lambda: self._zoom_active_pane(-ZOOM_STEP),
            "zoom_reset": self._reset_active_zoom,
            "split_right": lambda: self._handle_split_pane(
                self._active_pane_id, Orientation.HORIZONTAL
            ),
            "split_down": lambda: self._handle_split_pane(
                self._active_pane_id, Orientation.VERTICAL
            ),
        }
        for action, callback in bindings.items():
            seq = self._shortcuts.get(action)
            if seq:
                sc = QShortcut(QKeySequence(seq), self)
                sc.activated.connect(
                    lambda act=action, cb=callback: (
                        cb()
                        if self._shortcuts.should_intercept(
                            act, active_provider_quirks=self._active_provider_quirks()
                        )
                        else None
                    )
                )

        # Ctrl+1..9 direct Space switching
        for idx in range(9):
            sc = QShortcut(QKeySequence(f"Ctrl+{idx + 1}"), self)
            sc.activated.connect(
                lambda i=idx: (
                    self._switch_space_by_index(i)
                    if not self._shortcuts.pass_through_mode
                    else None
                )
            )

    def _zoom_active_pane(self, delta: float) -> None:
        frame = self._stack.get_pane(self._active_pane_id)
        if frame is not None:
            frame.adjust_manual_zoom(delta)

    def _reset_active_zoom(self) -> None:
        frame = self._stack.get_pane(self._active_pane_id)
        if frame is not None:
            frame.reset_zoom(self._settings.zoom_mode)

    def _open_active_find(self) -> None:
        frame = self._stack.get_pane(self._active_pane_id)
        if frame is not None:
            frame.open_find_bar()

    def _reload_active_pane(self) -> None:
        frame = self._stack.get_pane(self._active_pane_id)
        if frame is not None:
            frame.reload()

    def _restore_geometry(self) -> None:
        qsettings = QSettings("Kazu", "Kazu")
        saved = qsettings.value("window/geometry")
        if saved is not None:
            self.restoreGeometry(saved)  # type: ignore[arg-type]
            ensure_widget_on_screen(self, use_default_size_if_unset=False)
        else:
            ensure_widget_on_screen(self, use_default_size_if_unset=True)

    def _save_geometry(self) -> None:
        qsettings = QSettings("Kazu", "Kazu")
        qsettings.setValue("window/geometry", self.saveGeometry())

    def _register_shutdown_hooks(self) -> None:
        self._shutdown.register_hide_views(self._save_geometry)
        self._shutdown.register_hide_views(self.hide)
        self._shutdown.register_destroy_views_and_pages(self._stack.dispose_all_panes)
        self._shutdown.register_destroy_profiles(self._dispose_qt_profiles)
        self._shutdown.register_checkpoint_storage(self._db.close)

    def _dispose_qt_profiles(self) -> None:
        if self._qt_engine_factory is not None:
            self._qt_engine_factory.dispose_all_profiles()
