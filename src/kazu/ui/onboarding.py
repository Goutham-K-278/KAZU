"""Calm <= 30s skippable onboarding dialog (§8.2)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class OnboardingDialog(QDialog):
    """Welcome screen with trust line and Solo / Side-by-side / Four-up picker."""

    def __init__(self, window_width_px: int = 1280, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to Kazu")
        self.setMinimumWidth(460)
        self.selected_layout: str = "side_by_side"

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel("Welcome to Kazu")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        trust = QLabel(
            "Sign in directly on each provider's website.\n"
            "Your passwords never touch this app."
        )
        trust.setObjectName("MutedLabel")
        trust.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(trust)

        prompt = QLabel("Pick your starting layout:")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(prompt)

        row = QHBoxLayout()
        solo_btn = QPushButton("Solo (1 pane)")
        side_btn = QPushButton("Side by side (2 panes)")
        side_btn.setObjectName("PrimaryButton")
        four_btn = QPushButton("Four-up (2×2)")
        if window_width_px < 1100:
            four_btn.setEnabled(False)
            four_btn.setToolTip("Four-up works best on wider displays.")

        solo_btn.clicked.connect(lambda: self._choose("solo"))
        side_btn.clicked.connect(lambda: self._choose("side_by_side"))
        four_btn.clicked.connect(lambda: self._choose("four_up"))

        row.addWidget(solo_btn)
        row.addWidget(side_btn)
        row.addWidget(four_btn)
        layout.addLayout(row)

        skip_btn = QPushButton("Skip")
        skip_btn.clicked.connect(self.reject)
        layout.addWidget(skip_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _choose(self, preset: str) -> None:
        self.selected_layout = preset
        self.accept()
