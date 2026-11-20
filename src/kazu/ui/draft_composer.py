"""Collapsible Multi-Pane Draft Composer (Ctrl/Cmd+Shift+B; Problem E1, Bug #8).

Lets the user compose one prompt and send it via clipboard-safe paste to selected
panes while preserving the user's original clipboard content.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DraftComposer(QFrame):
    """Quiet bottom drawer for broadcasting a prompt to chosen panes."""

    def __init__(
        self,
        on_send: Callable[[str, list[str]], None],
        on_close: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._on_send = on_send
        self._on_close = on_close
        self._target_checks: dict[str, QCheckBox] = {}
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Draft Composer — paste to selected panes (your clipboard is preserved)")
        title.setObjectName("MutedLabel")
        close_btn = QPushButton("×")
        close_btn.setAccessibleName("Close Draft Composer")
        close_btn.clicked.connect(self.close_composer)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(close_btn)
        layout.addLayout(header)

        self._targets_row = QHBoxLayout()
        layout.addLayout(self._targets_row)

        self._editor = QPlainTextEdit()
        self._editor.setPlaceholderText("Write a prompt once, then paste to selected panes...")
        self._editor.setMaximumHeight(96)
        layout.addWidget(self._editor)

        footer = QHBoxLayout()
        self._status = QLabel("")
        self._status.setObjectName("MutedLabel")
        send_btn = QPushButton("Paste to selected")
        send_btn.setObjectName("PrimaryButton")
        send_btn.clicked.connect(self._handle_send)
        footer.addWidget(self._status)
        footer.addStretch(1)
        footer.addWidget(send_btn)
        layout.addLayout(footer)

    def set_targets(self, targets: list[tuple[str, str]]) -> None:
        """Populate checkboxes from `(pane_id, account_label)` pairs."""
        while self._targets_row.count():
            item = self._targets_row.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        self._target_checks.clear()

        for pane_id, label in targets:
            cb = QCheckBox(label)
            cb.setChecked(True)
            self._target_checks[pane_id] = cb
            self._targets_row.addWidget(cb)
        self._targets_row.addStretch(1)

    def open_composer(self, targets: list[tuple[str, str]]) -> None:
        self.set_targets(targets)
        self._status.setText("")
        self.show()
        self._editor.setFocus()

    def close_composer(self) -> None:
        self.hide()
        self._on_close()

    def set_status(self, message: str) -> None:
        self._status.setText(message)

    def _handle_send(self) -> None:
        text = self._editor.toPlainText().strip()
        if not text:
            return
        chosen = [pid for pid, cb in self._target_checks.items() if cb.isChecked()]
        if not chosen:
            self._status.setText("Select at least one pane.")
            return
        self._on_send(text, chosen)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.close_composer()
            return
        super().keyPressEvent(event)
