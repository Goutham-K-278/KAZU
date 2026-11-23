"""Application bootstrap.

HiDPI PassThrough, Chromium tuning, App Icon, SingleInstanceLock, and clean shutdown.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path

from kazu.domain.providers import ProviderPresetRegistry
from kazu.infra.db import Database
from kazu.infra.logging_setup import configure_logging
from kazu.infra.paths import AppPaths
from kazu.infra.shutdown import ShutdownCoordinator
from kazu.infra.single_instance import SingleInstanceLock

WINDOWS_APP_USER_MODEL_ID: str = "com.kazu.workspace"
_DEFAULT_CHROMIUM_FLAGS: tuple[str, ...] = (
    "--log-level=3",
    "--enable-gpu-rasterization",
    "--disable-features=MediaRouter",
)


def _configure_chromium_runtime() -> None:
    """Suppress noisy Chromium stderr warnings and disable unused background features."""
    existing_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    existing_keys = {flag.split("=", 1)[0] for flag in existing_flags}
    for flag in _DEFAULT_CHROMIUM_FLAGS:
        key = flag.split("=", 1)[0]
        if key not in existing_keys:
            existing_flags.append(flag)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(existing_flags).strip()
    os.environ.setdefault("QT_LOGGING_RULES", "js=false;qt.webenginecontext.debug=false")


def resolve_app_icon_path() -> Path | None:
    """Locate the bundled Kazu logo PNG in both source and frozen executable builds."""
    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "kazu" / "assets" / "kazu_logo.png")
    candidates.append(Path(__file__).resolve().parent / "assets" / "kazu_logo.png")
    for path in candidates:
        if path.exists():
            return path
    return None


def _configure_windows_taskbar_id() -> None:
    """Ensure Windows pins and taskbar show Kazu's own icon instead of python.exe."""
    if sys.platform != "win32":
        return
    try:  # noqa: SIM105
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
            WINDOWS_APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):  # noqa: S110
        pass


def run_app(argv: list[str] | None = None) -> int:
    """Launch Kazu with fast window startup, native app icon, and guaranteed ordered teardown."""
    _configure_chromium_runtime()

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    _configure_windows_taskbar_id()

    # Problem D4: crisp HiDPI text on 125%/150%/200% displays.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    qt_app = QApplication(argv if argv is not None else sys.argv)
    qt_app.setApplicationName("Kazu")
    qt_app.setOrganizationName("Kazu")
    qt_app.setDesktopFileName("kazu")

    icon_path = resolve_app_icon_path()
    if icon_path is not None:
        qt_app.setWindowIcon(QIcon(str(icon_path)))

    paths = AppPaths.default()
    paths.ensure_base_dirs()
    configure_logging(paths.log_file, level=logging.INFO)

    lock = SingleInstanceLock()
    db = Database(paths.db_path)
    settings = db.load_settings()
    presets = ProviderPresetRegistry()
    shutdown = ShutdownCoordinator()
    shutdown.set_event_processor(qt_app.processEvents)

    from kazu.ui.main_window import MainWindow

    window = MainWindow(
        db=db,
        paths=paths,
        settings=settings,
        presets=presets,
        shutdown=shutdown,
    )
    if icon_path is not None:
        window.setWindowIcon(QIcon(str(icon_path)))

    def _bring_to_front() -> None:
        window.showNormal()
        window.raise_()
        window.activateWindow()

    if not lock.try_acquire(on_activate=_bring_to_front):
        db.close()
        return 0

    shutdown.register_checkpoint_storage(lock.release)
    qt_app.aboutToQuit.connect(shutdown.execute)

    window.show()
    return qt_app.exec()
