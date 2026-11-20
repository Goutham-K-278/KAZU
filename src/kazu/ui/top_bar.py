"""Slim 36px top bar hosting Space tabs (with right-side delete '×'), New Space, Palette, and Settings."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from kazu.domain.models import Space


class TopBar(QFrame):
    """Minimal Space-tab bar with calm activity dots, delete cross buttons, and quick actions."""

    def __init__(
        self,
        on_select_space: Callable[[str], None],
        on_delete_space: Callable[[str], None],
        on_new_space: Callable[[], None],
        on_open_palette: Callable[[], None],
        on_open_settings: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TopBar")
        self._on_select_space = on_select_space
        self._on_delete_space = on_delete_space
        self._tab_groups: dict[str, QFrame] = {}

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
        unread = unread_space_ids or set()
        while self._tabs_layout.count():
            item = self._tabs_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._tab_groups.clear()

        can_delete = len(spaces) > 1

        for space in spaces:
            is_active = space.id == active_space_id
            dot = "● " if is_active else ("• " if space.id in unread else "○ ")

            group = QFrame()
            group.setObjectName("SpaceTabGroup")
            group.setProperty("active", "true" if is_active else "false")
            group_layout = QHBoxLayout(group)
            group_layout.setContentsMargins(2, 2, 4, 2)
            group_layout.setSpacing(2)

            tab_btn = QPushButton(f"{dot}{space.name}")
            tab_btn.setObjectName("SpaceTab")
            tab_btn.setProperty("active", "true" if is_active else "false")
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
