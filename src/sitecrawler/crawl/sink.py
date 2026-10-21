"""Where a crawl sends its results, without ``crawl`` knowing about the store.

The crawler calls a :class:`CrawlSink` at four points. The SQLite store
implements it; tests use fakes. Every method is synchronous and is called
from the event loop between fetches, so implementations must be quick.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sitecrawler.models import CrawlConfig, PageRecord, QueueItem, ResumeState


class CrawlSink(Protocol):
    """Receives a crawl's results as they happen."""

    def begin(self, config: CrawlConfig, *, resume: bool) -> ResumeState:
        """Start (or resume) a crawl. Raises ``ValueError`` if that is not possible."""
        ...

    def seeded(self, items: Sequence[QueueItem], sitemap_urls: Sequence[tuple[str, str]]) -> None:
        """Record the start URL and sitemap seeds as queued, plus every sitemap URL seen.

        Args:
            items: Queue items the frontier accepted during seeding.
            sitemap_urls: ``(sitemap_url, loc)`` for every URL in every sitemap file.
        """
        ...

    def page_done(self, record: PageRecord, discovered: Sequence[QueueItem]) -> None:
        """Record one fetched page and the new URLs it put on the queue, atomically."""
        ...

    def finish(self, *, pages_done: int, complete: bool) -> None:
        """Mark the crawl finished; ``complete`` is False when ``max_pages`` cut it short."""
        ...
