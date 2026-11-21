"""Individual pane container hosting header, FindBar, content engine, and recovery cards."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kazu.controllers.autofit import AutoFitZoomService
from kazu.domain.models import Account, EngineKind, Orientation, ZoomMode
from kazu.ui.block_card import build_crash_card, build_google_block_card
from kazu.ui.find_bar import FindBar
from kazu.ui.theme.tokens import ACCOUNT_DOT_HEX

MIN_RESIZE_WIDTH_FOR_ZOOM: int = 200


class PaneFrame(QFrame):
    """Visual frame for one pane with a 26px header, dot, Keep Running pin, and ⋯ menu."""

    def __init__(
        self,
        pane_id: str,
        account: Account | None,
        *,
        target_css_width: int = 950,
        zoom_mode: ZoomMode = ZoomMode.FIT_DESKTOP,
        on_activate: Callable[[str], None] | None = None,
        on_split: Callable[[str, Orientation], None] | None = None,
        on_close: Callable[[str], None] | None = None,
        on_toggle_keep_running: Callable[[str, bool], None] | None = None,
        on_switch_engine: Callable[[str, EngineKind], None] | None = None,
        on_rename_account: Callable[[str, str], None] | None = None,
        on_switch_companion: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pane_id = pane_id
        self.account = account
        self._target_css_width = target_css_width
        self._zoom_mode = zoom_mode
        self._autofit = AutoFitZoomService()
        self._on_activate = on_activate
        self._on_split = on_split
        self._on_close = on_close
        self._on_toggle_keep_running = on_toggle_keep_running
        self._on_rename_account = on_rename_account
        self._on_switch_engine = on_switch_engine
        self._on_switch_companion = on_switch_companion
        self._engine: Any = None
        self._content_widget: QWidget | None = None
        self._overlay_card: QWidget | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 26px Pane Header
        self._header = QFrame()
        self._header.setObjectName("PaneHeader")
        h_layout = QHBoxLayout(self._header)
        h_layout.setContentsMargins(8, 0, 6, 0)
        h_layout.setSpacing(6)

        dot_hex = ACCOUNT_DOT_HEX.get(account.color, "#3B82F6") if account else "#64748B"
        self._dot_label = QLabel("●")
        self._dot_label.setStyleSheet(f"color: {dot_hex}; font-size: 11px;")

        self._title_label = QLabel(account.label if account else "Empty Pane")
        self._signed_out_dot = QLabel("●")
        self._signed_out_dot.setStyleSheet("color: #F59E0B; font-size: 10px;")
        self._signed_out_dot.setToolTip("May need sign-in")
        self._signed_out_dot.hide()

        self._pin_btn = QPushButton("📌" if (account and account.keep_alive) else "○")
        self._pin_btn.setCheckable(True)
        self._pin_btn.setChecked(bool(account and account.keep_alive))
        self._pin_btn.setAccessibleName("Keep Running")
        self._pin_btn.setToolTip("Keep Running (never freeze this pane)")
        self._pin_btn.setMaximumWidth(28)
        self._pin_btn.toggled.connect(self._handle_pin_toggled)

        self._menu_btn = QPushButton("⋯")
        self._menu_btn.setAccessibleName("Pane options")
        self._menu_btn.setMaximumWidth(28)
        self._menu_btn.clicked.connect(self._open_menu)

        h_layout.addWidget(self._dot_label)
        h_layout.addWidget(self._title_label)
        h_layout.addWidget(self._signed_out_dot)
        h_layout.addStretch(1)
        h_layout.addWidget(self._pin_btn)
        h_layout.addWidget(self._menu_btn)
        root.addWidget(self._header)

        # Inline FindBar (hidden until Ctrl+F)
        self._find_bar = FindBar(
            on_search=self._handle_find,
            on_close=self._close_find_bar,
            parent=self,
        )
        root.addWidget(self._find_bar)

        # Stacked content: snapshot wake preview / primary view / single overlay card
        self._stack = QStackedWidget()
        root.addWidget(self._stack, stretch=1)

        self._snapshot_label = QLabel("Waking up...")
        self._snapshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._snapshot_label)

    def set_header_visible(self, visible: bool) -> None:
        """Toggle pane header for Focus mode (§8.1)."""
        self._header.setVisible(visible)

    def set_zoom_mode(self, mode: ZoomMode) -> None:
        """Apply updated zoom mode immediately."""
        self._zoom_mode = mode
        self._apply_autofit_zoom()

    def set_active(self, active: bool) -> None:
        self._header.setProperty("active", "true" if active else "false")
        self._header.style().unpolish(self._header)
        self._header.style().polish(self._header)

    def set_signed_out_hint(self, signed_out: bool) -> None:
        self._signed_out_dot.setVisible(signed_out)

    def set_content_widget(self, widget: QWidget, engine: Any = None) -> None:
        if self._content_widget is not None:
            self._stack.removeWidget(self._content_widget)
            self._content_widget.deleteLater()
        self._clear_overlay_card()
        self._engine = engine
        self._content_widget = widget
        self._stack.addWidget(widget)
        self._stack.setCurrentWidget(widget)

    def _show_overlay_card(self, card: QWidget) -> None:
        self._clear_overlay_card()
        self._overlay_card = card
        self._stack.addWidget(card)
        self._stack.setCurrentWidget(card)

    def _clear_overlay_card(self) -> None:
        if self._overlay_card is not None:
            self._stack.removeWidget(self._overlay_card)
            self._overlay_card.deleteLater()
            self._overlay_card = None

    def show_snapshot_preview(self, png_bytes: bytes) -> None:
        pixmap = QPixmap()
        if png_bytes and pixmap.loadFromData(png_bytes, "PNG"):
            self._snapshot_label.setPixmap(
                pixmap.scaled(
                    self._stack.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self._snapshot_label.setText("Waking up...")
        self._stack.setCurrentWidget(self._snapshot_label)

    def show_google_block_card(self) -> None:
        card = build_google_block_card(
            on_use_email=self.load_home,
            on_switch_companion=lambda: self._request_switch_engine(EngineKind.COMPANION),
            parent=self,
        )
        self._show_overlay_card(card)

    def show_crash_card(self) -> None:
        card = build_crash_card(on_reload=self.reload, parent=self)
        self._show_overlay_card(card)

    def open_find_bar(self) -> None:
        self._find_bar.open_bar()

    def load_home(self) -> None:
        """Return to the account's home URL (used by 'Use email login' to escape Google block)."""
        self._clear_overlay_card()
        if self._content_widget is not None:
            self._stack.setCurrentWidget(self._content_widget)
        if (
            self._engine is not None
            and hasattr(self._engine, "load_url")
            and self.account is not None
        ):
            self._engine.load_url(self.account.home_url)

    def reload(self) -> None:
        self._clear_overlay_card()
        if self._content_widget is not None:
            self._stack.setCurrentWidget(self._content_widget)
        if self._engine is not None and hasattr(self._engine, "reload"):
            self._engine.reload()

    def focus_input(self) -> bool:
        if self._engine is not None and hasattr(self._engine, "focus_view"):
            return bool(self._engine.focus_view())
        self.setFocus()
        return self.hasFocus()

    def trigger_paste(self) -> None:
        if self._engine is not None and hasattr(self._engine, "trigger_paste"):
            self._engine.trigger_paste()

    def dispose(self) -> None:
        self._clear_overlay_card()
        if self._engine is not None and hasattr(self._engine, "dispose"):
            self._engine.dispose()
            self._engine = None

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self._on_activate is not None:
            self._on_activate(self.pane_id)
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_autofit_zoom()

    def _apply_autofit_zoom(self) -> None:
        if (
            self.width() >= MIN_RESIZE_WIDTH_FOR_ZOOM
            and self._engine is not None
            and hasattr(self._engine, "set_zoom")
            and self.account is not None
        ):
            result = self._autofit.compute(
                pane_width_px=self.width(),
                target_css_width=self._target_css_width,
                mode=self._zoom_mode,
                manual_zoom=self.account.zoom,
            )
            self._engine.set_zoom(result.zoom)

    def _handle_find(self, query: str) -> None:
        if self._engine is not None and hasattr(self._engine, "find_text"):
            self._engine.find_text(query)

    def _close_find_bar(self) -> None:
        """Close the find bar and return focus to the pane content."""
        self.focus_input()

    def _handle_pin_toggled(self, checked: bool) -> None:
        self._pin_btn.setText("📌" if checked else "○")
        if self._on_toggle_keep_running is not None:
            self._on_toggle_keep_running(self.pane_id, checked)

    def _request_switch_engine(self, target: EngineKind) -> None:
        """Route engine-switch requests through on_switch_engine or legacy on_switch_companion."""
        if self._on_switch_engine is not None:
            self._on_switch_engine(self.pane_id, target)
        elif target == EngineKind.COMPANION and self._on_switch_companion is not None:
            self._on_switch_companion(self.pane_id)

    def _open_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Reload", self.reload)
        if self._engine is not None and hasattr(self._engine, "back"):
            menu.addAction("Back", self._engine.back)
            menu.addAction("Forward", self._engine.forward)
        menu.addAction("Find in page", self.open_find_bar)
        menu.addSeparator()

        if self.account is not None and self._on_rename_account is not None:
            menu.addAction("Rename pane...", self._handle_rename_account)

        if self.account is not None:
            if self.account.engine == EngineKind.COMPANION:
                menu.addAction(
                    "Switch to Embedded Mode",
                    lambda: self._request_switch_engine(EngineKind.EMBEDDED),
                )
            else:
                menu.addAction(
                    "Open in Companion Mode",
                    lambda: self._request_switch_engine(EngineKind.COMPANION),
                )

        menu.addSeparator()
        if self._on_split is not None:
            split_fn = self._on_split
            menu.addAction(
                "Split Right",
                lambda: split_fn(self.pane_id, Orientation.HORIZONTAL),
            )
            menu.addAction(
                "Split Down",
                lambda: split_fn(self.pane_id, Orientation.VERTICAL),
            )
        menu.addSeparator()
        if self._on_close is not None:
            close_fn = self._on_close
            menu.addAction("Close Pane", lambda: close_fn(self.pane_id))
        menu.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))

    def _handle_rename_account(self) -> None:
        """Prompt the user for a new label and update both DB and in-memory Account."""
        if self.account is None or self._on_rename_account is None:
            return
        new_label, ok = QInputDialog.getText(
            self,
            "Rename Pane",
            "Enter a new name for this pane:",
            text=self.account.label,
        )
        cleaned = new_label.strip()
        if ok and cleaned:
            self.account.label = cleaned
            self._on_rename_account(self.account.id, cleaned)
            self._title_label.setText(cleaned)
