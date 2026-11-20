"""Auto-fit zoom service for keeping desktop layouts intact in narrow panes (Problem E3)."""

from __future__ import annotations

from dataclasses import dataclass

from kazu.domain.models import ZoomMode

MIN_AUTOFIT_ZOOM: float = 0.67
MAX_AUTOFIT_ZOOM: float = 1.0


@dataclass(frozen=True, slots=True)
class AutoFitResult:
    """Computed zoom factor and optional gentle suggestion to split into a new Space."""

    zoom: float
    suggest_new_space: bool


class AutoFitZoomService:
    """Computes zoom = clamp(pane_width / target_css_width, 0.67, 1.0)."""

    def compute(
        self,
        pane_width_px: int,
        target_css_width: int,
        mode: ZoomMode = ZoomMode.FIT_DESKTOP,
        manual_zoom: float = 1.0,
    ) -> AutoFitResult:
        if mode == ZoomMode.NATIVE_NARROW or pane_width_px <= 0 or target_css_width <= 0:
            return AutoFitResult(zoom=round(manual_zoom, 3), suggest_new_space=False)

        raw_ratio = pane_width_px / float(target_css_width)
        suggest_new_space = raw_ratio < MIN_AUTOFIT_ZOOM
        clamped = max(MIN_AUTOFIT_ZOOM, min(MAX_AUTOFIT_ZOOM, raw_ratio))
        return AutoFitResult(zoom=round(clamped, 3), suggest_new_space=suggest_new_space)
