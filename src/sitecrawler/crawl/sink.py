"""Where a crawl sends its results, without ``crawl`` knowing about the store.

The crawler calls a :class:`CrawlSink` at four points. The SQLite store
implements it; tests use fakes. Every method is synchronous and is called
from the event loop between fetches, so implementations must be quick.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from sitecrawler.models import (
    CrawlConfig,
    PageRecord,
    QueueItem,
    ResumeState,
    SitemapEntry,
    SitemapFile,
)


class CrawlSink(Protocol):
    """Receives a crawl's results as they happen."""

    def begin(self, config: CrawlConfig, *, resume: bool) -> ResumeState:
        """Start (or resume) a crawl. Raises ``ValueError`` if that is not possible."""
        ...

    def seeded(
        self,
        items: Sequence[QueueItem],
        sitemap_files: Sequence[SitemapFile],
        sitemap_entries: Sequence[SitemapEntry],
    ) -> None:
        """Record the seeds as queued, plus every sitemap file read and every entry in them.

        Args:
            items: Queue items the frontier accepted during seeding.
            sitemap_files: Every sitemap or index the crawl tried to read, usable or not.
            sitemap_entries: Every ``<url>`` of every usable sitemap, with its file.
        """
        ...

    def page_done(self, record: PageRecord, discovered: Sequence[QueueItem]) -> None:
        """Record one fetched page and the new URLs it put on the queue, atomically."""
        ...

    def finish(self, *, pages_done: int, complete: bool) -> None:
        """Mark the crawl finished; ``complete`` is False when ``max_pages`` cut it short."""
        ...
