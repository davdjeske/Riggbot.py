"""Simple per-key cooldowns, e.g. "don't translate the same message twice within 30 seconds"."""
import time
from typing import Callable, Hashable


class Cooldown:
    def __init__(self, seconds: Callable[[], float], clock: Callable[[], float] = time.monotonic):
        """`seconds` returns the current cooldown length (so it can come from config)."""
        self._seconds = seconds
        self._clock = clock
        self._until: dict[Hashable, float] = {}

    def try_acquire(self, key: Hashable) -> bool:
        """True if `key` isn't cooling down, and starts its cooldown. False if it is."""
        now = self._clock()
        if self._until.get(key, 0) > now:
            return False
        if len(self._until) > 1000:
            self._until = {k: t for k, t in self._until.items() if t > now}
        self._until[key] = now + self._seconds()
        return True
