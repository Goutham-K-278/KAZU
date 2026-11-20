"""Calm inline recovery cards for Google sign-in block, renderer crash, and offline state."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class StatusCard(QFrame):
    """Reusable calm centered card for pane-level recovery states."""

    def __init__(
        self,
        title: str,
        body: str,
        actions: list[tuple[str, Callable[[], None], bool]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 600;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        body_lbl = QLabel(body)
        body_lbl.setObjectName("MutedLabel")
        body_lbl.setWordWrap(True)
        body_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title_lbl)
        layout.addWidget(body_lbl)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for label, callback, is_primary in actions:
            btn = QPushButton(label)
            if is_primary:
                btn.setObjectName("PrimaryButton")
            btn.clicked.connect(callback)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)


def build_google_block_card(
    on_use_email: Callable[[], None],
    on_switch_companion: Callable[[], None],
    parent: QWidget | None = None,
) -> StatusCard:
    """BlockDetector card offering zero-dead-end escape hatch (Problem A1)."""
    return StatusCard(
        title="Google doesn't allow sign-in inside apps",
        body=(
            "Sign in using your email / magic link in this pane, or switch this "
            "account to Companion Mode to use your real browser with Google Sign-In."
        ),
        actions=[
            ("Use email login", on_use_email, False),
            ("Switch to Companion", on_switch_companion, True),
        ],
        parent=parent,
    )


def build_crash_card(on_reload: Callable[[], None], parent: QWidget | None = None) -> StatusCard:
    """Single-pane crash recovery card (§8.9)."""
    return StatusCard(
        title="This pane stopped responding",
        body="Other panes are unaffected. Reload to pick up where you left off.",
        actions=[("Reload", on_reload, True)],
        parent=parent,
    )


def build_offline_card(
    host: str,
    on_retry: Callable[[], None],
    parent: QWidget | None = None,
) -> StatusCard:
    """Offline recovery card (§8.9)."""
    return StatusCard(
        title=f"Can't reach {host}",
        body="Check your connection. We'll retry automatically or you can retry now.",
        actions=[("Retry", on_retry, True)],
        parent=parent,
    )
