"""The crawl loop feeds rendered HTML to the parser and the frontier, with fakes for both ends."""

from __future__ import annotations

from types import TracebackType

import pytest

from sitecrawler.crawl import Crawler
from sitecrawler.models import CrawlConfig, FetchResult, Outcome, PageRecord, RenderResult

SITE = "https://x.test"

RAW = {
    "/": '<html><head><title>Raw home</title></head><body><a href="/raw">raw</a></body></html>',
    "/raw": "<html><head><title>Raw page</title></head><body></body></html>",
    "/js-only": "<html><head><title>JS only</title></head><body></body></html>",
}
RENDERED = {
    "/": (
        "<html><head><title>Rendered home</title>"
        '<link rel="canonical" href="/"></head>'
        '<body><a href="/raw">raw</a><a href="/js-only">js</a></body></html>'
    ),
}


class FakeFetcher:
    """Serves ``RAW``; stands in for ``Fetcher``."""

    async def __aenter__(self) -> FakeFetcher:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def fetch(self, url: str) -> FetchResult:
        path = url.removeprefix(SITE)
        if path not in RAW:
            return FetchResult(url=url, outcome=Outcome.FETCHED, status_code=404, final_url=url)
        return FetchResult(
            url=url,
            outcome=Outcome.FETCHED,
            status_code=200,
            final_url=url,
            content_type="text/html",
            text=RAW[path],
        )


class FakeRenderer:
    """Returns ``RENDERED`` where it has an entry, the raw HTML otherwise; fails on demand."""

    def __init__(self, *, fail: str = "") -> None:
        self.fail = fail
        self.rendered: list[str] = []
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> FakeRenderer:
        self.entered += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.exited += 1

    async def render(self, url: str) -> RenderResult:
        self.rendered.append(url)
        path = url.removeprefix(SITE)
        if path == self.fail:
            return RenderResult(url=url, ok=False, elapsed_ms=7, error="render timed out")
        return RenderResult(
            url=url, ok=True, html=RENDERED.get(path, RAW[path]), final_url=url, elapsed_ms=12
        )


def _crawl(renderer: FakeRenderer) -> dict[str, PageRecord]:
    config = CrawlConfig(start_url=f"{SITE}/", use_sitemap=False, delay_seconds=0, workers=1)
    crawler = Crawler(config)
    crawler.fetcher = FakeFetcher()  # type: ignore[assignment]
    crawler.renderer = renderer  # type: ignore[assignment]
    return {r.url.removeprefix(SITE): r for r in crawler.run()}


def test_rendered_fields_replace_raw_ones_and_rendered_links_are_crawled() -> None:
    renderer = FakeRenderer()
    by_path = _crawl(renderer)
    assert set(by_path) == {"/", "/raw", "/js-only"}, "the JS-only link was followed"
    home = by_path["/"]
    assert home.title == "Rendered home"
    assert home.canonical == f"{SITE}/"
    assert home.render_ms == 12
    diff = home.render
    assert diff is not None
    assert (diff.raw_title, diff.rendered_title) == ("Raw home", "Rendered home")
    assert diff.links_added == (f"{SITE}/js-only",)
    assert diff.changes == ("title", "canonical", "links")
    raw_diff = by_path["/raw"].render
    assert raw_diff is not None
    assert not raw_diff.changed
    assert (renderer.entered, renderer.exited) == (1, 1)
    assert sorted(renderer.rendered) == [f"{SITE}/", f"{SITE}/js-only", f"{SITE}/raw"]


def test_render_failure_keeps_the_raw_parse_and_records_the_error() -> None:
    by_path = _crawl(FakeRenderer(fail="/"))
    home = by_path["/"]
    assert home.outcome is Outcome.FETCHED
    assert home.title == "Raw home"
    assert home.render is None
    assert home.render_error == "render timed out"
    assert home.render_ms == 7
    assert set(by_path) == {"/", "/raw"}, "only the raw links were followed"
    assert by_path["/raw"].render is not None


def test_non_html_pages_are_not_rendered() -> None:
    renderer = FakeRenderer()
    crawler = Crawler(
        CrawlConfig(seed_urls=(f"{SITE}/", f"{SITE}/missing"), follow_links=False, delay_seconds=0)
    )
    crawler.fetcher = FakeFetcher()  # type: ignore[assignment]
    crawler.renderer = renderer  # type: ignore[assignment]
    records = {r.url.removeprefix(SITE): r for r in crawler.run()}
    assert records["/missing"].status_code == 404
    assert records["/missing"].render is None
    assert renderer.rendered == [f"{SITE}/"]


@pytest.mark.parametrize("workers", [1, 3])
def test_renderer_is_closed_when_the_crawl_stops_early(workers: int) -> None:
    renderer = FakeRenderer()
    config = CrawlConfig(
        start_url=f"{SITE}/", use_sitemap=False, delay_seconds=0, workers=workers, max_pages=1
    )
    crawler = Crawler(config)
    crawler.fetcher = FakeFetcher()  # type: ignore[assignment]
    crawler.renderer = renderer  # type: ignore[assignment]
    assert len(crawler.run()) == 1
    assert (renderer.entered, renderer.exited) == (1, 1)
