"""Compact find-in-page bar (Ctrl/Cmd+F)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QPushButton, QWidget


class FindBar(QFrame):
    """Inline find bar attached to the active pane."""

    def __init__(
        self,
        on_search: Callable[[str], None],
        on_close: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_search = on_search
        self._on_close = on_close
        self.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Find in page...")
        self._input.textChanged.connect(self._on_search)
        self._input.returnPressed.connect(lambda: self._on_search(self._input.text()))

        close_btn = QPushButton("×")
        close_btn.setAccessibleName("Close find bar")
        close_btn.clicked.connect(self.close_bar)

        layout.addWidget(self._input, stretch=1)
        layout.addWidget(close_btn)

    def open_bar(self) -> None:
        self.show()
        self._input.setFocus()
        self._input.selectAll()

    def close_bar(self) -> None:
        self._input.clear()
        self._on_search("")
        self.hide()
        self._on_close()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.close_bar()
            return
        super().keyPressEvent(event)
