# -*- mode: python ; coding: utf-8 -*-

import os

# Minimal one-file PyInstaller spec for `riggbot.py`.
# Keeps the build deterministic while avoiding unnecessary native bundles.

_binaries = []

a = Analysis(
    ['riggbot.py'],
    pathex=[os.path.abspath('.')],
    binaries=_binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# EXE (no COLLECT) produces a one-file bundle when built with PyInstaller.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='riggbot',
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
