"""Centered, screen-clamped, domain-locked OAuth popup dialog (Bug #10 + Scaling Fix)."""

from __future__ import annotations

from urllib.parse import urlparse

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QLabel, QSizePolicy, QVBoxLayout, QWidget

PREFERRED_OAUTH_WIDTH: int = 520
PREFERRED_OAUTH_HEIGHT: int = 680
SCREEN_MARGIN_X: int = 40
SCREEN_MARGIN_Y: int = 80


class OAuthPopup(QDialog):
    """Modal popup hosting an OAuth web view with a read-only domain lock header.

    Automatically clamps its size to the active screen's available geometry so
    the Allow/Continue button at the bottom is never cut off on 768p/HiDPI laptops.
    """

    def __init__(self, web_view: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in")

        screen = (
            parent.screen()
            if (parent is not None and hasattr(parent, "screen") and parent.screen() is not None)
            else QGuiApplication.primaryScreen()
        )
        if screen is not None:
            avail = screen.availableGeometry()
            width = min(PREFERRED_OAUTH_WIDTH, max(360, avail.width() - SCREEN_MARGIN_X))
            height = min(PREFERRED_OAUTH_HEIGHT, max(420, avail.height() - SCREEN_MARGIN_Y))
            self.setMinimumSize(min(420, width), min(460, height))
            self.resize(width, height)
            x = avail.x() + max(0, (avail.width() - width) // 2)
            y = avail.y() + max(0, (avail.height() - height) // 2)
            self.move(x, y)
        else:
            self.setMinimumSize(420, 480)
            self.resize(PREFERRED_OAUTH_WIDTH, PREFERRED_OAUTH_HEIGHT)

        web_view.setMinimumSize(0, 0)
        web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

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
