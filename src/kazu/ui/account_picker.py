"""Empty-pane provider & existing-account picker (with duplicate-account guard, Bug #9)."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kazu.domain.models import Account, Space
from kazu.domain.providers import ProviderPreset


class AccountPicker(QFrame):
    """Shown inside an empty pane so the user can pick a provider or existing account."""

    def __init__(
        self,
        presets: list[ProviderPreset],
        existing_accounts: list[Account],
        open_locations: Callable[[str], list[tuple[Space, str]]],
        on_pick_new_provider: Callable[[str, str | None], None],
        on_pick_existing_account: Callable[[str, bool], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._open_locations = open_locations
        self._on_pick_new_provider = on_pick_new_provider
        self._on_pick_existing_account = on_pick_existing_account

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        heading = QLabel("Choose an AI or website for this pane")
        heading.setStyleSheet("font-size: 16px; font-weight: 600;")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        trust = QLabel(
            "Sign in directly on each provider's website. Your passwords never touch this app."
        )
        trust.setObjectName("MutedLabel")
        trust.setAlignment(Qt.AlignmentFlag.AlignCenter)
        trust.setWordWrap(True)
        layout.addWidget(trust)

        grid = QGridLayout()
        grid.setSpacing(8)
        row, col = 0, 0
        for preset in presets:
            if preset.key == "custom":
                continue
            label = preset.name
            if preset.badge_hint:
                label = f"{preset.name}\n({preset.badge_hint})"
            btn = QPushButton(label)
            btn.setMinimumHeight(46)
            btn.clicked.connect(lambda _=False, key=preset.key: self._on_pick_new_provider(key, None))
            grid.addWidget(btn, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1
        layout.addLayout(grid)

        # Custom URL row (Problem E7: first-class custom URLs)
        custom_row = QHBoxLayout()
        self._custom_url = QLineEdit()
        self._custom_url.setPlaceholderText("Or enter any URL (e.g. https://notion.so, http://localhost:3000)")
        add_custom_btn = QPushButton("Open URL")
        add_custom_btn.clicked.connect(self._handle_custom_url)
        custom_row.addWidget(self._custom_url, stretch=1)
        custom_row.addWidget(add_custom_btn)
        layout.addLayout(custom_row)

        if existing_accounts:
            existing_label = QLabel("Or reuse an existing account:")
            existing_label.setObjectName("MutedLabel")
            layout.addWidget(existing_label)

            for account in existing_accounts:
                locs = self._open_locations(account.id)
                suffix = f" — Open in {locs[0][0].name}" if locs else ""
                btn = QPushButton(f"{account.label}{suffix}")
                btn.clicked.connect(
                    lambda _=False, acc=account, opened=bool(locs): self._handle_existing(acc, opened)
                )
                layout.addWidget(btn)

    def _handle_custom_url(self) -> None:
        raw = self._custom_url.text().strip()
        if not raw:
            return
        if not (raw.startswith("https://") or raw.startswith("http://")):
            raw = f"https://{raw}"
        self._on_pick_new_provider("custom", raw)

    def _handle_existing(self, account: Account, already_open: bool) -> None:
        if not already_open:
            self._on_pick_existing_account(account.id, False)
            return

        # Bug #9: prevent silent duplicate account confusion.
        box = QMessageBox(self)
        box.setWindowTitle("Account already open")
        box.setText(f"{account.label} is already open in another pane.")
        box.setInformativeText("Move it here, or open a second view?")
        move_btn = box.addButton("Move it here", QMessageBox.ButtonRole.AcceptRole)
        second_btn = box.addButton("Open second view", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()

        clicked = box.clickedButton()
        if clicked == move_btn:
            self._on_pick_existing_account(account.id, True)
        elif clicked == second_btn:
            self._on_pick_existing_account(account.id, False)
