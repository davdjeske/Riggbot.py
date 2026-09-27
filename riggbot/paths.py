"""Filesystem locations.

Everything the bot reads or writes at runtime (config.json, .env, data/, logs/) lives in the
*base directory*: the folder containing the exe when frozen by PyInstaller, otherwise the
project root. This keeps the bot working no matter which directory it's launched from.
Set RIGGBOT_HOME to use a different base directory.
"""
import os
import sys
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def base_dir() -> Path:
    override = os.getenv('RIGGBOT_HOME', '').strip()
    if override:
        return Path(override).resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return _PACKAGE_DIR.parent


def defaults_dir() -> Path:
    """Read-only defaults shipped with the bot (bundled inside the exe when frozen)."""
    bundle_root = getattr(sys, '_MEIPASS', None)
    if bundle_root:
        return Path(bundle_root) / 'riggbot' / 'defaults'
    return _PACKAGE_DIR / 'defaults'
