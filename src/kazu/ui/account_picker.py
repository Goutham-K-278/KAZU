"""Empty-pane provider & existing-account picker (scroll-safe + duplicate-account guard)."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urlparse

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from kazu.domain.models import Account, Space
from kazu.domain.providers import ProviderPreset


class AccountPicker(QFrame):
    """Shown inside an empty pane inside a frameless scroll area so it never expands MainWindow."""

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
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumSize(0, 0)

        container = QWidget()
        layout = QVBoxLayout(container)
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

        layout.addLayout(self._build_provider_grid(presets))
        layout.addLayout(self._build_custom_url_row())

        self._url_error = QLabel("")
        self._url_error.setStyleSheet("color: #F87171; font-size: 12px;")
        self._url_error.hide()
        layout.addWidget(self._url_error)

        if existing_accounts:
            self._append_existing_accounts(layout, existing_accounts)

        scroll.setWidget(container)
        outer.addWidget(scroll)

    def _build_provider_grid(self, presets: list[ProviderPreset]) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(8)
        row, col = 0, 0
        for preset in presets:
            if preset.key == "custom":
                continue
            label = f"{preset.name}\n({preset.badge_hint})" if preset.badge_hint else preset.name
            btn = QPushButton(label)
            btn.setMinimumHeight(46)
            btn.clicked.connect(
                lambda _=False, key=preset.key: self._on_pick_new_provider(key, None)
            )
            grid.addWidget(btn, row, col)
            col += 1
            if col >= 3:
                col = 0
                row += 1
        return grid

    def _build_custom_url_row(self) -> QHBoxLayout:
        custom_row = QHBoxLayout()
        self._custom_url = QLineEdit()
        self._custom_url.setPlaceholderText(
            "Or enter any URL (e.g. https://notion.so, http://localhost:3000)"
        )
        self._custom_url.returnPressed.connect(self._handle_custom_url)
        add_custom_btn = QPushButton("Open URL")
        add_custom_btn.clicked.connect(self._handle_custom_url)
        custom_row.addWidget(self._custom_url, stretch=1)
        custom_row.addWidget(add_custom_btn)
        return custom_row

    def _append_existing_accounts(
        self,
        layout: QVBoxLayout,
        existing_accounts: list[Account],
    ) -> None:
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
        parsed = urlparse(raw)
        if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
            self._url_error.setText("Please enter a valid website URL (e.g. https://example.com).")
            self._url_error.show()
            return
        self._url_error.hide()
        self._on_pick_new_provider("custom", raw)

    def _handle_existing(self, account: Account, already_open: bool) -> None:
        if not already_open:
            self._on_pick_existing_account(account.id, False)
            return

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
