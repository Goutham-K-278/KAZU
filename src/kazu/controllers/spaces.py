"""Space & layout controller with Undo-close support and layout-only sync export."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import time

from kazu.domain.layout import (
    LayoutNode,
    PaneNode,
    assign_account_to_pane,
    close_pane,
    default_four_up_layout,
    default_side_by_side_layout,
    default_solo_layout,
    deserialize_layout,
    iter_panes,
    serialize_layout,
    split_pane,
    swap_panes,
)
from kazu.domain.models import Orientation, Space, new_id
from kazu.infra.db import Database

UNDO_WINDOW_SECONDS: float = 5.0
SYNC_EXPORT_VERSION: int = 1
SYNC_FILENAME: str = "kazu-layouts.json"


@dataclass(frozen=True, slots=True)
class ClosedPaneSnapshot:
    """Saved layout state so Ctrl+Shift+T / Undo toast restores the exact slot."""

    space_id: str
    previous_layout_json: str
    closed_account_id: str | None
    closed_at: float


class SpaceController:
    """Manages Spaces, layout mutations, duplicate-account detection, and Undo."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._undo_stack: list[ClosedPaneSnapshot] = []

    def ensure_default_space(self) -> Space:
        """Guarantee at least one Space exists on startup."""
        spaces = self._db.list_spaces()
        if spaces:
            return spaces[0]
        return self.create_space("Workspace", layout=default_side_by_side_layout())

    def list_spaces(self) -> list[Space]:
        return self._db.list_spaces()

    def get_space(self, space_id: str) -> Space | None:
        return self._db.get_space(space_id)

    def create_space(self, name: str, layout: LayoutNode | None = None) -> Space:
        spaces = self._db.list_spaces()
        tree = layout if layout is not None else default_side_by_side_layout()
        space = Space(
            id=new_id(),
            name=name.strip() or f"Space {len(spaces) + 1}",
            order_index=len(spaces),
            layout_json=serialize_layout(tree),
        )
        self._db.upsert_space(space)
        return space

    def create_space_from_preset(self, name: str, preset_kind: str) -> Space:
        """Create a Space using 'solo', 'side_by_side', or 'four_up' preset."""
        if preset_kind == "solo":
            layout = default_solo_layout()
        elif preset_kind == "four_up":
            layout = default_four_up_layout()
        else:
            layout = default_side_by_side_layout()
        return self.create_space(name=name, layout=layout)

    def rename_space(self, space_id: str, new_name: str) -> Space | None:
        space = self._db.get_space(space_id)
        if space is None:
            return None
        cleaned = new_name.strip()
        if not cleaned:
            return space
        space.name = cleaned
        self._db.upsert_space(space)
        return space

    def delete_space(self, space_id: str) -> bool:
        spaces = self._db.list_spaces()
        if len(spaces) <= 1:
            return False  # Never leave the user with zero Spaces.
        self._db.delete_space(space_id)
        remaining = [s.id for s in spaces if s.id != space_id]
        self._db.reorder_spaces(remaining)
        return True

    def reorder_spaces(self, ordered_ids: list[str]) -> None:
        self._db.reorder_spaces(ordered_ids)

    def get_layout(self, space_id: str) -> LayoutNode:
        space = self._db.get_space(space_id)
        if space is None:
            return default_solo_layout()
        return deserialize_layout(space.layout_json)

    def save_layout(self, space_id: str, root: LayoutNode) -> Space | None:
        space = self._db.get_space(space_id)
        if space is None:
            return None
        space.layout_json = serialize_layout(root)
        self._db.upsert_space(space)
        return space

    def split_pane_in_space(
        self,
        space_id: str,
        pane_id: str,
        orientation: Orientation,
        new_account_id: str | None = None,
    ) -> PaneNode | None:
        root = self.get_layout(space_id)
        updated, created = split_pane(root, pane_id, orientation, new_account_id)
        if created is None:
            return None
        self.save_layout(space_id, updated)
        return created

    def close_pane_in_space(
        self,
        space_id: str,
        pane_id: str,
        now: float | None = None,
    ) -> ClosedPaneSnapshot | None:
        """Close a pane and push an Undo snapshot so Ctrl+Shift+T restores it."""
        space = self._db.get_space(space_id)
        if space is None:
            return None

        root = deserialize_layout(space.layout_json)
        target_account: str | None = None
        for pane in iter_panes(root):
            if pane.pane_id == pane_id:
                target_account = pane.account_id
                break

        updated, removed = close_pane(root, pane_id)
        if not removed:
            return None

        snapshot = ClosedPaneSnapshot(
            space_id=space_id,
            previous_layout_json=space.layout_json,
            closed_account_id=target_account,
            closed_at=now if now is not None else time.monotonic(),
        )
        self._undo_stack.append(snapshot)
        self.save_layout(space_id, updated)
        return snapshot

    def undo_last_close(self, now: float | None = None) -> ClosedPaneSnapshot | None:
        """Restore the most recently closed pane if still available."""
        if not self._undo_stack:
            return None
        snapshot = self._undo_stack.pop()
        space = self._db.get_space(snapshot.space_id)
        if space is None:
            return None
        space.layout_json = snapshot.previous_layout_json
        self._db.upsert_space(space)
        return snapshot

    def assign_account(self, space_id: str, pane_id: str, account_id: str | None) -> bool:
        root = self.get_layout(space_id)
        if not assign_account_to_pane(root, pane_id, account_id):
            return False
        self.save_layout(space_id, root)
        return True

    def swap_panes_in_space(self, space_id: str, pane_a_id: str, pane_b_id: str) -> bool:
        root = self.get_layout(space_id)
        if not swap_panes(root, pane_a_id, pane_b_id):
            return False
        self.save_layout(space_id, root)
        return True

    def find_open_account_locations(self, account_id: str) -> list[tuple[Space, str]]:
        """Return `(space, pane_id)` pairs where `account_id` is already open (Bug #9)."""
        matches: list[tuple[Space, str]] = []
        for space in self._db.list_spaces():
            root = deserialize_layout(space.layout_json)
            for pane in iter_panes(root):
                if pane.account_id == account_id:
                    matches.append((space, pane.pane_id))
        return matches

    # --- Layout-Only Export / Sync Folder (Problem E4; never touches sessions) ---

    def export_layouts_json(self) -> str:
        """Export Spaces and Account metadata (labels, colors, URLs) — never cookies."""
        accounts = [
            {
                "id": a.id,
                "label": a.label,
                "provider_key": a.provider_key,
                "home_url": a.home_url,
                "engine": a.engine.value,
                "color": a.color,
                "zoom": a.zoom,
                "keep_alive": a.keep_alive,
            }
            for a in self._db.list_accounts()
        ]
        spaces = [
            {
                "id": s.id,
                "name": s.name,
                "order_index": s.order_index,
                "layout": json.loads(s.layout_json),
            }
            for s in self._db.list_spaces()
        ]
        payload = {"v": SYNC_EXPORT_VERSION, "accounts": accounts, "spaces": spaces}
        return json.dumps(payload, indent=2)

    def write_sync_folder(self, sync_folder: Path) -> Path:
        """Atomically write layouts JSON to a user's Sync Folder with .bak backup."""
        sync_folder.mkdir(parents=True, exist_ok=True)
        target = sync_folder / SYNC_FILENAME
        backup = sync_folder / f"{SYNC_FILENAME}.bak"
        temp = sync_folder / f"{SYNC_FILENAME}.tmp"

        data = self.export_layouts_json()
        temp.write_text(data, encoding="utf-8")
        if target.exists():
            shutil.copy2(target, backup)
        temp.replace(target)
        return target
