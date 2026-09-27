"""JSON storage for state the bot writes itself (everything under data/).

- `JsonStore`: one document in one file (e.g. the global flag map).
- `GuildStore`: one document per Discord server. Each feature keeps its data under its own key.

Writes are atomic (write a temp file, then swap it in), so a crash mid-save can't leave a
half-written file. A file that can't be parsed is renamed to *.corrupt-<timestamp> and
replaced with defaults, so the bot keeps running and nothing is silently lost.
"""
import asyncio
import copy
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from . import paths

log = logging.getLogger(__name__)


def read_default(name: str, fallback: Any = None) -> Any:
    """A fresh copy of a JSON file from the shipped defaults (riggbot/defaults/).

    If the file is missing or broken, logs an error and returns `fallback`.
    """
    try:
        # deepcopy so callers can change the result without changing the cached original.
        return copy.deepcopy(_read_default_cached(name))
    except (OSError, ValueError) as e:
        log.error('Could not read default file %s: %s', name, e)
        return copy.deepcopy(fallback)


# Default files already read, by name, so each is only read from disk once.
_default_cache: dict[str, Any] = {}


def _read_default_cached(name: str) -> Any:
    if name not in _default_cache:
        _default_cache[name] = json.loads((paths.defaults_dir() / name).read_text(encoding='utf-8'))
    return _default_cache[name]


def write_json_atomic(path: Path, data: Any) -> None:
    """Save `data` to `path` as JSON, without ever leaving a half-written file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write everything to a temporary file first...
    tmp = path.with_name(path.name + '.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        # ensure_ascii=False keeps emoji readable in the file instead of \ud83c-style escapes.
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
    # ...then swap it into place in one step. If the bot crashes before this line,
    # the old file is still intact.
    os.replace(tmp, path)


def _read_or_quarantine(path: Path, expected_type: type) -> Any | None:
    """Parse `path`. If it exists but is unusable, move it aside and return None."""
    if not path.exists():
        return None
    try:
        # 'utf-8-sig' also accepts files saved by Notepad with a byte-order mark.
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if isinstance(data, expected_type):
            return data
        problem = f'expected a JSON {expected_type.__name__}, found {type(data).__name__}'
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        problem = str(e)
    # The file is broken. Rename it (rather than delete it) so it can be inspected or fixed by hand.
    aside = path.with_name(f'{path.name}.corrupt-{time.strftime("%Y%m%d-%H%M%S")}')
    os.replace(path, aside)
    log.error('Could not read %s (%s); moved it to %s and started from defaults', path, problem, aside.name)
    return None


class JsonStore:
    """One JSON document in one file.

    `data` is loaded when the store is created. Change it in place, then `await save()`.
    If the file doesn't exist yet, `data` starts as `initial()`.
    """

    def __init__(self, path: Path, initial: Callable[[], Any] = dict):
        self.path = path
        self._initial = initial         # a function returning the starting data, e.g. dict or list
        self._lock = asyncio.Lock()     # makes sure two saves never write the file at the same time
        self.data = self._load()

    def _load(self) -> Any:
        # The file must hold the same kind of data as initial() gives (e.g. an object, not a list).
        expected = type(self._initial())
        data = _read_or_quarantine(self.path, expected)
        if data is None:
            data = self._initial()
            log.debug('%s not found; starting from defaults', self.path.name)
        return data

    def reload(self) -> None:
        """Throw away the in-memory data and read the file again."""
        self.data = self._load()

    async def save(self) -> None:
        """Write the current `data` to disk."""
        async with self._lock:
            write_json_atomic(self.path, self.data)


class GuildStore:
    """One JSON document per Discord server, stored as <directory>/<guild_id>.json.

    Each feature keeps its data under its own key. `section()` returns a feature's data for a
    server (creating it from `initial()` on first use); change it in place, then
    `await save(guild_id)`.

    Example: a server's file might look like {"triggers": [...], "approved_bots": [123]}.
    """

    def __init__(self, directory: Path):
        self.directory = directory
        self._docs: dict[int, dict] = {}    # server ID -> its document, once loaded
        self._lock = asyncio.Lock()

    def _path(self, guild_id: int) -> Path:
        return self.directory / f'{guild_id}.json'

    def document(self, guild_id: int) -> dict:
        """The whole document for one server (loaded from disk the first time it's asked for)."""
        doc = self._docs.get(guild_id)
        if doc is None:
            # Not loaded yet: read the file, or start with an empty document for a new server.
            doc = _read_or_quarantine(self._path(guild_id), dict) or {}
            self._docs[guild_id] = doc
        return doc

    def section(self, guild_id: int, key: str, initial: Callable[[], Any]) -> Any:
        """One feature's data for one server, e.g. section(guild_id, 'triggers', list)."""
        doc = self.document(guild_id)
        if key not in doc:
            # First time this feature is used on this server: start from its default.
            doc[key] = initial()
        return doc[key]

    async def save(self, guild_id: int) -> None:
        """Write one server's document to disk."""
        async with self._lock:
            write_json_atomic(self._path(guild_id), self.document(guild_id))

    def reload(self) -> None:
        """Forget cached documents so they're re-read from disk on next use."""
        self._docs.clear()
