# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec to create a standalone Windows executable."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


block_cipher = None

project_root = Path(__file__).resolve().parents[1]

datas = collect_data_files("stuttgart_charts", include_py_files=False)
datas += collect_data_files("PySide6", include_py_files=False)
datas.append((str(project_root / "data" / "watchlist.csv"), "data"))

hiddenimports = sorted(
    set(
        collect_submodules("stuttgart_charts")
        + collect_submodules("PySide6.QtWebEngineCore")
        + collect_submodules("PySide6.QtWebEngineWidgets")
        + collect_submodules("PySide6.QtWebEngine")
    )
)

a = Analysis(
    [str(project_root / "windows_app" / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="BoerseStuttgartCharts",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
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
    name="BoerseStuttgartCharts",
)
