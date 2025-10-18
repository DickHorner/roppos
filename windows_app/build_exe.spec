# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building the Windows desktop executable."""
from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

project_root = Path(__file__).resolve().parent.parent

# Bundle static assets (watchlist, Plotly schema files, etc.).
datas = [
    (str(project_root / "data" / "watchlist.csv"), "data"),
]

datas += collect_data_files("plotly")

a = Analysis(
    [str(project_root / "windows_app" / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngine",
        "PySide6.QtWebChannel",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StuttgartCharts",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="StuttgartCharts",
)
