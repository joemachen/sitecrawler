"""The crawl loop: pull from the frontier, fetch, parse, feed links back."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

from sitecrawler.crawl.fetcher import Fetcher
from sitecrawler.crawl.frontier import Frontier
from sitecrawler.crawl.robots import RobotsCache
from sitecrawler.crawl.sink import CrawlSink
from sitecrawler.crawl.urls import normalize, same_site
from sitecrawler.models import (
    CrawlConfig,
    FetchResult,
    Outcome,
    PageRecord,
    QueueItem,
    ResumeState,
)
from sitecrawler.parse import parse_html, parse_sitemap

log = logging.getLogger(__name__)

ProgressCallback = Callable[[PageRecord, int, int], None]
"""Called after each page with (record, pages_done, pages_queued)."""

_Processed = tuple[PageRecord, list[str]]


class Crawler:
    """Breadth-first crawler for one site, or a fetcher for a given list of URLs.

    Usage::

        records = Crawler(CrawlConfig(start_url="https://example.com")).run()
        records = Crawler(CrawlConfig(seed_urls=("https://a.test/x", "https://b.test/y"))).run()

    With ``seed_urls`` the crawler is in *list mode*: it fetches exactly those
    URLs (any number of hosts), follows links only if ``follow_links`` is on
    and then only within the seeds' hosts, and never reads sitemaps.

    With a ``sink`` (normally a :class:`~sitecrawler.store.Store`) every page
    is handed over as soon as it is fetched, and ``resume=True`` continues an
    interrupted crawl from what the sink already holds.

    ``run`` drives an asyncio event loop internally; call :meth:`arun` instead
    from code that already has one.
    """

    def __init__(
        self, config: CrawlConfig, *, sink: CrawlSink | None = None, resume: bool = False
    ) -> None:
        """Validate the start URL or seed list and prepare (but do not start) the crawl."""
        if resume and sink is None:
            msg = "resume=True needs a sink to resume from"
            raise ValueError(msg)
        self.config = config
        self.sink = sink
        self.resume = resume
        self.list_mode = bool(config.seed_urls)
        self.robots = RobotsCache(config.user_agent)
        self.records: list[PageRecord] = []
        self.fetcher = Fetcher(
            config.user_agent,
            config.delay_seconds,
            config.timeout_seconds,
            max_redirects=config.max_redirects,
            http2=config.http2,
        )

        if self.list_mode:
            self.seeds = self._validate_seeds(config)
            self.start_url = ""
            self.scheme: str | None = None
            hosts = {urlparse(url).netloc for url in self.seeds}
            self.frontier = Frontier(hosts, scheme=None, keep_query=config.keep_query)
        else:
            start = normalize(config.start_url, keep_query=config.keep_query)
            if start is None:
                msg = (
                    "Give a start_url or seed_urls"
                    if not config.start_url
                    else f"Invalid start URL: {config.start_url!r}"
                )
                raise ValueError(msg)
            self.seeds = ()
            self.start_url = start
            self.scheme = urlparse(start).scheme
            self.frontier = Frontier(
                urlparse(start).netloc, scheme=self.scheme, keep_query=config.keep_query
            )

    @staticmethod
    def _validate_seeds(config: CrawlConfig) -> tuple[str, ...]:
        seeds: list[str] = []
        bad: list[str] = []
        for raw in config.seed_urls:
            url = normalize(raw, keep_query=config.keep_query)
            if url is None:
                bad.append(repr(raw))
            elif url not in seeds:
                seeds.append(url)
        if bad:
            msg = "Invalid URL(s) in list: " + "; ".join(bad)
            raise ValueError(msg)
        return tuple(seeds)

    # ------------------------------------------------------------------ setup
    async def _seed(self) -> None:
        seeds: list[QueueItem] = []
        sitemap_urls: list[tuple[str, str]] = []
        if self.list_mode:
            for url in self.seeds:
                item = self.frontier.add_seed(url, "list")
                if item is not None:
                    seeds.append(item)
            log.info("list mode: %d URLs to fetch", len(seeds))
        else:
            start_item = self.frontier.add(self.start_url, 0, "start")
            if start_item is not None:
                seeds.append(start_item)
            else:
                log.warning(
                    "start URL %s does not look like a page; nothing to crawl", self.start_url
                )
            if self.config.use_sitemap:
                await self._seed_from_sitemaps(seeds, sitemap_urls)
        if self.sink is not None:
            self.sink.seeded(seeds, sitemap_urls)

    async def _seed_from_sitemaps(
        self, seeds: list[QueueItem], sitemap_urls: list[tuple[str, str]]
    ) -> None:
        policy = await self.robots.policy(self.fetcher, self.start_url)
        candidates = [*policy.sitemaps(), urljoin(self.start_url, "/sitemap.xml")]
        visited: set[str] = set()
        from_sitemaps = 0
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
                continue
            for loc in doc.locs:
                sitemap_urls.append((sitemap_url, loc))
                item = self.frontier.add(loc, 0, f"sitemap:{sitemap_url}")
                if item is not None:
                    seeds.append(item)
                    from_sitemaps += 1
        log.info("seeded %d URLs from %d sitemap file(s)", from_sitemaps, len(visited))

    # ------------------------------------------------------------------ one page
    async def _process(self, item: QueueItem) -> _Processed:
        """Fetch and parse one URL. Returns the record and the raw links found.

        Never raises: a page that breaks the parser becomes an ``ERROR`` record
        so one weird page cannot end the crawl.
        """
        record = PageRecord(
            url=item.url, outcome=Outcome.FETCHED, depth=item.depth, found_on=item.found_on
        )
        try:
            if self.config.respect_robots and not await self.robots.allowed(self.fetcher, item.url):
                record.outcome = Outcome.BLOCKED
                record.error = "disallowed by robots.txt"
                return record, []
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

        page_host = urlparse(item.url).netloc
        final = self._normalize(result.final_url)
        if final and not self.frontier.in_scope(urlparse(final).netloc):
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
        record.h1s = tuple(page.h1s)
        record.h2s = tuple(page.h2s)
        record.meta_robots = page.meta_robots
        record.lang = page.lang
        record.word_count = page.word_count
        record.links = tuple(page.anchors)
        if page.canonical:
            record.canonical = page.canonical

        internal = {self._normalize(link) for link in page.links}
        internal.discard(None)
        record.internal_links = sum(
            1 for link in internal if link and same_site(urlparse(link).netloc, page_host)
        )
        return record, page.links if self.config.follow_links else []

    def _normalize(self, url: str) -> str | None:
        return normalize(url, keep_query=self.config.keep_query, scheme=self.scheme)

    @staticmethod
    def _is_parsable(result: FetchResult) -> bool:
        return result.is_html and result.status_code is not None and result.status_code < 400

    # ------------------------------------------------------------------ run
    def run(self, on_progress: ProgressCallback | None = None) -> list[PageRecord]:
        """Crawl until the frontier is empty or ``max_pages`` is reached.

        Returns:
            The page records fetched by this run, sorted by URL. On a resumed
            crawl that excludes pages from earlier runs; read those from the sink.
        """
        return asyncio.run(self.arun(on_progress))

    async def arun(self, on_progress: ProgressCallback | None = None) -> list[PageRecord]:
        """Async form of :meth:`run`, for callers that already have an event loop."""
        async with self.fetcher:
            state = ResumeState()
            if self.sink is not None:
                state = self.sink.begin(self.config, resume=self.resume)
            done = state.done
            if self.resume:
                self.frontier.mark_seen(state.seen)
                for item in state.pending:
                    self.frontier.restore(item)
                log.info("resuming: %d done, %d pending", state.done, len(state.pending))
            else:
                await self._seed()
            done = await self._crawl_loop(on_progress, done)

        self.records.sort(key=lambda r: r.url)
        if len(self.frontier):
            log.warning(
                "stopped at max_pages=%d with %d URLs unvisited",
                self.config.max_pages,
                len(self.frontier),
            )
        if self.sink is not None:
            self.sink.finish(pages_done=done, complete=len(self.frontier) == 0)
        return self.records

    async def _crawl_loop(self, on_progress: ProgressCallback | None, done: int) -> int:
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
                discovered: list[QueueItem] = []
                for link in links:
                    queued = self.frontier.add(link, record.depth + 1, record.url)
                    if queued is not None:
                        discovered.append(queued)
                if self.sink is not None:
                    self.sink.page_done(record, discovered)
                if on_progress is not None:
                    on_progress(record, done, len(self.frontier))
        finally:
            for task in inflight:
                task.cancel()
            if inflight:
                await asyncio.gather(*inflight, return_exceptions=True)
        return done
