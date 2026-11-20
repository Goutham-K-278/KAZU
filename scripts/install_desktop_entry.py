"""Install Kazu into the current user's native Start Menu / Applications launcher.

Works out of the box for users who clone from GitHub and run:
    uv run python scripts/install_desktop_entry.py

- Windows: creates a windowless Start Menu shortcut using `pythonw.exe -m kazu`
  (so NO terminal/console window ever opens) with `packaging/icons/kazu.ico`.
- Linux: installs `~/.local/share/applications/kazu.desktop` and copies Kazu's
  256x256 PNG icon to `~/.local/share/icons/hicolor/256x256/apps/kazu.png`.
- macOS: creates a lightweight `~/Applications/Kazu.app` bundle launcher with
  `packaging/icons/kazu.icns`.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = REPO_ROOT / "packaging" / "icons"


def _resolve_windows_gui_target() -> tuple[Path, str]:
    """Return `(executable, args)` guaranteed to launch windowlessly on Windows.

    Prefers `pythonw.exe -m kazu` inside the active virtual environment so
    Windows never spawns a black console / Windows Terminal window.
    """
    exe = Path(sys.executable).resolve()
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        return pythonw, "-m kazu"
    kazu_gui = exe.parent / "kazu.exe"
    if kazu_gui.exists():
        return kazu_gui, ""
    return exe, "-m kazu"


def _resolve_unix_executable() -> Path:
    """Find the installed `kazu` launcher inside the active virtual environment."""
    bin_dir = Path(sys.executable).resolve().parent
    candidate = bin_dir / "kazu"
    if candidate.exists():
        return candidate
    return Path(sys.executable).resolve()


def _install_windows() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    start_menu = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    start_menu.mkdir(parents=True, exist_ok=True)
    shortcut_path = start_menu / "Kazu.lnk"
    icon_path = ICONS_DIR / "kazu.ico"

    target_exe, args = _resolve_windows_gui_target()
    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{shortcut_path}'); "
        f"$sc.TargetPath = '{target_exe}'; "
        f"$sc.Arguments = '{args}'; "
        f"$sc.WorkingDirectory = '{REPO_ROOT}'; "
        f"$sc.IconLocation = '{icon_path}'; "
        "$sc.WindowStyle = 1; "
        "$sc.Description = 'Kazu — Multi-Agent AI Workspace'; "
        "$sc.Save()"
    )
    subprocess.run(  # noqa: S603
        ["powershell", "-NoProfile", "-Command", ps_script],  # noqa: S607
        check=True,
    )
    return shortcut_path


def _install_linux(target_exe: Path) -> Path:
    apps_dir = Path.home() / ".local" / "share" / "applications"
    icons_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)

    icon_dest = icons_dir / "kazu.png"
    shutil.copy2(ICONS_DIR / "kazu-256.png", icon_dest)

    exec_cmd = str(target_exe) if target_exe.name == "kazu" else f"{target_exe} -m kazu"
    desktop_file = apps_dir / "kazu.desktop"
    desktop_file.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Kazu\n"
        "GenericName=Multi-Agent AI Workspace\n"
        "Comment=Run multiple AI chats side by side in isolated Spaces\n"
        f"Exec={exec_cmd}\n"
        "Icon=kazu\n"
        "Terminal=false\n"
        "Categories=Network;Utility;Office;\n"
        "StartupWMClass=kazu\n",
        encoding="utf-8",
    )
    return desktop_file


def _install_macos(target_exe: Path) -> Path:
    app_bundle = Path.home() / "Applications" / "Kazu.app"
    macos_dir = app_bundle / "Contents" / "MacOS"
    res_dir = app_bundle / "Contents" / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    res_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(ICONS_DIR / "kazu.icns", res_dir / "kazu.icns")
    (app_bundle / "Contents" / "Info.plist").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        "  <key>CFBundleName</key><string>Kazu</string>\n"
        "  <key>CFBundleDisplayName</key><string>Kazu</string>\n"
        "  <key>CFBundleIdentifier</key><string>com.kazu.workspace</string>\n"
        "  <key>CFBundleExecutable</key><string>kazu-launcher</string>\n"
        "  <key>CFBundleIconFile</key><string>kazu.icns</string>\n"
        "  <key>NSHighResolutionCapable</key><true/>\n"
        "</dict></plist>\n",
        encoding="utf-8",
    )

    launcher = macos_dir / "kazu-launcher"
    if target_exe.name == "kazu":
        exec_line = f'exec "{target_exe}"'
    else:
        exec_line = f'exec "{target_exe}" -m kazu'
    launcher.write_text(f"#!/bin/sh\n{exec_line}\n", encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return app_bundle


def main() -> int:
    if sys.platform == "win32":
        installed = _install_windows()
    elif sys.platform == "darwin":
        installed = _install_macos(_resolve_unix_executable())
    else:
        installed = _install_linux(_resolve_unix_executable())
    print(f"Kazu registered in your system launcher (no terminal window): {installed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
