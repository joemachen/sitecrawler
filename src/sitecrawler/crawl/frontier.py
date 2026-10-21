"""The crawl frontier: which URLs are still to be fetched, and which we've seen."""

from __future__ import annotations

import threading
from collections import deque
from urllib.parse import urlparse

from sitecrawler.crawl.urls import looks_like_page, normalize, same_site
from sitecrawler.models import QueueItem


class Frontier:
    """Thread-safe FIFO of URLs to crawl, de-duplicated by normalised form.

    Only URLs on the same site as ``site_host`` that look like HTML pages are
    accepted; everything else is silently dropped by :meth:`add`.
    """

    def __init__(self, site_host: str, *, scheme: str = "https", keep_query: bool = False) -> None:
        """Create an empty frontier scoped to one site (host and scheme)."""
        self._host = site_host
        self._scheme = scheme
        self._keep_query = keep_query
        self._seen: set[str] = set()
        self._queue: deque[QueueItem] = deque()
        self._lock = threading.Lock()

    def add(self, url: str, depth: int, found_on: str) -> bool:
        """Queue ``url`` if it is in scope and new. Returns True if it was queued."""
        normalised = normalize(url, keep_query=self._keep_query, scheme=self._scheme)
        if normalised is None:
            return False
        if not same_site(urlparse(normalised).netloc, self._host):
            return False
        if not looks_like_page(normalised):
            return False
        with self._lock:
            if normalised in self._seen:
                return False
            self._seen.add(normalised)
            self._queue.append(QueueItem(normalised, depth, found_on))
            return True

    def pop(self) -> QueueItem | None:
        """Take the next item, or ``None`` when the queue is empty."""
        with self._lock:
            return self._queue.popleft() if self._queue else None

    def __len__(self) -> int:
        """Number of URLs still queued (not counting in-flight ones)."""
        return len(self._queue)

    @property
    def seen_count(self) -> int:
        """Number of distinct URLs ever accepted."""
        return len(self._seen)
