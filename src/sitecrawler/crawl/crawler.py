"""The crawl loop: pull from the frontier, fetch, parse, feed links back."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import replace
from urllib.parse import urljoin, urlparse

from sitecrawler.crawl.control import POLL_SECONDS, CrawlControl
from sitecrawler.crawl.fetcher import Fetcher
from sitecrawler.crawl.frontier import Frontier
from sitecrawler.crawl.renderer import Renderer, require_playwright
from sitecrawler.crawl.robots import RobotsCache
from sitecrawler.crawl.sink import CrawlSink
from sitecrawler.crawl.urls import normalize, same_site
from sitecrawler.models import (
    CrawlConfig,
    FetchResult,
    Outcome,
    PageRecord,
    ParsedPage,
    QueueItem,
    ResumeState,
    SitemapEntry,
    SitemapFile,
)
from sitecrawler.parse import (
    compile_extractors,
    diff_rendered,
    link_header_rels,
    parse_html,
    parse_sitemap,
)

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

    A ``control`` lets another thread pause, resume or stop the crawl while it
    runs (see :class:`~sitecrawler.crawl.control.CrawlControl`). A stopped
    crawl tells its sink it is incomplete, so the file can be resumed later.

    With ``config.render`` on, every parsable HTML page is also loaded in
    headless Chromium after its raw fetch; the record then carries the
    rendered fields and a :class:`~sitecrawler.models.RenderDiff` against
    the raw ones. Playwright must be installed, or construction fails.

    With ``config.extract`` or ``config.search`` set, every parsable HTML page
    also carries the custom extraction and search results, computed from the
    same text the page record was parsed from (ADR-0009).
    """

    def __init__(
        self,
        config: CrawlConfig,
        *,
        sink: CrawlSink | None = None,
        resume: bool = False,
        control: CrawlControl | None = None,
    ) -> None:
        """Validate the start URL or seed list and prepare (but do not start) the crawl.

        Raises:
            ValueError: a bad start URL or seed, ``resume`` without a sink,
                rendering requested without Playwright installed, or an
                extractor or search that does not compile.
        """
        if resume and sink is None:
            msg = "resume=True needs a sink to resume from"
            raise ValueError(msg)
        self.config = config
        self.sink = sink
        self.resume = resume
        self.control = control if control is not None else CrawlControl()
        self.list_mode = bool(config.seed_urls)
        self.robots = RobotsCache(config.user_agent)
        self.records: list[PageRecord] = []
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
        self.fetcher = Fetcher(
            config.user_agent,
            config.delay_seconds,
            config.timeout_seconds,
            max_redirects=config.max_redirects,
            http2=config.http2,
            hop_allowed=lambda target: self.frontier.in_scope(urlparse(target).netloc),
        )
        self.renderer: Renderer | None = None
        if config.render:
            require_playwright()
            self.renderer = Renderer(
                config.user_agent,
                workers=config.render_workers,
                wait=config.render_wait,
                selector=config.render_selector,
                timeout_seconds=config.render_timeout_seconds,
                block=config.render_block,
                throttle=self.fetcher.throttle,
            )
        self.extractors = compile_extractors(config.extract, config.search)

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
        sitemap_files: list[SitemapFile] = []
        sitemap_entries: list[SitemapEntry] = []
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
                await self._seed_from_sitemaps(seeds, sitemap_files, sitemap_entries)
        if self.sink is not None:
            self.sink.seeded(seeds, sitemap_files, sitemap_entries)

    async def _seed_from_sitemaps(
        self,
        seeds: list[QueueItem],
        files: list[SitemapFile],
        entries: list[SitemapEntry],
    ) -> None:
        """Read every sitemap robots.txt names (or ``/sitemap.xml``), indexes included.

        Every file tried is recorded in ``files`` with what happened to it;
        every ``<url>`` of every usable sitemap goes to ``entries`` and, when
        it is a page on this site, to the frontier at depth 0.
        """
        policy = await self.robots.policy(self.fetcher, self.start_url)
        candidates = [(url, "robots.txt") for url in policy.sitemaps()]
        if not candidates:
            candidates.append((urljoin(self.start_url, "/sitemap.xml"), "default"))
        visited: set[str] = set()
        from_sitemaps = 0
        while candidates:
            sitemap_url, found_in = candidates.pop(0)
            if sitemap_url in visited:
                continue
            visited.add(sitemap_url)
            result = await self.fetcher.fetch(sitemap_url)
            file = SitemapFile(sitemap_url, found_in, status_code=result.status_code)
            doc = None
            if result.outcome is not Outcome.FETCHED:
                file = replace(file, error=f"fetch error: {result.error}"[:200])
            elif result.status_code != 200:
                file = replace(file, error=f"status {result.status_code}")
            elif (doc := parse_sitemap(result.content, sitemap_url)) is None:
                file = replace(file, error="not sitemap XML")
            else:
                file = replace(file, kind=doc.kind, url_count=len(doc.entries))
            files.append(file)
            if doc is None:
                log.warning("sitemap %s skipped: %s", sitemap_url, file.error)
                continue
            if doc.kind == "index":
                candidates.extend((entry.loc, sitemap_url) for entry in doc.entries)
                continue
            for entry in doc.entries:
                entries.append(entry)
                item = self.frontier.add(entry.loc, 0, f"sitemap:{sitemap_url}")
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
        redirected = final is not None and final != item.url
        if final and redirected:
            record.canonical = final  # overwritten below if the page declares one

        if not self._is_parsable(result):
            return record, []

        page = parse_html(result.text, result.final_url)
        html = result.text
        # A redirect source is never audited as HTML (its content belongs to the
        # target, which is rendered on its own), so rendering it would spend a
        # browser load for nothing.
        if self.renderer is not None and not redirected:
            page, html = await self._render(record, result, page)
        if self.extractors:
            record.extractions = self.extractors.run(html)
        record.title = page.title
        record.meta_description = page.meta_description
        record.h1 = page.h1
        record.h1s = tuple(page.h1s)
        record.h2s = tuple(page.h2s)
        record.meta_robots = page.meta_robots
        record.lang = page.lang
        record.word_count = page.word_count
        record.links = tuple(page.anchors)
        record.title_count = page.title_count
        record.meta_description_count = page.meta_description_count
        record.og_url = page.og_url
        record.hreflang = tuple(page.hreflang)
        record.rel_prev = page.rel_prev
        record.rel_next = page.rel_next
        record.fingerprint = page.fingerprint
        record.canonical_header = link_header_rels(
            result.headers.get("link", ""), result.final_url
        ).get("canonical", "")
        if page.canonical:
            record.canonical = page.canonical

        internal = {self._normalize(link) for link in page.links}
        internal.discard(None)
        record.internal_links = sum(
            1 for link in internal if link and same_site(urlparse(link).netloc, page_host)
        )
        return record, page.links if self.config.follow_links else []

    async def _render(
        self, record: PageRecord, result: FetchResult, raw: ParsedPage
    ) -> tuple[ParsedPage, str]:
        """Render the page and return the parsed DOM with its HTML.

        On failure the raw parse and the raw HTML come back unchanged.
        """
        if self.renderer is None:  # pragma: no cover - callers check first
            return raw, result.text
        rendered = await self.renderer.render(result.final_url)
        record.render_ms = rendered.elapsed_ms
        if not rendered.ok:
            record.render_error = rendered.error
            log.warning("could not render %s: %s", record.url, rendered.error)
            return raw, result.text
        landed = rendered.final_url or result.final_url
        if not self.frontier.in_scope(urlparse(landed).netloc):
            # The DOM is another site's page; the HTTP redirect check above never saw it.
            record.render_error = f"JavaScript redirected off-site to {landed}"
            log.warning("could not render %s: %s", record.url, record.render_error)
            return raw, result.text
        page = parse_html(rendered.html, landed)
        record.render = diff_rendered(raw, page)
        return page, rendered.html

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
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(self.fetcher)
            if self.renderer is not None:
                await stack.enter_async_context(self.renderer)
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
        stopped = self.control.stopping
        if stopped:
            log.info("stopped on request with %d URLs unvisited", len(self.frontier))
        elif len(self.frontier):
            log.warning(
                "stopped at max_pages=%d with %d URLs unvisited",
                self.config.max_pages,
                len(self.frontier),
            )
        if self.sink is not None:
            self.sink.finish(pages_done=done, complete=len(self.frontier) == 0 and not stopped)
        return self.records

    async def _crawl_loop(self, on_progress: ProgressCallback | None, done: int) -> int:
        limit = self.config.max_pages
        control = self.control
        inflight: dict[asyncio.Task[_Processed], QueueItem] = {}
        try:
            while (len(self.frontier) or inflight) and done < limit:
                if control.stopping:
                    break
                if not control.paused:
                    while len(inflight) < self.config.workers and done + len(inflight) < limit:
                        item = self.frontier.pop()
                        if item is None:
                            break
                        inflight[asyncio.create_task(self._process(item))] = item
                if not inflight:
                    if control.paused:
                        await asyncio.sleep(POLL_SECONDS)
                        continue
                    break
                # Take one finished task at a time so ``max_pages`` is exact; wake
                # up every POLL_SECONDS to notice a pause or stop request.
                finished, _ = await asyncio.wait(
                    inflight, timeout=POLL_SECONDS, return_when=asyncio.FIRST_COMPLETED
                )
                if not finished:
                    continue
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
