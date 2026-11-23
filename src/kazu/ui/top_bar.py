"""Top bar: Space tabs with delete button, double-click rename, New Space, Palette, and Settings."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QPushButton,
    QWidget,
)

from kazu.domain.models import Space


class _SpaceTabButton(QPushButton):
    """Space tab button with clean double-click rename handling."""

    def __init__(
        self,
        text: str,
        on_double_click: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._on_double_click = on_double_click

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        event.accept()
        self._on_double_click()


class TopBar(QFrame):
    """Minimal Space-tab bar with calm activity dots, delete cross buttons, and quick actions."""

    def __init__(
        self,
        on_select_space: Callable[[str], None],
        on_delete_space: Callable[[str], None],
        on_new_space: Callable[[], None],
        on_open_palette: Callable[[], None],
        on_open_settings: Callable[[], None],
        on_rename_space: Callable[[str, str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self._on_select_space = on_select_space
        self._on_delete_space = on_delete_space
        self._on_rename_space = on_rename_space
        self._tab_groups: dict[str, QFrame] = {}
        self._last_render_key: tuple[tuple[tuple[str, str], ...], str, frozenset[str]] | None = None

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 0, 8, 0)
        self._layout.setSpacing(4)

        self._tabs_layout = QHBoxLayout()
        self._tabs_layout.setSpacing(4)
        self._layout.addLayout(self._tabs_layout)

        new_btn = QPushButton("＋")
        new_btn.setAccessibleName("New Space")
        new_btn.setToolTip("New Space (Ctrl+T)")
        new_btn.clicked.connect(on_new_space)
        self._layout.addWidget(new_btn)

        self._layout.addStretch(1)

        palette_btn = QPushButton("⌘K")
        palette_btn.setAccessibleName("Command Palette")
        palette_btn.setToolTip("Command Palette (Ctrl+K)")
        palette_btn.clicked.connect(on_open_palette)
        self._layout.addWidget(palette_btn)

        settings_btn = QPushButton("⚙")
        settings_btn.setAccessibleName("Settings")
        settings_btn.setToolTip("Settings (Ctrl+,)")
        settings_btn.clicked.connect(on_open_settings)
        self._layout.addWidget(settings_btn)

    def render_spaces(
        self,
        spaces: list[Space],
        active_space_id: str,
        unread_space_ids: set[str] | None = None,
    ) -> None:
        unread_frozen = frozenset(unread_space_ids or ())
        render_key = (
            tuple((s.id, s.name) for s in spaces),
            active_space_id,
            unread_frozen,
        )
        if render_key == self._last_render_key:
            return
        self._last_render_key = render_key

        while self._tabs_layout.count():
            item = self._tabs_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        self._tab_groups.clear()

        can_delete = len(spaces) > 1

        for space in spaces:
            is_active = space.id == active_space_id
            dot = "● " if is_active else ("• " if space.id in unread_frozen else "○ ")

            group = QFrame()
            group.setObjectName("SpaceTabGroup")
            group.setProperty("active", "true" if is_active else "false")
            group_layout = QHBoxLayout(group)
            group_layout.setContentsMargins(2, 2, 4, 2)
            group_layout.setSpacing(2)

            tab_btn = _SpaceTabButton(
                f"{dot}{space.name}",
                on_double_click=lambda sid=space.id, sname=space.name: self._handle_rename(
                    sid, sname
                ),
            )
            tab_btn.setObjectName("SpaceTab")
            tab_btn.setProperty("active", "true" if is_active else "false")
            tab_btn.setToolTip("Double-click to rename")
            tab_btn.clicked.connect(lambda _=False, sid=space.id: self._on_select_space(sid))
            group_layout.addWidget(tab_btn)

            if can_delete:
                close_btn = QPushButton("×")
                close_btn.setObjectName("SpaceCloseBtn")
                close_btn.setAccessibleName(f"Delete Space {space.name}")
                close_btn.setToolTip(f"Delete Space '{space.name}'")
                close_btn.setFixedSize(20, 20)
                close_btn.clicked.connect(
                    lambda _=False, sid=space.id: self._on_delete_space(sid)
                )
                group_layout.addWidget(close_btn)

            self._tabs_layout.addWidget(group)
            self._tab_groups[space.id] = group

    def _handle_rename(self, space_id: str, current_name: str) -> None:
        """Prompt the user inline for a new Space name."""
        if self._on_rename_space is None:
            return
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Space",
            "Enter a new name for this workspace:",
            text=current_name,
        )
        if ok and new_name.strip():
            self._on_rename_space(space_id, new_name.strip())
