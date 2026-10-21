"""The crawl frontier: which URLs are still to be fetched, and which we've seen."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from urllib.parse import urlparse

from sitecrawler.crawl.urls import looks_like_page, normalize, strip_www
from sitecrawler.models import QueueItem


class Frontier:
    """FIFO of URLs to crawl, de-duplicated by normalised form.

    Only URLs on one of the ``hosts`` that look like HTML pages are accepted;
    everything else is silently dropped by :meth:`add`. The crawler drives it
    from a single event loop, so no locking is needed.
    """

    def __init__(
        self,
        hosts: str | Iterable[str],
        *,
        scheme: str | None = "https",
        keep_query: bool = False,
    ) -> None:
        """Create an empty frontier scoped to one host (a string) or several.

        Args:
            hosts: The site host, or every host a list-mode crawl may visit.
            scheme: Force every URL to this scheme so http and https forms of a
                page collapse; ``None`` keeps each URL's own scheme.
            keep_query: Treat different query strings as different pages.
        """
        names = [hosts] if isinstance(hosts, str) else list(hosts)
        self._hosts = frozenset(strip_www(h) for h in names)
        self._scheme = scheme
        self._keep_query = keep_query
        self._seen: set[str] = set()
        self._queue: deque[QueueItem] = deque()

    def in_scope(self, host: str) -> bool:
        """True when ``host`` is one of the frontier's hosts (``www.`` ignored)."""
        return strip_www(host) in self._hosts

    def add(self, url: str, depth: int, found_on: str) -> QueueItem | None:
        """Queue ``url`` if it is in scope and new. Returns the queued item, else ``None``."""
        normalised = normalize(url, keep_query=self._keep_query, scheme=self._scheme)
        if normalised is None:
            return None
        if not self.in_scope(urlparse(normalised).netloc):
            return None
        if not looks_like_page(normalised):
            return None
        return self._enqueue(normalised, depth, found_on)

    def add_seed(self, url: str, found_on: str) -> QueueItem | None:
        """Queue a URL the user asked for explicitly: normalised and de-duplicated only."""
        normalised = normalize(url, keep_query=self._keep_query, scheme=self._scheme)
        if normalised is None:
            return None
        return self._enqueue(normalised, 0, found_on)

    def _enqueue(self, url: str, depth: int, found_on: str) -> QueueItem | None:
        if url in self._seen:
            return None
        self._seen.add(url)
        item = QueueItem(url, depth, found_on)
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
