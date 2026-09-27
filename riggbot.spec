# -*- mode: python ; coding: utf-8 -*-
# One-file PyInstaller build:  pyinstaller riggbot.spec
#
# The exe looks for .env, config.json, data/ and logs/ next to itself.
# The shipped defaults (riggbot/defaults/) are bundled inside the exe.

import os

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[('riggbot/defaults', 'riggbot/defaults')],
    # Cogs are loaded by name and providers are imported lazily, so list them explicitly.
    hiddenimports=collect_submodules('riggbot.cogs') + collect_submodules('riggbot.translation'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

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
