"""Window geometry clamping for multi-monitor, HiDPI, and unplugged displays (Bug #4 + Scaling Fix).

Provides pure-Python rectangle clamping (testable without Qt) that accounts for
OS window frame margins (title bar + borders) so the bottom of the app NEVER
extends underneath the taskbar or off-screen, plus Qt helpers for clamping on
launch, showEvent, and monitor/DPI changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MIN_WINDOW_WIDTH: int = 640
MIN_WINDOW_HEIGHT: int = 480
DEFAULT_SCREEN_FILL_RATIO: float = 0.88
DEFAULT_TITLEBAR_MARGIN_PX: int = 36
DEFAULT_SIDE_BORDER_PX: int = 8


@dataclass(frozen=True, slots=True)
class FrameMargins:
    """Pixel thickness of the OS window decorations (title bar + borders)."""

    left: int = DEFAULT_SIDE_BORDER_PX
    top: int = DEFAULT_TITLEBAR_MARGIN_PX
    right: int = DEFAULT_SIDE_BORDER_PX
    bottom: int = DEFAULT_SIDE_BORDER_PX

    @property
    def horizontal(self) -> int:
        return max(0, self.left) + max(0, self.right)

    @property
    def vertical(self) -> int:
        return max(0, self.top) + max(0, self.bottom)


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


def compute_initial_window_rect(
    available_screen: Rect,
    *,
    fill_ratio: float = DEFAULT_SCREEN_FILL_RATIO,
    margins: FrameMargins | None = None,
) -> Rect:
    """Compute a comfortable centered client Rect that fits strictly inside `available_screen`."""
    m = margins if margins is not None else FrameMargins()
    max_client_w = max(MIN_WINDOW_WIDTH, available_screen.width - m.horizontal)
    max_client_h = max(MIN_WINDOW_HEIGHT, available_screen.height - m.vertical)

    target_w = min(max_client_w, max(MIN_WINDOW_WIDTH, int(available_screen.width * fill_ratio)))
    target_h = min(max_client_h, max(MIN_WINDOW_HEIGHT, int(available_screen.height * fill_ratio)))

    client_x = available_screen.x + m.left + max(0, (max_client_w - target_w) // 2)
    client_y = available_screen.y + m.top + max(0, (max_client_h - target_h) // 2)
    return Rect(x=client_x, y=client_y, width=target_w, height=target_h)


def clamp_window_rect(
    saved: Rect,
    screens: list[Rect],
    *,
    margins: FrameMargins | None = None,
) -> Rect:
    """Ensure `saved` (client rect) plus its OS frame fits strictly inside an active screen.

    Prevents both off-screen ghost windows (unplugged monitor) and bottom-of-screen
    overflow underneath the taskbar on HiDPI / smaller laptop displays.
    """
    m = margins if margins is not None else FrameMargins(0, 0, 0, 0)
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

    max_client_w = max(320, target_screen.width - m.horizontal)
    max_client_h = max(240, target_screen.height - m.vertical)
    clamped_w = min(max(MIN_WINDOW_WIDTH, saved.width), max_client_w)
    clamped_h = min(max(MIN_WINDOW_HEIGHT, saved.height), max_client_h)

    min_x = target_screen.x + m.left
    max_x = max(min_x, target_screen.right - m.right - clamped_w)
    min_y = target_screen.y + m.top
    max_y = max(min_y, target_screen.bottom - m.bottom - clamped_h)

    if overlap == 0 or (overlap / saved_area) < 0.25:
        clamped_x = min_x + max(0, (max_client_w - clamped_w) // 2)
        clamped_y = min_y + max(0, (max_client_h - clamped_h) // 2)
    else:
        clamped_x = max(min_x, min(saved.x, max_x))
        clamped_y = max(min_y, min(saved.y, max_y))

    return Rect(x=clamped_x, y=clamped_y, width=clamped_w, height=clamped_h)


def _measure_widget_frame_margins(widget: Any) -> FrameMargins:
    """Measure real OS frame margins once the widget is shown, or fall back to safe defaults."""
    geom = widget.geometry()
    frame = widget.frameGeometry()
    top = frame.top()
    left = frame.left()
    right = frame.right()
    bottom = frame.bottom()
    if frame.width() > geom.width() or frame.height() > geom.height():
        return FrameMargins(
            left=max(0, geom.left() - left),
            top=max(0, geom.top() - top),
            right=max(0, right - geom.right()),
            bottom=max(0, bottom - geom.bottom()),
        )
    return FrameMargins()


def ensure_widget_on_screen(widget: Any, *, use_default_size_if_unset: bool = False) -> None:
    """Clamp a Qt top-level window (including its title bar/frame) onto connected screens."""
    from PySide6.QtGui import QGuiApplication

    if hasattr(widget, "isMaximized") and widget.isMaximized():
        return

    qt_screens = QGuiApplication.screens()
    if not qt_screens:
        return

    screen_rects = []
    for screen in qt_screens:
        avail = screen.availableGeometry()
        screen_rects.append(Rect(avail.x(), avail.y(), avail.width(), avail.height()))

    margins = _measure_widget_frame_margins(widget)
    if use_default_size_if_unset:
        clamped = compute_initial_window_rect(screen_rects[0], margins=margins)
    else:
        geom = widget.geometry()
        clamped = clamp_window_rect(
            Rect(geom.x(), geom.y(), geom.width(), geom.height()),
            screen_rects,
            margins=margins,
        )
    widget.setGeometry(clamped.x, clamped.y, clamped.width, clamped.height)
