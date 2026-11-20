"""Phase 0 Hardware Verification Spike (T1–T14).

Run on real hardware with PySide6 + PySide6-WebEngine installed:
    uv run python scripts/phase0_spike.py

Creates two isolated persistent profiles side by side (no white flash in dark
mode, smooth splitter shield, recursive RAM readout, and a button to test
Companion Mode launch) so you can execute T1–T14 and fill docs/phase0-findings.md.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from kazu.domain.models import Account, EngineKind
from kazu.infra.memory import MemoryMonitor
from kazu.infra.paths import AppPaths
from kazu.infra.shutdown import ShutdownCoordinator
from kazu.ui.engine_companion import BrowserAppEngine
from kazu.ui.engine_qt import QtWebEngineFactory


def main() -> int:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import (
        QApplication,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QSplitter,
        QVBoxLayout,
        QWidget,
    )

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)

    base = Path(tempfile.gettempdir()) / "kazu-phase0-spike"
    paths = AppPaths(data_dir=base / "data", cache_dir=base / "cache", log_dir=base / "logs")
    paths.ensure_base_dirs()

    factory = QtWebEngineFactory(paths=paths, bg_hex="#0F0F10")
    monitor = MemoryMonitor()
    shutdown = ShutdownCoordinator()

    left_account = Account(
        id="spike_left_claude",
        label="Spike Claude",
        provider_key="claude",
        home_url="https://claude.ai",
        engine=EngineKind.EMBEDDED,
    )
    right_account = Account(
        id="spike_right_chatgpt",
        label="Spike ChatGPT",
        provider_key="chatgpt",
        home_url="https://chatgpt.com",
        engine=EngineKind.EMBEDDED,
    )
    gemini_account = Account(
        id="spike_companion_gemini",
        label="Spike Gemini",
        provider_key="gemini",
        home_url="https://gemini.google.com",
        engine=EngineKind.COMPANION,
    )

    left_pane = factory.create_pane(left_account)
    right_pane = factory.create_pane(right_account)

    window = QMainWindow()
    window.setWindowTitle("Kazu Phase 0 Spike (T1–T14)")
    window.resize(1360, 820)
    window.setStyleSheet("background-color: #0F0F10; color: #EDEDED;")

    root = QWidget()
    layout = QVBoxLayout(root)
    layout.setContentsMargins(0, 0, 0, 0)

    bar = QHBoxLayout()
    ram_label = QLabel("RAM: measuring...")
    companion_btn = QPushButton("Test T13: Launch Gemini Companion")

    def _launch_companion() -> None:
        engine = BrowserAppEngine(paths=paths)
        engine.launch(gemini_account)

    companion_btn.clicked.connect(_launch_companion)
    bar.addWidget(ram_label)
    bar.addStretch(1)
    bar.addWidget(companion_btn)
    layout.addLayout(bar)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.addWidget(left_pane.widget)
    splitter.addWidget(right_pane.widget)
    splitter.setSizes([680, 680])
    layout.addWidget(splitter, stretch=1)

    window.setCentralWidget(root)

    def _refresh_ram() -> None:
        sample = monitor.sample()
        ram_label.setText(
            f"Recursive RAM: {sample.total_rss_mb:.1f} MB "
            f"(main {sample.main_rss_mb:.1f} MB + {sample.child_count} child procs)"
        )

    timer = QTimer(window)
    timer.timeout.connect(_refresh_ram)
    timer.start(2000)

    shutdown.register_hide_views(window.hide)
    shutdown.register_destroy_views_and_pages(left_pane.dispose)
    shutdown.register_destroy_views_and_pages(right_pane.dispose)
    shutdown.set_event_processor(app.processEvents)
    shutdown.register_destroy_profiles(factory.dispose_all_profiles)
    app.aboutToQuit.connect(shutdown.execute)

    window.show()
    left_pane.load_url(left_account.home_url)
    QTimer.singleShot(150, lambda: right_pane.load_url(right_account.home_url))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
