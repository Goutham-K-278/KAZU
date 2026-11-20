"""Versioned layout tree model and immutable-friendly tree operations.

Zero Qt imports. Represents a Space's split hierarchy as a tree of SplitNode
and PaneNode objects, serializing safely to/from versioned JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from kazu.domain.models import LAYOUT_SCHEMA_VERSION, Orientation, new_id

MAX_PANES_RECOMMENDED_SMALL: int = 2
MAX_PANES_RECOMMENDED_MEDIUM: int = 3
MAX_PANES_RECOMMENDED_LARGE: int = 4
WINDOW_SMALL_BREAKPOINT_PX: int = 1100
WINDOW_LARGE_BREAKPOINT_PX: int = 1900


@dataclass(slots=True)
class PaneNode:
    """Leaf node displaying one account (or the account picker if account_id is None)."""

    pane_id: str = field(default_factory=new_id)
    account_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "pane",
            "pane_id": self.pane_id,
            "account_id": self.account_id,
        }


@dataclass(slots=True)
class SplitNode:
    """Internal node dividing space between child nodes."""

    orientation: Orientation
    children: list[LayoutNode]
    sizes: list[float]

    def __post_init__(self) -> None:
        if len(self.sizes) != len(self.children) or sum(self.sizes) <= 0:
            self.sizes = equal_sizes(len(self.children))
        else:
            self.sizes = normalize_sizes(self.sizes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "split",
            "orientation": self.orientation.value,
            "sizes": [round(s, 4) for s in self.sizes],
            "children": [child.to_dict() for child in self.children],
        }


LayoutNode = PaneNode | SplitNode


def equal_sizes(count: int) -> list[float]:
    """Return equal normalized split ratios for `count` children."""
    if count <= 0:
        return []
    ratio = 1.0 / count
    return [ratio] * count


def normalize_sizes(sizes: list[float]) -> list[float]:
    """Normalize positive ratios so they sum to 1.0."""
    positive = [max(0.01, float(s)) for s in sizes]
    total = sum(positive)
    if total <= 0:
        return equal_sizes(len(sizes))
    return [value / total for value in positive]


def default_solo_layout(account_id: str | None = None) -> LayoutNode:
    """Create a 1-pane layout."""
    return PaneNode(account_id=account_id)


def default_side_by_side_layout(
    left_account_id: str | None = None,
    right_account_id: str | None = None,
) -> LayoutNode:
    """Create a 2-pane horizontal split layout."""
    return SplitNode(
        orientation=Orientation.HORIZONTAL,
        children=[
            PaneNode(account_id=left_account_id),
            PaneNode(account_id=right_account_id),
        ],
        sizes=[0.5, 0.5],
    )


def default_four_up_layout(account_ids: list[str | None] | None = None) -> LayoutNode:
    """Create a 2x2 grid layout."""
    ids = list(account_ids or []) + [None, None, None, None]
    return SplitNode(
        orientation=Orientation.VERTICAL,
        children=[
            SplitNode(
                orientation=Orientation.HORIZONTAL,
                children=[PaneNode(account_id=ids[0]), PaneNode(account_id=ids[1])],
                sizes=[0.5, 0.5],
            ),
            SplitNode(
                orientation=Orientation.HORIZONTAL,
                children=[PaneNode(account_id=ids[2]), PaneNode(account_id=ids[3])],
                sizes=[0.5, 0.5],
            ),
        ],
        sizes=[0.5, 0.5],
    )


def recommended_max_panes(window_width_px: int) -> int:
    """Return adaptive layout suggestion based on window width (suggestions, not limits)."""
    if window_width_px < WINDOW_SMALL_BREAKPOINT_PX:
        return MAX_PANES_RECOMMENDED_SMALL
    if window_width_px < WINDOW_LARGE_BREAKPOINT_PX:
        return MAX_PANES_RECOMMENDED_MEDIUM
    return MAX_PANES_RECOMMENDED_LARGE


def serialize_layout(root: LayoutNode) -> str:
    """Serialize a layout tree into versioned JSON."""
    payload = {
        "v": LAYOUT_SCHEMA_VERSION,
        "root": root.to_dict(),
    }
    return json.dumps(payload, separators=(",", ":"))


def deserialize_layout(raw_json: str) -> LayoutNode:
    """Deserialize versioned JSON into a LayoutNode.

    Never crashes on bad or corrupted data: falls back to a single empty pane.
    """
    try:
        payload = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return default_solo_layout()

    if not isinstance(payload, dict):
        return default_solo_layout()

    root_data = payload.get("root")
    parsed = _parse_node(root_data)
    return parsed if parsed is not None else default_solo_layout()


def _parse_node(data: Any) -> LayoutNode | None:
    if not isinstance(data, dict):
        return None

    node_type = data.get("type")
    if node_type == "pane":
        raw_pane_id = data.get("pane_id")
        pane_id = str(raw_pane_id) if isinstance(raw_pane_id, str) and raw_pane_id else new_id()
        raw_account = data.get("account_id")
        account_id = str(raw_account) if isinstance(raw_account, str) and raw_account else None
        return PaneNode(pane_id=pane_id, account_id=account_id)

    if node_type == "split":
        raw_orientation = data.get("orientation", Orientation.HORIZONTAL.value)
        try:
            orientation = Orientation(str(raw_orientation))
        except ValueError:
            orientation = Orientation.HORIZONTAL

        raw_children = data.get("children")
        if not isinstance(raw_children, list) or not raw_children:
            return None

        children: list[LayoutNode] = []
        for child_data in raw_children:
            child = _parse_node(child_data)
            if child is not None:
                children.append(child)

        if not children:
            return None
        if len(children) == 1:
            return children[0]

        raw_sizes = data.get("sizes")
        if isinstance(raw_sizes, list) and len(raw_sizes) == len(children):
            try:
                sizes = [float(s) for s in raw_sizes]
            except (TypeError, ValueError):
                sizes = equal_sizes(len(children))
        else:
            sizes = equal_sizes(len(children))

        return SplitNode(orientation=orientation, children=children, sizes=sizes)

    return None


def iter_panes(root: LayoutNode) -> list[PaneNode]:
    """Return all leaf PaneNodes in left-to-right / top-to-bottom order."""
    if isinstance(root, PaneNode):
        return [root]
    result: list[PaneNode] = []
    for child in root.children:
        result.extend(iter_panes(child))
    return result


def find_pane(root: LayoutNode, pane_id: str) -> PaneNode | None:
    """Locate a leaf PaneNode by its pane_id."""
    for pane in iter_panes(root):
        if pane.pane_id == pane_id:
            return pane
    return None


def split_pane(
    root: LayoutNode,
    target_pane_id: str,
    orientation: Orientation,
    new_account_id: str | None = None,
) -> tuple[LayoutNode, PaneNode | None]:
    """Split `target_pane_id` into two panes along `orientation`.

    Returns `(updated_root, newly_created_pane)`. If target is not found,
    returns `(root, None)`.
    """
    created: list[PaneNode] = []

    def _transform(node: LayoutNode) -> LayoutNode:
        if isinstance(node, PaneNode):
            if node.pane_id != target_pane_id:
                return node
            new_pane = PaneNode(account_id=new_account_id)
            created.append(new_pane)
            return SplitNode(
                orientation=orientation,
                children=[node, new_pane],
                sizes=[0.5, 0.5],
            )
        new_children = [_transform(child) for child in node.children]
        return SplitNode(  # noqa: E501
            orientation=node.orientation, children=new_children, sizes=list(node.sizes)
        )

    updated = _transform(root)
    return updated, (created[0] if created else None)


def close_pane(root: LayoutNode, target_pane_id: str) -> tuple[LayoutNode, bool]:
    """Remove `target_pane_id` from the layout tree and collapse single-child splits.

    If the last remaining pane is closed, resets it to a single empty pane so a
    Space is never left without a pane.
    """
    if isinstance(root, PaneNode):
        if root.pane_id == target_pane_id:
            return default_solo_layout(), True
        return root, False

    removed = False

    def _prune(node: LayoutNode) -> LayoutNode | None:
        nonlocal removed
        if isinstance(node, PaneNode):
            if node.pane_id == target_pane_id:
                removed = True
                return None
            return node

        kept_children: list[LayoutNode] = []
        kept_sizes: list[float] = []
        for child, size in zip(node.children, node.sizes, strict=True):
            pruned = _prune(child)
            if pruned is not None:
                kept_children.append(pruned)
                kept_sizes.append(size)

        if not kept_children:
            return None
        if len(kept_children) == 1:
            return kept_children[0]
        return SplitNode(
            orientation=node.orientation,
            children=kept_children,
            sizes=normalize_sizes(kept_sizes),
        )

    result = _prune(root)
    return (result if result is not None else default_solo_layout()), removed


def assign_account_to_pane(
    root: LayoutNode,
    target_pane_id: str,
    account_id: str | None,
) -> bool:
    """Assign (or clear) an account_id on a pane in place. Returns True if found."""
    pane = find_pane(root, target_pane_id)
    if pane is None:
        return False
    pane.account_id = account_id
    return True


def swap_panes(root: LayoutNode, pane_a_id: str, pane_b_id: str) -> bool:
    """Swap the assigned accounts of two panes. Returns True if both exist."""
    pane_a = find_pane(root, pane_a_id)
    pane_b = find_pane(root, pane_b_id)
    if pane_a is None or pane_b is None:
        return False
    pane_a.account_id, pane_b.account_id = pane_b.account_id, pane_a.account_id
    return True


def clear_account_references(root: LayoutNode, account_id: str) -> int:
    """Clear all pane references to a deleted account. Returns count cleared."""
    cleared = 0
    for pane in iter_panes(root):
        if pane.account_id == account_id:
            pane.account_id = None
            cleared += 1
    return cleared
