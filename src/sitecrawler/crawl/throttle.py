"""Per-host politeness delay for the asyncio fetcher."""

from __future__ import annotations

import asyncio
import time


class HostThrottle:
    """Allow at most one request per ``delay_seconds`` to each host.

    Every coroutine calls :meth:`acquire` before a request. Calls for the same
    host queue up behind one lock and are released ``delay_seconds`` apart;
    different hosts never wait for each other. A delay of zero never sleeps.
    """

    def __init__(self, delay_seconds: float) -> None:
        """Create a throttle; ``delay_seconds`` is the gap between requests per host."""
        self._delay = delay_seconds
        self._next_allowed: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def acquire(self, host: str) -> None:
        """Return once a request to ``host`` may be sent."""
        if self._delay <= 0:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._next_allowed.get(host, 0.0) - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_allowed[host] = time.monotonic() + self._delay
