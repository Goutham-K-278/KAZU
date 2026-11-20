"""4-tier activity-aware pane lifecycle service (Problems C1 & C2).

Tiers:
  LIVE          -> Pane is in the currently visible Space.
  HIDDEN_ACTIVE -> Space hidden < freeze_after_s OR recent activity (Activity Guard).
  FROZEN        -> Hidden >= freeze_after_s and idle; ~0% CPU, instant resume.
  DISCARDED     -> Hidden >= discard_after_s and idle; frees renderer, snapshot shown on wake.

Pinned ('Keep Running') panes never transition past HIDDEN_ACTIVE.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum


class LifecycleTier(StrEnum):
    """Four-tier lifecycle state for an embedded pane."""

    LIVE = "live"
    HIDDEN_ACTIVE = "hidden_active"
    FROZEN = "frozen"
    DISCARDED = "discarded"


@dataclass(slots=True)
class PaneLifecycleRecord:
    """Tracked runtime state for one pane."""

    pane_id: str
    space_id: str
    tier: LifecycleTier = LifecycleTier.LIVE
    keep_running: bool = False
    hidden_since: float | None = None
    last_activity_at: float = 0.0
    has_unread_activity: bool = False
    recommended_allows_freeze: bool = True


class TieredLifecycleService:
    """Pure state-machine governing pane freezing, discarding, and activity dots."""

    def __init__(
        self,
        freeze_after_seconds: float = 600.0,
        discard_after_seconds: float = 1800.0,
    ) -> None:
        self._freeze_after_s = max(30.0, float(freeze_after_seconds))
        self._discard_after_s = max(self._freeze_after_s + 30.0, float(discard_after_seconds))
        self._records: dict[str, PaneLifecycleRecord] = {}

    def register_pane(
        self,
        pane_id: str,
        space_id: str,
        *,
        visible: bool = True,
        keep_running: bool = False,
        now: float | None = None,
    ) -> PaneLifecycleRecord:
        ts = now if now is not None else time.monotonic()
        record = PaneLifecycleRecord(
            pane_id=pane_id,
            space_id=space_id,
            tier=LifecycleTier.LIVE if visible else LifecycleTier.HIDDEN_ACTIVE,
            keep_running=keep_running,
            hidden_since=None if visible else ts,
            last_activity_at=ts,
        )
        self._records[pane_id] = record
        return record

    def unregister_pane(self, pane_id: str) -> None:
        self._records.pop(pane_id, None)

    def get_record(self, pane_id: str) -> PaneLifecycleRecord | None:
        return self._records.get(pane_id)

    def set_keep_running(self, pane_id: str, keep_running: bool, now: float | None = None) -> None:
        record = self._records.get(pane_id)
        if record is None:
            return
        record.keep_running = keep_running
        if keep_running:
            ts = now if now is not None else time.monotonic()
            record.last_activity_at = ts
            if record.tier in (LifecycleTier.FROZEN, LifecycleTier.DISCARDED):
                record.tier = LifecycleTier.HIDDEN_ACTIVE

    def set_recommended_allows_freeze(self, pane_id: str, allowed: bool) -> None:
        """Mirror Qt's QWebEnginePage.recommendedState guidance."""
        record = self._records.get(pane_id)
        if record is not None:
            record.recommended_allows_freeze = allowed

    def record_activity(self, pane_id: str, now: float | None = None) -> bool:
        """Activity Guard: reset idle countdown on title/audio/notification change.

        Returns True if the pane is in a hidden Space (so the Space tab should
        display its calm Activity Dot).
        """
        record = self._records.get(pane_id)
        if record is None:
            return False
        ts = now if now is not None else time.monotonic()
        record.last_activity_at = ts
        if record.tier != LifecycleTier.LIVE:
            record.has_unread_activity = True
            return True
        return False

    def activate_space(self, active_space_id: str, now: float | None = None) -> list[str]:
        """Switch visible Space. Returns pane_ids that were DISCARDED and need snapshot wake."""
        ts = now if now is not None else time.monotonic()
        waking_from_discarded: list[str] = []

        for record in self._records.values():
            if record.space_id == active_space_id:
                if record.tier == LifecycleTier.DISCARDED:
                    waking_from_discarded.append(record.pane_id)
                record.tier = LifecycleTier.LIVE
                record.hidden_since = None
                record.last_activity_at = ts
                record.has_unread_activity = False
            elif record.tier == LifecycleTier.LIVE:
                record.tier = LifecycleTier.HIDDEN_ACTIVE
                record.hidden_since = ts
        return waking_from_discarded

    def evaluate_transitions(self, now: float | None = None) -> dict[str, LifecycleTier]:
        """Compute due tier transitions for all hidden panes.

        Returns a mapping of `pane_id -> new_tier` for panes whose tier changed.
        """
        ts = now if now is not None else time.monotonic()
        transitions: dict[str, LifecycleTier] = {}

        for record in self._records.values():
            if record.tier == LifecycleTier.LIVE or record.keep_running:
                continue

            idle_anchor = max(record.hidden_since or ts, record.last_activity_at)
            idle_seconds = max(0.0, ts - idle_anchor)

            if (
                record.tier == LifecycleTier.HIDDEN_ACTIVE
                and idle_seconds >= self._freeze_after_s
                and record.recommended_allows_freeze
            ):
                record.tier = LifecycleTier.FROZEN
                transitions[record.pane_id] = LifecycleTier.FROZEN
            elif (
                record.tier == LifecycleTier.FROZEN
                and idle_seconds >= self._discard_after_s
            ):
                record.tier = LifecycleTier.DISCARDED
                transitions[record.pane_id] = LifecycleTier.DISCARDED

        return transitions

    def force_hibernate_pane(self, pane_id: str, discard: bool = False) -> LifecycleTier | None:
        """Manually hibernate a hidden pane (or freeze on demand)."""
        record = self._records.get(pane_id)
        if record is None or record.tier == LifecycleTier.LIVE:
            return None
        target = LifecycleTier.DISCARDED if discard else LifecycleTier.FROZEN
        record.tier = target
        return target

    def freeze_other_spaces(self, active_space_id: str) -> dict[str, LifecycleTier]:
        """One-click 'Freeze other Spaces' action when RAM gets high."""
        transitions: dict[str, LifecycleTier] = {}
        for record in self._records.values():
            if record.space_id == active_space_id or record.keep_running:
                continue
            if record.tier == LifecycleTier.HIDDEN_ACTIVE:
                record.tier = LifecycleTier.FROZEN
                transitions[record.pane_id] = LifecycleTier.FROZEN
        return transitions

    def space_has_unread_activity(self, space_id: str) -> bool:
        return any(
            r.space_id == space_id and r.has_unread_activity
            for r in self._records.values()
        )
