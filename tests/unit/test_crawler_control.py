"""Pause and stop requests reach the crawl loop between fetches, without a network."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from types import TracebackType

import pytest

from sitecrawler.crawl import CrawlControl, Crawler
from sitecrawler.models import (
    CrawlConfig,
    FetchResult,
    Outcome,
    PageRecord,
    QueueItem,
    ResumeState,
    SitemapEntry,
    SitemapFile,
)

SITE = "https://x.test"


class SlowFetcher:
    """Serves ``/p0`` .. ``/p{n-1}``; each page links to the next two. Stands in for ``Fetcher``."""

    def __init__(self, pages: int, delay: float) -> None:
        self.pages = pages
        self.delay = delay

    async def __aenter__(self) -> SlowFetcher:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def fetch(self, url: str) -> FetchResult:
        await asyncio.sleep(self.delay)
        n = int(url.rsplit("/p", 1)[1])
        links = "".join(f'<a href="/p{i}">next</a>' for i in (n + 1, n + 2) if i < self.pages)
        return FetchResult(
            url=url,
            outcome=Outcome.FETCHED,
            status_code=200,
            final_url=url,
            content_type="text/html",
            text=f"<html><head><title>Page {n}</title></head><body>{links}</body></html>",
        )


@dataclass
class RecordingSink:
    records: list[PageRecord] = field(default_factory=list)
    finished: tuple[int, bool] | None = None

    def begin(self, config: CrawlConfig, *, resume: bool) -> ResumeState:
        return ResumeState()

    def seeded(
        self,
        items: Sequence[QueueItem],
        sitemap_files: Sequence[SitemapFile],
        sitemap_entries: Sequence[SitemapEntry],
    ) -> None:
        return None

    def page_done(self, record: PageRecord, discovered: Sequence[QueueItem]) -> None:
        self.records.append(record)

    def finish(self, *, pages_done: int, complete: bool) -> None:
        self.finished = (pages_done, complete)


def _crawler(
    pages: int, delay: float, sink: RecordingSink, control: CrawlControl, *, workers: int = 1
) -> Crawler:
    config = CrawlConfig(
        start_url=f"{SITE}/p0",
        delay_seconds=0,
        workers=workers,
        respect_robots=False,
        use_sitemap=False,
    )
    crawler = Crawler(config, sink=sink, control=control)
    crawler.fetcher = SlowFetcher(pages, delay)  # type: ignore[assignment]
    return crawler


async def _wait_for(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            pytest.fail("condition not reached in time")
        await asyncio.sleep(0.005)


async def test_default_control_changes_nothing() -> None:
    sink = RecordingSink()
    records = await _crawler(5, 0, sink, CrawlControl()).arun()
    assert len(records) == 5
    assert sink.finished == (5, True)


async def test_stop_ends_the_crawl_and_marks_it_incomplete() -> None:
    sink, control = RecordingSink(), CrawlControl()
    task = asyncio.create_task(_crawler(20, 0.02, sink, control).arun())
    await _wait_for(lambda: len(sink.records) >= 3)

    control.stop()
    records = await task

    assert 3 <= len(records) < 20
    assert sink.finished == (len(records), False)


async def test_pause_holds_scheduling_and_resume_continues() -> None:
    sink, control = RecordingSink(), CrawlControl()
    task = asyncio.create_task(_crawler(20, 0.02, sink, control, workers=2).arun())
    await _wait_for(lambda: len(sink.records) >= 2)

    before = len(sink.records)
    control.pause()
    await asyncio.sleep(0.3)  # long enough for ~15 more fetches, were it running
    held = len(sink.records)
    assert held <= before + 2, "only the two fetches already in flight may complete"
    await asyncio.sleep(0.1)
    assert len(sink.records) == held
    assert not task.done()

    control.resume()
    records = await task
    assert len(records) == 20
    assert sink.finished == (20, True)


async def test_stop_with_empty_frontier_but_a_fetch_in_flight_is_incomplete() -> None:
    sink, control = RecordingSink(), CrawlControl()
    task = asyncio.create_task(_crawler(1, 0.5, sink, control).arun())
    await asyncio.sleep(0.05)

    control.stop()
    records = await task

    assert records == []
    assert sink.finished == (0, False)


async def test_stop_while_paused_ends_promptly() -> None:
    sink, control = RecordingSink(), CrawlControl()
    task = asyncio.create_task(_crawler(20, 0.02, sink, control).arun())
    await _wait_for(lambda: len(sink.records) >= 1)
    control.pause()
    await asyncio.sleep(0.1)

    control.stop()
    await asyncio.wait_for(task, timeout=2.0)

    assert sink.finished is not None
    assert sink.finished[1] is False
