"""Simple per-key cooldowns, e.g. "don't translate the same message twice within 30 seconds".

Example:

    cooldown = Cooldown(lambda: 30)
    if cooldown.try_acquire(message.id):
        ...  # first time in 30 seconds for this message: go ahead
"""
import time
from typing import Callable, Hashable


class Cooldown:
    """Remembers, per key, until when that key is "cooling down"."""

    def __init__(self, seconds: Callable[[], float], clock: Callable[[], float] = time.monotonic):
        """`seconds` returns the current cooldown length (so it can come from config)."""
        self._seconds = seconds
        # The clock is replaceable so tests can fake the passing of time.
        # time.monotonic is used rather than the wall clock so changing the PC's time can't break it.
        self._clock = clock
        # key -> the moment its cooldown ends
        self._until: dict[Hashable, float] = {}

    def try_acquire(self, key: Hashable) -> bool:
        """True if `key` isn't cooling down, and starts its cooldown. False if it is."""
        now = self._clock()
        # Still cooling down from last time: refuse.
        if self._until.get(key, 0) > now:
            return False
        # Housekeeping: once the dict gets big, forget keys whose cooldown has already ended,
        # so memory use can't grow forever.
        if len(self._until) > 1000:
            self._until = {k: t for k, t in self._until.items() if t > now}
        # Start (or restart) this key's cooldown.
        self._until[key] = now + self._seconds()
        return True
