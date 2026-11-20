"""SpaceStack builds nested QSplitter trees from LayoutNode and guards divider drags."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QSplitter, QStackedWidget, QWidget

from kazu.domain.layout import LayoutNode, PaneNode, SplitNode, iter_panes, normalize_sizes
from kazu.domain.models import Orientation
from kazu.ui.pane_frame import PaneFrame
from kazu.ui.splitter_shield import SplitterDragShield

DEBOUNCE_PERSIST_MS: int = 500


class SpaceStack(QStackedWidget):
    """Holds one widget tree per Space with debounced splitter persistence."""

    def __init__(
        self,
        on_layout_resized: Callable[[str, LayoutNode], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_layout_resized = on_layout_resized
        self._space_widgets: dict[str, QWidget] = {}
        self._space_trees: dict[str, LayoutNode] = {}
        self._panes: dict[str, PaneFrame] = {}
        self._shield = SplitterDragShield(self)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._flush_pending_resize)
        self._pending_space_id: str | None = None

    def set_space_tree(
        self,
        space_id: str,
        root: LayoutNode,
        pane_builder: Callable[[PaneNode], PaneFrame],
    ) -> None:
        """Build or rebuild the QSplitter widget tree for `space_id`."""
        self.remove_space(space_id)

        self._space_trees[space_id] = root
        widget = self._build_node(space_id, root, pane_builder)
        self._space_widgets[space_id] = widget
        self.addWidget(widget)
        self.setCurrentWidget(widget)

    def remove_space(self, space_id: str) -> list[str]:
        """Dispose all panes belonging to `space_id` and remove its widget from the stack.

        Returns the list of disposed pane_ids so callers can unregister them from
        TieredLifecycleService and SnapshotCache.
        """
        disposed_ids: list[str] = []
        old_tree = self._space_trees.pop(space_id, None)
        if old_tree is not None:
            for pane_node in iter_panes(old_tree):
                frame = self._panes.pop(pane_node.pane_id, None)
                if frame is not None:
                    frame.dispose()
                disposed_ids.append(pane_node.pane_id)

        old_widget = self._space_widgets.pop(space_id, None)
        if old_widget is not None:
            self.removeWidget(old_widget)
            old_widget.deleteLater()

        if self._pending_space_id == space_id:
            self._pending_space_id = None
        return disposed_ids

    def show_space(self, space_id: str) -> bool:
        widget = self._space_widgets.get(space_id)
        if widget is None:
            return False
        self.setCurrentWidget(widget)
        return True

    def get_pane(self, pane_id: str) -> PaneFrame | None:
        return self._panes.get(pane_id)

    def all_panes(self) -> list[PaneFrame]:
        return list(self._panes.values())

    def dispose_all_panes(self) -> None:
        for pane in list(self._panes.values()):
            pane.dispose()
        self._panes.clear()

    def _build_node(
        self,
        space_id: str,
        node: LayoutNode,
        pane_builder: Callable[[PaneNode], PaneFrame],
    ) -> QWidget:
        if isinstance(node, PaneNode):
            frame = pane_builder(node)
            self._panes[node.pane_id] = frame
            return frame

        qt_orient = (
            Qt.Orientation.Horizontal
            if node.orientation == Orientation.HORIZONTAL
            else Qt.Orientation.Vertical
        )
        splitter = QSplitter(qt_orient)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)

        for child in node.children:
            splitter.addWidget(self._build_node(space_id, child, pane_builder))

        pixel_sizes = [max(100, int(ratio * 1000)) for ratio in node.sizes]
        splitter.setSizes(pixel_sizes)
        splitter.splitterMoved.connect(
            lambda _pos, _idx, sp=splitter, sn=node, sid=space_id: self._record_splitter_move(
                sid, sn, sp
            )
        )
        self._shield.attach_to_splitter(splitter)
        return splitter

    def _record_splitter_move(self, space_id: str, node: SplitNode, splitter: QSplitter) -> None:
        sizes = splitter.sizes()
        if sizes and sum(sizes) > 0:
            node.sizes = normalize_sizes([float(s) for s in sizes])
            self._pending_space_id = space_id
            self._debounce_timer.start(DEBOUNCE_PERSIST_MS)

    def _flush_pending_resize(self) -> None:
        if self._pending_space_id is None:
            return
        sid = self._pending_space_id
        self._pending_space_id = None
        tree = self._space_trees.get(sid)
        if tree is not None:
            self._on_layout_resized(sid, tree)
