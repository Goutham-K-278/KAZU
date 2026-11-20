"""Bounded in-memory snapshot cache for discarded panes.

Stores lightweight PNG bytes captured right before a pane transitions to
Discarded so returning to that Space shows the last frame with a soft
'Waking up...' badge instead of a blank screen.
"""

from __future__ import annotations

from collections import OrderedDict

DEFAULT_MAX_SNAPSHOTS: int = 24
MAX_SNAPSHOT_BYTES: int = 4 * 1024 * 1024  # 4 MB safety cap per snapshot


class SnapshotCache:
    """LRU-bounded cache mapping pane_id -> PNG bytes."""

    def __init__(self, max_entries: int = DEFAULT_MAX_SNAPSHOTS) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[str, bytes] = OrderedDict()

    def put(self, pane_id: str, png_bytes: bytes) -> bool:
        """Store snapshot bytes for a pane. Returns False if oversized or empty."""
        if not png_bytes or len(png_bytes) > MAX_SNAPSHOT_BYTES:
            return False
        if pane_id in self._entries:
            self._entries.move_to_end(pane_id)
        self._entries[pane_id] = png_bytes
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return True

    def get(self, pane_id: str) -> bytes | None:
        """Retrieve cached PNG bytes for a pane, refreshing LRU recency."""
        data = self._entries.get(pane_id)
        if data is not None:
            self._entries.move_to_end(pane_id)
        return data

    def remove(self, pane_id: str) -> None:
        """Remove a pane's cached snapshot."""
        self._entries.pop(pane_id, None)

    def clear(self) -> None:
        """Evict all cached snapshots."""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
