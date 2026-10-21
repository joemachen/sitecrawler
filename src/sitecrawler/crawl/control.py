"""Pause, resume or stop a running crawl from another thread."""

from __future__ import annotations

import threading

POLL_SECONDS = 0.25
"""How often the crawl loop looks at its control while waiting on fetches."""


class CrawlControl:
    """Flags a :class:`~sitecrawler.crawl.Crawler` checks between fetches.

    Built on ``threading.Event`` rather than loop callbacks so it can be
    created before the event loop exists, poked from any thread (the web
    server's, a signal handler's) and unit-tested without a loop. The loop
    notices a change within :data:`POLL_SECONDS`.

    A crawler without an explicit control gets a fresh one whose flags are
    never set, so the default behaviour is unchanged.
    """

    def __init__(self) -> None:
        """Start with nothing requested."""
        self._paused = threading.Event()
        self._stop = threading.Event()

    def pause(self) -> None:
        """Stop scheduling new fetches; in-flight ones finish and are recorded."""
        self._paused.set()

    def resume(self) -> None:
        """Carry on after :meth:`pause`."""
        self._paused.clear()

    def stop(self) -> None:
        """End the crawl: in-flight fetches are cancelled and the sink is told it is incomplete."""
        self._stop.set()
        self._paused.clear()

    @property
    def paused(self) -> bool:
        """True while a pause is requested."""
        return self._paused.is_set()

    @property
    def stopping(self) -> bool:
        """True once a stop is requested; never cleared."""
        return self._stop.is_set()
