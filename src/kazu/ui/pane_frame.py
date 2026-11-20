"""Individual pane container hosting header, FindBar, content engine, and recovery cards."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kazu.controllers.autofit import AutoFitZoomService
from kazu.domain.models import Account, Orientation, ZoomMode
from kazu.ui.block_card import build_crash_card, build_google_block_card
from kazu.ui.find_bar import FindBar
from kazu.ui.theme.tokens import ACCOUNT_DOT_HEX


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
        self._on_switch_companion = on_switch_companion
        self._engine: Any = None

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
            on_close=self.focus_input,
            parent=self,
        )
        root.addWidget(self._find_bar)

        # Stacked content: primary view / snapshot wake preview / recovery cards
        self._stack = QStackedWidget()
        root.addWidget(self._stack, stretch=1)

        self._snapshot_label = QLabel("Waking up...")
        self._snapshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._snapshot_label)

    def set_header_visible(self, visible: bool) -> None:
        """Toggle pane header for Focus mode (§8.1)."""
        self._header.setVisible(visible)

    def set_active(self, active: bool) -> None:
        self._header.setProperty("active", "true" if active else "false")
        self._header.style().unpolish(self._header)
        self._header.style().polish(self._header)

    def set_signed_out_hint(self, signed_out: bool) -> None:
        self._signed_out_dot.setVisible(signed_out)

    def set_content_widget(self, widget: QWidget, engine: Any = None) -> None:
        self._engine = engine
        idx = self._stack.addWidget(widget)
        self._stack.setCurrentIndex(idx)

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
            on_use_email=self.reload,
            on_switch_companion=lambda: (
                self._on_switch_companion(self.pane_id) if self._on_switch_companion else None
            ),
            parent=self,
        )
        idx = self._stack.addWidget(card)
        self._stack.setCurrentIndex(idx)

    def show_crash_card(self) -> None:
        card = build_crash_card(on_reload=self.reload, parent=self)
        idx = self._stack.addWidget(card)
        self._stack.setCurrentIndex(idx)

    def open_find_bar(self) -> None:
        self._find_bar.open_bar()

    def reload(self) -> None:
        if self._engine is not None and hasattr(self._engine, "reload"):
            self._engine.reload()
            if self._stack.count() > 1:
                self._stack.setCurrentIndex(1)

    def focus_input(self) -> bool:
        if self._engine is not None and hasattr(self._engine, "focus_view"):
            return bool(self._engine.focus_view())
        self.setFocus()
        return self.hasFocus()

    def trigger_paste(self) -> None:
        if self._engine is not None and hasattr(self._engine, "trigger_paste"):
            self._engine.trigger_paste()

    def dispose(self) -> None:
        if self._engine is not None and hasattr(self._engine, "dispose"):
            self._engine.dispose()
            self._engine = None

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self._on_activate is not None:
            self._on_activate(self.pane_id)
        super().mousePressEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._engine is not None and hasattr(self._engine, "set_zoom") and self.account:
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

    def _handle_pin_toggled(self, checked: bool) -> None:
        self._pin_btn.setText("📌" if checked else "○")
        if self._on_toggle_keep_running is not None:
            self._on_toggle_keep_running(self.pane_id, checked)

    def _open_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Reload", self.reload)
        if self._engine is not None and hasattr(self._engine, "back"):
            menu.addAction("Back", self._engine.back)
            menu.addAction("Forward", self._engine.forward)
        menu.addAction("Find in page", self.open_find_bar)
        menu.addSeparator()
        if self._on_split is not None:
            menu.addAction("Split Right", lambda: self._on_split(self.pane_id, Orientation.HORIZONTAL))
            menu.addAction("Split Down", lambda: self._on_split(self.pane_id, Orientation.VERTICAL))
        if self._on_switch_companion is not None and self.account is not None:
            menu.addAction("Open in Companion Mode", lambda: self._on_switch_companion(self.pane_id))
        menu.addSeparator()
        if self._on_close is not None:
            menu.addAction("Close Pane", lambda: self._on_close(self.pane_id))
        menu.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))
