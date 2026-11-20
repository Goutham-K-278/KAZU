"""Centered, domain-locked OAuth popup dialog (Bug #10 fix)."""

from __future__ import annotations

from urllib.parse import urlparse

from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

MIN_OAUTH_WIDTH: int = 520
MIN_OAUTH_HEIGHT: int = 680


class OAuthPopup(QDialog):
    """Modal popup hosting an OAuth web view with a read-only domain lock header."""

    def __init__(self, web_view: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in")
        self.setMinimumSize(MIN_OAUTH_WIDTH, MIN_OAUTH_HEIGHT)
        self.resize(MIN_OAUTH_WIDTH, MIN_OAUTH_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._url_label = QLabel("Connecting securely...")
        self._url_label.setObjectName("MutedLabel")
        self._url_label.setStyleSheet("padding: 6px 10px;")
        layout.addWidget(self._url_label)
        layout.addWidget(web_view, stretch=1)

    def set_display_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        prefix = "🔒 " if parsed.scheme == "https" else ""
        self._url_label.setText(f"{prefix}{host}" if host else "Connecting...")
