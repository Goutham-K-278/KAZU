"""Companion Mode backend (BrowserAppEngine — Problems A1, A2, A6).

Launches the user's real installed Chrome, Edge, or Brave in bar-free App Mode
with an isolated per-account --user-data-dir folder. Never uses shell=True and
never spoofs user agents.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any

from kazu.controllers.lifecycle import LifecycleTier
from kazu.domain.models import Account
from kazu.infra.paths import AppPaths

logger = logging.getLogger("kazu.companion")

_WINDOWS_CANDIDATES: tuple[str, ...] = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
)

_MACOS_CANDIDATES: tuple[str, ...] = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
)

_LINUX_BINARIES: tuple[str, ...] = (
    "google-chrome",
    "google-chrome-stable",
    "microsoft-edge",
    "brave-browser",
    "chromium",
    "chromium-browser",
)


@dataclass(frozen=True, slots=True)
class DetectedBrowser:
    """Path and display name of an installed Chromium-based Companion browser."""

    name: str
    executable: Path


def detect_companion_browser() -> DetectedBrowser | None:
    """Locate an installed Chrome, Edge, or Brave executable on the current OS."""
    system = platform.system()
    if system == "Windows":
        for raw in _WINDOWS_CANDIDATES:
            candidate = Path(raw)
            if candidate.exists():
                return DetectedBrowser(name=candidate.stem, executable=candidate)
    elif system == "Darwin":
        for raw in _MACOS_CANDIDATES:
            candidate = Path(raw)
            if candidate.exists():
                return DetectedBrowser(name=candidate.name, executable=candidate)
    else:
        for binary in _LINUX_BINARIES:
            found = shutil.which(binary)
            if found:
                return DetectedBrowser(name=binary, executable=Path(found))
    return None


def build_companion_command(
    browser: DetectedBrowser,
    account: Account,
    profile_dir: Path,
) -> list[str]:
    """Construct safe list-arg command for isolated bar-free App Mode launch."""
    return [
        str(browser.executable),
        f"--app={account.home_url}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]


class BrowserAppEngine:
    """Launches and tracks isolated Companion browser windows per account."""

    def __init__(self, paths: AppPaths) -> None:
        self._paths = paths
        self._processes: dict[str, subprocess.Popen[bytes]] = {}

    def is_wayland(self) -> bool:
        return bool(os.environ.get("WAYLAND_DISPLAY"))

    def launch(self, account: Account) -> tuple[bool, str]:
        """Launch `account` in an isolated real browser App Mode window.

        Returns `(success, status_message)`.
        """
        browser = detect_companion_browser()
        if browser is None:
            return (
                False,
                "No Chrome, Edge, or Brave installation was found for Companion Mode.",
            )

        profile_dir = self._paths.companion_profile(account.id)
        cmd = build_companion_command(browser, account, profile_dir)
        try:
            proc = subprocess.Popen(  # noqa: S603
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._processes[account.id] = proc
            logger.info("Launched Companion browser for account %s", account.id)
            if self.is_wayland():
                return (
                    True,
                    f"Opened in {browser.name} (isolated window; Wayland does not auto-tile).",
                )
            return True, f"Opened in {browser.name} Companion Mode."
        except OSError as exc:
            logger.warning("Companion launch failed for account %s: %s", account.id, exc)
            return False, f"Could not launch {browser.name}: {exc}"

    def is_running(self, account_id: str) -> bool:
        proc = self._processes.get(account_id)
        return proc is not None and proc.poll() is None

    def create_pane_widget(
        self,
        account: Account,
        on_switch_embedded: Any = None,
    ) -> Any:
        """Build a calm Companion control card inside Kazu's pane slot."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        title = QLabel(f"{account.label} — Companion Mode")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(
            "Runs in your real browser with its own isolated profile so Google Sign-In "
            "and passkeys work natively."
        )
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        status_label = QLabel("")
        status_label.setObjectName("MutedLabel")
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        launch_btn = QPushButton("Launch / Focus Companion Window")
        launch_btn.setObjectName("PrimaryButton")

        def _on_launch() -> None:
            _ok, message = self.launch(account)
            status_label.setText(message)

        launch_btn.clicked.connect(_on_launch)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(launch_btn)
        if on_switch_embedded is not None:
            switch_btn = QPushButton("Switch to Embedded Pane")
            switch_btn.clicked.connect(on_switch_embedded)
            layout.addWidget(switch_btn)
        layout.addWidget(status_label)
        return card

    def set_lifecycle_tier(self, _tier: LifecycleTier) -> None:
        """Companion windows manage their own browser lifecycle."""
