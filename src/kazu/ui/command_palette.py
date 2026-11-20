"""Fuzzy-search Command Palette (Ctrl/Cmd+K; §8.5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True, slots=True)
class PaletteCommand:
    """One executable action shown in the Command Palette."""

    label: str
    shortcut: str
    callback: Callable[[], None]


def fuzzy_score(query: str, text: str) -> int:
    """Simple subsequence fuzzy matcher returning > 0 when query matches text."""
    q = query.strip().lower()
    if not q:
        return 1
    t = text.lower()
    if q in t:
        return 100 - t.index(q)
    pos = 0
    for ch in q:
        idx = t.find(ch, pos)
        if idx == -1:
            return 0
        pos = idx + 1
    return 10


class CommandPalette(QDialog):
    """Keyboard-first action launcher."""

    def __init__(
        self,
        commands: list[PaletteCommand],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setMinimumSize(460, 340)
        self._commands = commands
        self._filtered: list[PaletteCommand] = list(commands)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a command or Space name...")
        self._input.textChanged.connect(self._refresh)
        self._input.returnPressed.connect(self._execute_selected)

        self._list = QListWidget()
        self._list.itemActivated.connect(lambda _: self._execute_selected())

        layout.addWidget(self._input)
        layout.addWidget(self._list, stretch=1)
        self._refresh("")
        self._input.setFocus()

    def _refresh(self, query: str) -> None:
        scored = [
            (fuzzy_score(query, cmd.label), cmd)
            for cmd in self._commands
        ]
        self._filtered = [cmd for score, cmd in sorted(scored, key=lambda x: -x[0]) if score > 0]
        self._list.clear()
        for cmd in self._filtered:
            suffix = f"   ({cmd.shortcut})" if cmd.shortcut else ""
            self._list.addItem(QListWidgetItem(f"{cmd.label}{suffix}"))
        if self._filtered:
            self._list.setCurrentRow(0)

    def _execute_selected(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._filtered):
            cmd = self._filtered[row]
            self.accept()
            cmd.callback()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
