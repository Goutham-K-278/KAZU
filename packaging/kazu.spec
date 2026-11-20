# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller spec for Kazu (Windows, macOS, Linux).

Run from repo root:
    uv run pyinstaller packaging/kazu.spec --noconfirm
"""

from pathlib import Path
import sys

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
ASSETS = SRC / "kazu" / "assets" / "kazu_logo.png"
ICONS = ROOT / "packaging" / "icons"

if sys.platform == "win32":
    APP_ICON = str(ICONS / "kazu.ico")
elif sys.platform == "darwin":
    APP_ICON = str(ICONS / "kazu.icns")
else:
    APP_ICON = str(ICONS / "kazu-256.png")

a = Analysis(
    [str(SRC / "kazu" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[(str(ASSETS), "kazu/assets")],
    hiddenimports=["kazu.ui.engine_qt"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="kazu",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=APP_ICON,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="kazu",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Kazu.app",
        icon=APP_ICON,
        bundle_identifier="com.kazu.workspace",
        info_plist={
            "CFBundleDisplayName": "Kazu",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            "NSMicrophoneUsageDescription": "Kazu requests microphone access only when you use voice mode on an AI site.",
            "NSCameraUsageDescription": "Kazu requests camera access only when you enable video on a site.",
        },
    )
