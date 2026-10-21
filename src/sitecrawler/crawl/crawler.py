"""The crawl loop: pull from the frontier, fetch, parse, feed links back."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

from sitecrawler.crawl.fetcher import Fetcher
from sitecrawler.crawl.frontier import Frontier
from sitecrawler.crawl.robots import RobotsPolicy
from sitecrawler.crawl.urls import normalize, same_site
from sitecrawler.models import CrawlConfig, FetchResult, Outcome, PageRecord, QueueItem
from sitecrawler.parse import parse_html, parse_sitemap

log = logging.getLogger(__name__)

ProgressCallback = Callable[[PageRecord, int, int], None]
"""Called after each page with (record, pages_done, pages_queued)."""

_Processed = tuple[PageRecord, list[str]]


class Crawler:
    """Breadth-first crawler for a single site.

    Usage::

        records = Crawler(CrawlConfig(start_url="https://example.com")).run()

    ``run`` drives an asyncio event loop internally; call :meth:`arun` instead
    from code that already has one.
    """

    def __init__(self, config: CrawlConfig) -> None:
        """Validate the start URL and prepare (but do not start) the crawl."""
        start = normalize(config.start_url, keep_query=config.keep_query)
        if start is None:
            msg = f"Invalid start URL: {config.start_url!r}"
            raise ValueError(msg)
        self.config = config
        self.start_url = start
        self.host = urlparse(start).netloc
        self.scheme = urlparse(start).scheme
        self.frontier = Frontier(self.host, scheme=self.scheme, keep_query=config.keep_query)
        self.fetcher = Fetcher(
            config.user_agent,
            config.delay_seconds,
            config.timeout_seconds,
            max_redirects=config.max_redirects,
            http2=config.http2,
        )
        self.robots = RobotsPolicy(config.user_agent)
        self.records: list[PageRecord] = []

    # ------------------------------------------------------------------ setup
    async def _seed(self) -> None:
        self.frontier.add(self.start_url, 0, "start")
        if not self.config.use_sitemap:
            return
        candidates = [*self.robots.sitemaps(), urljoin(self.start_url, "/sitemap.xml")]
        visited: set[str] = set()
        seeded = 0
        while candidates:
            sitemap_url = candidates.pop(0)
            if sitemap_url in visited:
                continue
            visited.add(sitemap_url)
            result = await self.fetcher.fetch(sitemap_url)
            if result.outcome is not Outcome.FETCHED or result.status_code != 200:
                continue
            doc = parse_sitemap(result.content)
            if doc is None:
                continue
            if doc.kind == "index":
                candidates.extend(doc.locs)
            else:
                for loc in doc.locs:
                    if self.frontier.add(loc, 0, f"sitemap:{sitemap_url}"):
                        seeded += 1
        log.info("seeded %d URLs from %d sitemap file(s)", seeded, len(visited))

    # ------------------------------------------------------------------ one page
    async def _process(self, item: QueueItem) -> _Processed:
        """Fetch and parse one URL. Returns the record and the raw links found.

        Never raises: a page that breaks the parser becomes an ``ERROR`` record
        so one weird page cannot end the crawl.
        """
        record = PageRecord(
            url=item.url, outcome=Outcome.FETCHED, depth=item.depth, found_on=item.found_on
        )
        if self.config.respect_robots and not self.robots.allowed(item.url):
            record.outcome = Outcome.BLOCKED
            record.error = "disallowed by robots.txt"
            return record, []
        try:
            return await self._fetch_and_parse(item, record)
        except Exception as exc:  # deliberately total, see docstring
            log.exception("unexpected failure processing %s", item.url)
            record.outcome = Outcome.ERROR
            record.error = f"internal error: {exc}"[:200]
            return record, []

    async def _fetch_and_parse(self, item: QueueItem, record: PageRecord) -> _Processed:
        result = await self.fetcher.fetch(item.url)
        record.outcome = result.outcome
        record.status_code = result.status_code
        record.content_type = result.content_type
        record.fetch_ms = result.elapsed_ms
        record.error = result.error
        record.final_url = result.final_url
        record.size_bytes = result.size_bytes
        record.headers = result.headers
        record.redirect_hops = result.hops
        if result.outcome is not Outcome.FETCHED:
            return record, []

        final = self._normalize(result.final_url)
        if final and not same_site(urlparse(final).netloc, self.host):
            record.error = f"redirected off-site to {result.final_url}"
            return record, []
        if final and final != item.url:
            record.canonical = final  # overwritten below if the page declares one

        if not self._is_parsable(result):
            return record, []

        page = parse_html(result.text, result.final_url)
        record.title = page.title
        record.meta_description = page.meta_description
        record.h1 = page.h1
        record.word_count = page.word_count
        if page.canonical:
            record.canonical = page.canonical

        internal = {self._normalize(link) for link in page.links}
        internal.discard(None)
        record.internal_links = sum(
            1 for link in internal if link and same_site(urlparse(link).netloc, self.host)
        )
        return record, page.links

    def _normalize(self, url: str) -> str | None:
        return normalize(url, keep_query=self.config.keep_query, scheme=self.scheme)

    @staticmethod
    def _is_parsable(result: FetchResult) -> bool:
        return result.is_html and result.status_code is not None and result.status_code < 400

    # ------------------------------------------------------------------ run
    def run(self, on_progress: ProgressCallback | None = None) -> list[PageRecord]:
        """Crawl until the frontier is empty or ``max_pages`` is reached.

        Returns:
            All page records, sorted by URL.
        """
        return asyncio.run(self.arun(on_progress))

    async def arun(self, on_progress: ProgressCallback | None = None) -> list[PageRecord]:
        """Async form of :meth:`run`, for callers that already have an event loop."""
        async with self.fetcher:
            if self.config.respect_robots:
                await self.robots.load(self.fetcher, self.start_url)
            await self._seed()
            await self._crawl_loop(on_progress)

        self.records.sort(key=lambda r: r.url)
        if len(self.frontier):
            log.warning(
                "stopped at max_pages=%d with %d URLs unvisited",
                self.config.max_pages,
                len(self.frontier),
            )
        return self.records

    async def _crawl_loop(self, on_progress: ProgressCallback | None) -> None:
        done = 0
        limit = self.config.max_pages
        inflight: dict[asyncio.Task[_Processed], QueueItem] = {}
        try:
            while (len(self.frontier) or inflight) and done < limit:
                while len(inflight) < self.config.workers and done + len(inflight) < limit:
                    item = self.frontier.pop()
                    if item is None:
                        break
                    inflight[asyncio.create_task(self._process(item))] = item
                if not inflight:
                    break
                # Take one finished task at a time so ``max_pages`` is exact.
                finished, _ = await asyncio.wait(inflight, return_when=asyncio.FIRST_COMPLETED)
                task = next(iter(finished))
                inflight.pop(task)
                record, links = task.result()
                self.records.append(record)
                done += 1
                for link in links:
                    self.frontier.add(link, record.depth + 1, record.url)
                if on_progress is not None:
                    on_progress(record, done, len(self.frontier))
        finally:
            for task in inflight:
                task.cancel()
            if inflight:
                await asyncio.gather(*inflight, return_exceptions=True)
