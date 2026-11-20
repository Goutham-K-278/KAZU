"""Core domain models for Kazu.

This module intentionally has ZERO Qt imports so all domain logic can be tested
headlessly and reused across engines.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

# Eight color-blind-safe Okabe-Ito-inspired palette keys for account dots.
ACCOUNT_COLOR_KEYS: tuple[str, ...] = (
    "cobalt",
    "teal",
    "amber",
    "coral",
    "violet",
    "emerald",
    "rose",
    "slate",
)

DEFAULT_ZOOM: float = 1.0
MIN_ZOOM: float = 0.5
MAX_ZOOM: float = 2.0
LAYOUT_SCHEMA_VERSION: int = 1


class EngineKind(StrEnum):
    """Supported pane rendering backends."""

    EMBEDDED = "embedded"
    COMPANION = "companion"


class Orientation(StrEnum):
    """Split direction for a layout container."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


class ThemeMode(StrEnum):
    """User-selectable visual theme mode."""

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class DensityMode(StrEnum):
    """UI spacing density preference."""

    COMFORTABLE = "comfortable"
    COMPACT = "compact"


class ZoomMode(StrEnum):
    """Narrow-pane zoom strategy."""

    FIT_DESKTOP = "fit_desktop"
    NATIVE_NARROW = "native_narrow"


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    """Generate a new lowercase UUID4 string."""
    return str(uuid.uuid4())


def clamp_zoom(value: float) -> float:
    """Clamp a zoom factor to safe display bounds."""
    return max(MIN_ZOOM, min(MAX_ZOOM, float(value)))


@dataclass(slots=True)
class Account:
    """One persistent, isolated browser session for an AI provider or custom URL."""

    id: str
    label: str
    provider_key: str
    home_url: str
    engine: EngineKind = EngineKind.EMBEDDED
    color: str = ACCOUNT_COLOR_KEYS[0]
    zoom: float = DEFAULT_ZOOM
    keep_alive: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    last_used_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.label = self.label.strip() or "Untitled Account"
        self.provider_key = self.provider_key.strip().lower() or "custom"
        self.home_url = self.home_url.strip()
        if not isinstance(self.engine, EngineKind):
            self.engine = EngineKind(str(self.engine))
        if self.color not in ACCOUNT_COLOR_KEYS:
            self.color = ACCOUNT_COLOR_KEYS[0]
        self.zoom = clamp_zoom(self.zoom)


@dataclass(slots=True)
class Space:
    """A saved workspace containing a layout tree of panes."""

    id: str
    name: str
    order_index: int
    layout_json: str

    def __post_init__(self) -> None:
        self.name = self.name.strip() or "Untitled Space"
        self.order_index = max(0, int(self.order_index))


@dataclass(slots=True)
class AppSettings:
    """User-configurable application settings with sensible defaults."""

    restore_last_session: bool = True
    launch_on_login: bool = False
    close_to_tray: bool = False
    confirm_delete_space: bool = True
    theme: ThemeMode = ThemeMode.SYSTEM
    density: DensityMode = DensityMode.COMFORTABLE
    accent_color: str = "#5B6CFF"
    zoom_mode: ZoomMode = ZoomMode.FIT_DESKTOP
    freeze_after_minutes: int = 10
    discard_after_minutes: int = 30
    show_memory_per_pane: bool = False
    pass_through_mode: bool = False
    onboarding_completed: bool = False
    sync_folder: str = ""
    download_dir: str = ""
    last_space_id: str = ""

    def __post_init__(self) -> None:
        self.freeze_after_minutes = max(1, int(self.freeze_after_minutes))
        self.discard_after_minutes = max(
            self.freeze_after_minutes + 1,
            int(self.discard_after_minutes),
        )
