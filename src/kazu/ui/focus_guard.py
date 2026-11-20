"""Automatic keyboard focus forwarding helper (Bug #1 fix).

Ensures that after switching Spaces, closing the Command Palette with Esc, or
clicking a pane header, keyboard focus lands directly inside the active pane's
web view rather than remaining stranded on a toolbar button.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer


class FocusGuard(QObject):
    """Defers focus restoration by one event-loop tick so Qt finishes tab activation."""

    def __init__(  # noqa: E501
        self, focus_active_pane: Callable[[], bool], parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._focus_active_pane = focus_active_pane

    def schedule_focus_active_pane(self) -> None:
        """Forward focus to the active pane on the next Qt event loop turn."""
        QTimer.singleShot(0, self._focus_active_pane)
