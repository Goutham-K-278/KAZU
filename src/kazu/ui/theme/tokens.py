"""Design tokens and cached QSS generator keeping Light and Dark themes in sync (§8.7)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

# 8 color-blind-safe account dot colors matching domain.models.ACCOUNT_COLOR_KEYS.
ACCOUNT_DOT_HEX: dict[str, str] = {
    "cobalt": "#3B82F6",
    "teal": "#14B8A6",
    "amber": "#F59E0B",
    "coral": "#F97316",
    "violet": "#8B5CF6",
    "emerald": "#10B981",
    "rose": "#EC4899",
    "slate": "#64748B",
}


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """Color and geometry tokens for Kazu's calm minimal chrome."""

    name: str
    bg: str
    surface: str
    border: str
    text: str
    text_muted: str
    accent: str
    danger: str
    top_bar_height: int = 36
    pane_header_height: int = 26
    card_radius: int = 8
    button_radius: int = 6


LIGHT_TOKENS = ThemeTokens(
    name="light",
    bg="#FAFAF9",
    surface="#FFFFFF",
    border="#E7E5E4",
    text="#1C1917",
    text_muted="#78716C",
    accent="#5B6CFF",
    danger="#DC2626",
)

DARK_TOKENS = ThemeTokens(
    name="dark",
    bg="#0F0F10",
    surface="#171718",
    border="#262628",
    text="#EDEDED",
    text_muted="#9A9A9F",
    accent="#7280FF",
    danger="#F87171",
)


@lru_cache(maxsize=4)
def build_qss(tokens: ThemeTokens) -> str:
    """Generate and cache a complete Qt Style Sheet from a ThemeTokens palette."""
    return f"""
QMainWindow, QDialog, QWidget {{
    background-color: {tokens.bg};
    color: {tokens.text};
    font-size: 13px;
}}

QFrame#TopBar {{
    background-color: {tokens.surface};
    border-bottom: 1px solid {tokens.border};
    min-height: {tokens.top_bar_height}px;
    max-height: {tokens.top_bar_height}px;
}}

QFrame#SpaceTabGroup {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {tokens.button_radius}px;
}}

QFrame#SpaceTabGroup[active="true"] {{
    background-color: {tokens.bg};
    border: 1px solid {tokens.border};
}}

QPushButton#SpaceTab {{
    background: transparent;
    border: none;
    padding: 3px 6px 3px 9px;
    color: {tokens.text_muted};
    font-weight: 500;
}}

QPushButton#SpaceTab[active="true"] {{
    color: {tokens.text};
}}

QPushButton#SpaceTab:hover {{
    color: {tokens.text};
}}

QPushButton#SpaceCloseBtn {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 1px 5px;
    color: {tokens.text_muted};
    font-size: 12px;
    font-weight: 600;
}}

QPushButton#SpaceCloseBtn:hover {{
    background-color: {tokens.danger};
    color: #FFFFFF;
}}

QFrame#PaneHeader {{
    background-color: {tokens.surface};
    border-bottom: 1px solid {tokens.border};
    border-top: 2px solid transparent;
    min-height: {tokens.pane_header_height}px;
    max-height: {tokens.pane_header_height}px;
    font-size: 12px;
}}

QFrame#PaneHeader[active="true"] {{
    border-top: 2px solid {tokens.accent};
}}

QSplitter::handle {{
    background-color: {tokens.border};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}

QPushButton {{
    background-color: {tokens.surface};
    color: {tokens.text};
    border: 1px solid {tokens.border};
    border-radius: {tokens.button_radius}px;
    padding: 5px 10px;
}}

QPushButton:hover {{
    border-color: {tokens.accent};
}}

QPushButton#PrimaryButton {{
    background-color: {tokens.accent};
    color: #FFFFFF;
    border: none;
}}

QPushButton#DangerButton {{
    background-color: {tokens.danger};
    color: #FFFFFF;
    border: none;
}}

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background-color: {tokens.surface};
    color: {tokens.text};
    border: 1px solid {tokens.border};
    border-radius: {tokens.button_radius}px;
    padding: 5px 8px;
}}

QLineEdit:focus, QPlainTextEdit:focus {{
    border-color: {tokens.accent};
}}

QFrame#Card {{
    background-color: {tokens.surface};
    border: 1px solid {tokens.border};
    border-radius: {tokens.card_radius}px;
}}

QFrame#ToastBanner {{
    background-color: {tokens.surface};
    border: 1px solid {tokens.accent};
    border-radius: {tokens.card_radius}px;
    padding: 6px 12px;
}}

QLabel#MutedLabel {{
    color: {tokens.text_muted};
    font-size: 12px;
}}
"""
