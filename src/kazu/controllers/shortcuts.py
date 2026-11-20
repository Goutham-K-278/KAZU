"""Rebindable shortcut registry with Pass-Through Mode and conflict detection (Bug #6)."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SHORTCUTS: dict[str, str] = {
    "command_palette": "Ctrl+K",
    "new_space": "Ctrl+T",
    "next_space": "Ctrl+Tab",
    "prev_space": "Ctrl+Shift+Tab",
    "split_right": "Ctrl+\\",
    "split_down": "Ctrl+Shift+\\",
    "maximize_pane": "Ctrl+Shift+Return",
    "close_pane": "Ctrl+W",
    "undo_close_pane": "Ctrl+Shift+T",
    "find_in_page": "Ctrl+F",
    "reload_pane": "Ctrl+R",
    "zoom_in": "Ctrl+=",
    "zoom_out": "Ctrl+-",
    "zoom_reset": "Ctrl+0",
    "draft_composer": "Ctrl+Shift+B",
    "paste_to_all": "Ctrl+Shift+V",
    "settings": "Ctrl+,",
}

# Known website shortcuts that conflict with app defaults (e.g. ChatGPT uses Ctrl+K).
PROVIDER_CONFLICTS: dict[str, tuple[str, ...]] = {
    "uses_ctrl_k": ("command_palette",),
}


@dataclass(slots=True)
class ShortcutRegistry:
    """Manages key bindings, user overrides, and Pass-Through Mode."""

    bindings: dict[str, str]
    pass_through_mode: bool = False

    @classmethod
    def default(cls, pass_through_mode: bool = False) -> ShortcutRegistry:
        return cls(bindings=dict(DEFAULT_SHORTCUTS), pass_through_mode=pass_through_mode)

    def get(self, action: str) -> str:
        return self.bindings.get(action, "")

    def rebind(self, action: str, sequence: str) -> bool:
        if action not in self.bindings or not sequence.strip():
            return False
        self.bindings[action] = sequence.strip()
        return True

    def should_intercept(
        self, action: str, *, active_provider_quirks: tuple[str, ...] = ()
    ) -> bool:
        """Return False when Pass-Through Mode is active or the site claims this combo."""
        if self.pass_through_mode:
            return False
        for quirk in active_provider_quirks:
            if action in PROVIDER_CONFLICTS.get(quirk, ()):
                return False
        return action in self.bindings
