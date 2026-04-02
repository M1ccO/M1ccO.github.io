# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs


# PyInstaller does not define __file__ inside the spec execution context.
# Resolve paths from the working directory instead; the build script runs
# PyInstaller from the project root.
project_dir = Path.cwd()

datas = [
    (str(project_dir / 'assets'), 'assets'),
    (str(project_dir / 'databases'), 'databases'),
    (str(project_dir / 'preview'), 'preview'),
    (str(project_dir / 'styles'), 'styles'),
]

hiddenimports = [
    'OCC.Core',
    'OCC.Display',
]

try:
    occ_binaries = collect_dynamic_libs('OCC')
except Exception:
    occ_binaries = []


a = Analysis(
    ['main.py'],
    pathex=[str(project_dir)],
    binaries=occ_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Tools and jaws Library',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Tools and jaws Library',
)
