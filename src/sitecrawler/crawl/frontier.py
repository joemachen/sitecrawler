"""The crawl frontier: which URLs are still to be fetched, and which we've seen."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from urllib.parse import urlparse

from sitecrawler.crawl.urls import looks_like_page, normalize, same_site
from sitecrawler.models import QueueItem


class Frontier:
    """FIFO of URLs to crawl, de-duplicated by normalised form.

    Only URLs on the same site as ``site_host`` that look like HTML pages are
    accepted; everything else is silently dropped by :meth:`add`. The crawler
    drives it from a single event loop, so no locking is needed.
    """

    def __init__(self, site_host: str, *, scheme: str = "https", keep_query: bool = False) -> None:
        """Create an empty frontier scoped to one site (host and scheme)."""
        self._host = site_host
        self._scheme = scheme
        self._keep_query = keep_query
        self._seen: set[str] = set()
        self._queue: deque[QueueItem] = deque()

    def add(self, url: str, depth: int, found_on: str) -> QueueItem | None:
        """Queue ``url`` if it is in scope and new. Returns the queued item, else ``None``."""
        normalised = normalize(url, keep_query=self._keep_query, scheme=self._scheme)
        if normalised is None:
            return None
        if not same_site(urlparse(normalised).netloc, self._host):
            return None
        if not looks_like_page(normalised):
            return None
        if normalised in self._seen:
            return None
        self._seen.add(normalised)
        item = QueueItem(normalised, depth, found_on)
        self._queue.append(item)
        return item

    def mark_seen(self, urls: Iterable[str]) -> None:
        """Treat ``urls`` as already known so :meth:`add` will not queue them again."""
        self._seen.update(urls)

    def restore(self, item: QueueItem) -> None:
        """Re-queue an item from a previous run without re-checking scope."""
        self._seen.add(item.url)
        self._queue.append(item)

    def pop(self) -> QueueItem | None:
        """Take the next item, or ``None`` when the queue is empty."""
        return self._queue.popleft() if self._queue else None

    def __len__(self) -> int:
        """Number of URLs still queued (not counting in-flight ones)."""
        return len(self._queue)

    @property
    def seen_count(self) -> int:
        """Number of distinct URLs ever accepted."""
        return len(self._seen)
