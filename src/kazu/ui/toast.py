"""Non-blocking floating overlay toast notification (never shifts layout height)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

DEFAULT_TOAST_MS: int = 5000
TOAST_BOTTOM_MARGIN_PX: int = 18


class ToastBanner(QFrame):
    """Calm floating overlay toast anchored at bottom-center of its parent window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ToastBanner")
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        self._label = QLabel("")
        self._action_btn = QPushButton("")
        self._action_btn.setObjectName("PrimaryButton")
        self._action_btn.hide()

        layout.addWidget(self._label)
        layout.addWidget(self._action_btn)

        self._callback: Callable[[], None] | None = None
        self._action_btn.clicked.connect(self._trigger_action)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def reposition(self) -> None:
        """Center this floating banner near the bottom of its parent without affecting layout."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        max_w = max(220, parent.width() - 32)
        width = min(self.sizeHint().width(), max_w)
        height = self.sizeHint().height()
        x = max(16, (parent.width() - width) // 2)
        y = max(16, parent.height() - height - TOAST_BOTTOM_MARGIN_PX)
        self.setGeometry(x, y, width, height)

    def show_message(
        self,
        message: str,
        *,
        action_label: str = "",
        on_action: Callable[[], None] | None = None,
        duration_ms: int = DEFAULT_TOAST_MS,
    ) -> None:
        self._label.setText(message)
        self._callback = on_action
        if action_label and on_action is not None:
            self._action_btn.setText(action_label)
            self._action_btn.show()
        else:
            self._action_btn.hide()

        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def _trigger_action(self) -> None:
        self._timer.stop()
        self.hide()
        if self._callback is not None:
            self._callback()
