"""Window geometry clamping for multi-monitor & unplugged displays (Bug #4 fix).

Provides pure-Python rectangle clamping (testable without Qt) plus a thin Qt
helper that validates a QWidget's geometry against QGuiApplication.screens().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MIN_WINDOW_WIDTH: int = 640
MIN_WINDOW_HEIGHT: int = 480


@dataclass(frozen=True, slots=True)
class Rect:
    """Platform-independent screen or window rectangle."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def intersection_area(self, other: Rect) -> int:
        overlap_w = max(0, min(self.right, other.right) - max(self.x, other.x))
        overlap_h = max(0, min(self.bottom, other.bottom) - max(self.y, other.y))
        return overlap_w * overlap_h


def clamp_window_rect(saved: Rect, screens: list[Rect]) -> Rect:
    """Ensure `saved` is visible on at least one active screen.

    If the saved window is mostly or completely off-screen (for example, after
    unplugging an external monitor), clamp and center it onto the primary screen.
    """
    if not screens:
        return Rect(
            x=max(0, saved.x),
            y=max(0, saved.y),
            width=max(MIN_WINDOW_WIDTH, saved.width),
            height=max(MIN_WINDOW_HEIGHT, saved.height),
        )

    best_screen = max(screens, key=lambda s: saved.intersection_area(s))
    overlap = saved.intersection_area(best_screen)
    saved_area = max(1, saved.width * saved.height)

    target_screen = best_screen if (overlap / saved_area) >= 0.25 else screens[0]

    clamped_w = min(max(MIN_WINDOW_WIDTH, saved.width), target_screen.width)
    clamped_h = min(max(MIN_WINDOW_HEIGHT, saved.height), target_screen.height)

    if overlap == 0 or (overlap / saved_area) < 0.25:
        clamped_x = target_screen.x + (target_screen.width - clamped_w) // 2
        clamped_y = target_screen.y + (target_screen.height - clamped_h) // 2
    else:
        clamped_x = max(target_screen.x, min(saved.x, target_screen.right - clamped_w))
        clamped_y = max(target_screen.y, min(saved.y, target_screen.bottom - clamped_h))

    return Rect(x=clamped_x, y=clamped_y, width=clamped_w, height=clamped_h)


def ensure_widget_on_screen(widget: Any) -> None:
    """Clamp a Qt top-level window onto connected screens using QGuiApplication."""
    from PySide6.QtGui import QGuiApplication

    qt_screens = QGuiApplication.screens()
    if not qt_screens:
        return
    screen_rects = []
    for screen in qt_screens:
        avail = screen.availableGeometry()
        screen_rects.append(Rect(avail.x(), avail.y(), avail.width(), avail.height()))

    geom = widget.geometry()
    clamped = clamp_window_rect(
        Rect(geom.x(), geom.y(), geom.width(), geom.height()),
        screen_rects,
    )
    widget.setGeometry(clamped.x, clamped.y, clamped.width, clamped.height)
