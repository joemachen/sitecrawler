"""The crawl loop: pull from the frontier, fetch, parse, feed links back."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests

from sitecrawler.crawl.fetcher import Fetcher
from sitecrawler.crawl.frontier import Frontier
from sitecrawler.crawl.robots import RobotsPolicy
from sitecrawler.crawl.urls import normalize, same_site
from sitecrawler.models import CrawlConfig, FetchResult, Outcome, PageRecord, QueueItem
from sitecrawler.parse import parse_html, parse_sitemap

log = logging.getLogger(__name__)

ProgressCallback = Callable[[PageRecord, int, int], None]
"""Called after each page with (record, pages_done, pages_queued)."""


class Crawler:
    """Breadth-first crawler for a single site.

    Usage::

        records = Crawler(CrawlConfig(start_url="https://example.com")).run()
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
        self.fetcher = Fetcher(config.user_agent, config.delay_seconds, config.timeout_seconds)
        self.robots = RobotsPolicy(config.user_agent)
        self.records: list[PageRecord] = []

    # ------------------------------------------------------------------ setup
    def _seed(self) -> None:
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
            self.fetcher.throttle()
            try:
                response = self.fetcher.session.get(
                    sitemap_url, timeout=self.config.timeout_seconds
                )
            except requests.RequestException:
                continue
            if not response.ok:
                continue
            doc = parse_sitemap(response.content)
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
    def _process(self, item: QueueItem) -> tuple[PageRecord, list[str]]:
        """Fetch and parse one URL. Returns the record and the raw links found."""
        record = PageRecord(
            url=item.url, outcome=Outcome.FETCHED, depth=item.depth, found_on=item.found_on
        )
        if self.config.respect_robots and not self.robots.allowed(item.url):
            record.outcome = Outcome.BLOCKED
            record.error = "disallowed by robots.txt"
            return record, []

        result = self.fetcher.fetch(item.url)
        record.outcome = result.outcome
        record.status_code = result.status_code
        record.content_type = result.content_type
        record.fetch_ms = result.elapsed_ms
        record.error = result.error
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
        if self.config.respect_robots:
            self.robots.load(self.fetcher.session, self.start_url, self.config.timeout_seconds)
        self._seed()

        done = 0
        limit = self.config.max_pages
        with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
            inflight: dict[Future[tuple[PageRecord, list[str]]], QueueItem] = {}
            while (len(self.frontier) or inflight) and done < limit:
                while len(inflight) < self.config.workers and done + len(inflight) < limit:
                    item = self.frontier.pop()
                    if item is None:
                        break
                    inflight[pool.submit(self._process, item)] = item
                if not inflight:
                    break
                future = next(as_completed(list(inflight)))
                inflight.pop(future)
                record, links = future.result()
                self.records.append(record)
                done += 1
                for link in links:
                    self.frontier.add(link, record.depth + 1, record.url)
                if on_progress is not None:
                    on_progress(record, done, len(self.frontier))

        self.records.sort(key=lambda r: r.url)
        if len(self.frontier):
            log.warning("stopped at max_pages=%d with %d URLs unvisited", limit, len(self.frontier))
        return self.records
