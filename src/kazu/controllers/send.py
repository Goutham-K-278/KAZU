"""Clipboard-safe cross-pane send & broadcast service (Problem E1, Bug #8).

Zero scraping, zero DOM scripting: relies exclusively on the user's explicit
action, snapshots the system clipboard before pasting, and restores it cleanly
afterward.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ClipboardAdapter(Protocol):
    """Minimal clipboard interface so SendService is unit-testable without Qt."""

    def get_text(self) -> str: ...
    def set_text(self, text: str) -> None: ...


class PasteTarget(Protocol):
    """Minimal target pane interface for receiving a clipboard paste."""

    pane_id: str

    def focus_input(self) -> bool: ...
    def trigger_paste(self) -> None: ...


@dataclass(frozen=True, slots=True)
class BroadcastResult:
    """Outcome of a multi-pane send/paste operation."""

    pasted_pane_ids: tuple[str, ...]
    needs_manual_click_pane_ids: tuple[str, ...]


def normalize_selected_text(text: str) -> str:
    """Convert Qt paragraph separator U+2029 to standard newlines."""
    return text.replace("\u2029", "\n")


class SendService:
    """Snapshots and restores the user's clipboard while pasting to target panes."""

    def __init__(self, clipboard: ClipboardAdapter) -> None:
        self._clipboard = clipboard

    def send_text(self, text: str, targets: list[PasteTarget]) -> BroadcastResult:
        """Paste `text` into each target pane while preserving original clipboard text."""
        cleaned = normalize_selected_text(text)
        if not cleaned or not targets:
            return BroadcastResult((), ())

        saved_clipboard = self._clipboard.get_text()
        pasted: list[str] = []
        needs_click: list[str] = []

        try:
            self._clipboard.set_text(cleaned)
            for target in targets:
                if target.focus_input():
                    target.trigger_paste()
                    pasted.append(target.pane_id)
                else:
                    needs_click.append(target.pane_id)
        finally:
            self._clipboard.set_text(saved_clipboard)

        return BroadcastResult(
            pasted_pane_ids=tuple(pasted),
            needs_manual_click_pane_ids=tuple(needs_click),
        )
