"""HTTP fetching with a global politeness delay."""

from __future__ import annotations

import threading
import time

import requests

from sitecrawler.models import FetchResult, Outcome


class Fetcher:
    """Fetches URLs through one shared session, never faster than ``delay`` allows.

    The delay is global across threads: with four workers and a 0.5 s delay the
    site still sees at most two requests per second.
    """

    def __init__(self, user_agent: str, delay_seconds: float, timeout_seconds: float) -> None:
        """Create a fetcher with its own :class:`requests.Session`."""
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.session.headers["Accept"] = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"
        self._delay = delay_seconds
        self._timeout = timeout_seconds
        self._lock = threading.Lock()
        self._last_request = 0.0

    def throttle(self) -> None:
        """Block until at least ``delay`` seconds have passed since the last request."""
        with self._lock:
            wait = self._last_request + self._delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    def fetch(self, url: str) -> FetchResult:
        """GET ``url`` following redirects and return what came back.

        Never raises for HTTP or network errors; those are reported in the result.
        """
        self.throttle()
        started = time.monotonic()
        try:
            response = self.session.get(url, timeout=self._timeout, allow_redirects=True)
        except requests.RequestException as exc:
            return FetchResult(
                url=url,
                outcome=Outcome.ERROR,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                error=str(exc)[:200],
            )
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        return FetchResult(
            url=url,
            outcome=Outcome.FETCHED,
            status_code=response.status_code,
            final_url=response.url,
            content_type=content_type,
            text=response.text if "html" in content_type else "",
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
