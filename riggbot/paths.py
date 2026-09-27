"""Filesystem locations.

Everything the bot reads or writes at runtime (config.json, .env, data/, logs/) lives in the
*base directory*: the folder containing the exe when frozen by PyInstaller, otherwise the
project root. This keeps the bot working no matter which directory it's launched from.
Set RIGGBOT_HOME to use a different base directory.
"""
import os
import sys
from pathlib import Path

# The folder this file lives in: .../Riggbot/riggbot
_PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    """True when running as the PyInstaller exe instead of from Python source."""
    # PyInstaller sets sys.frozen = True inside the exe; normal Python doesn't have it at all.
    return bool(getattr(sys, 'frozen', False))


def base_dir() -> Path:
    """The folder where .env, config.json, data/ and logs/ live."""
    # 1. An explicit override always wins (handy for testing with a separate folder).
    override = os.getenv('RIGGBOT_HOME', '').strip()
    if override:
        return Path(override).resolve()
    # 2. Running as riggbot.exe: use the folder the exe is in.
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # 3. Running from source: use the project root (the folder above riggbot/).
    return _PACKAGE_DIR.parent


def defaults_dir() -> Path:
    """Read-only defaults shipped with the bot (bundled inside the exe when frozen)."""
    # A one-file exe unpacks its bundled files into a temporary folder, sys._MEIPASS.
    bundle_root = getattr(sys, '_MEIPASS', None)
    if bundle_root:
        return Path(bundle_root) / 'riggbot' / 'defaults'
    # From source, the defaults are simply in riggbot/defaults/.
    return _PACKAGE_DIR / 'defaults'
