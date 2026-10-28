"""Renderer option validation and the Playwright guard, without a browser."""

from __future__ import annotations

import asyncio

import pytest

from sitecrawler.crawl import Crawler, Renderer, RenderUnavailableError
from sitecrawler.crawl.renderer import (
    FROZEN_HINT,
    INSTALL_HINT,
    WAIT_STRATEGIES,
    render_unavailable_reason,
    require_playwright,
)
from sitecrawler.models import CrawlConfig


def test_wait_strategy_is_validated() -> None:
    for wait in WAIT_STRATEGIES:
        assert Renderer("ua", wait=wait).wait == wait
    with pytest.raises(ValueError, match="render_wait must be one of"):
        Renderer("ua", wait="eventually")
    with pytest.raises(ValueError, match="render_workers"):
        Renderer("ua", workers=0)
    # Playwright reads timeout=0 as "no timeout", which would hang the crawl on one page.
    with pytest.raises(ValueError, match="render_timeout must be above 0"):
        Renderer("ua", timeout_seconds=0)
    with pytest.raises(ValueError, match="render_timeout"):
        Renderer("ua", timeout_seconds=-1)


def test_blocked_resource_types() -> None:
    renderer = Renderer("ua", block=("image", "font"))
    assert renderer.should_block("image")
    assert not renderer.should_block("document")
    assert not Renderer("ua", block=()).should_block("image")


def test_render_before_entering_is_a_programming_error() -> None:
    with pytest.raises(RuntimeError, match="async with"):
        asyncio.run(Renderer("ua").render("https://x.test/"))


def test_missing_playwright_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sitecrawler.crawl.renderer.playwright_available", lambda: False)
    with pytest.raises(RenderUnavailableError, match="playwright install chromium"):
        require_playwright()
    with pytest.raises(ValueError, match=INSTALL_HINT[:30]):
        Crawler(CrawlConfig(start_url="https://x.test/", render=True))
    assert Crawler(CrawlConfig(start_url="https://x.test/")).renderer is None


def test_the_exe_says_rendering_is_not_included(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sitecrawler.crawl.renderer.playwright_available", lambda: False)
    assert render_unavailable_reason() == INSTALL_HINT
    # PyInstaller sets sys.frozen; uv and pip instructions mean nothing to someone running the exe.
    monkeypatch.setattr("sys.frozen", True, raising=False)
    assert render_unavailable_reason() == FROZEN_HINT
    with pytest.raises(RenderUnavailableError, match="not included in the standalone"):
        require_playwright()
    monkeypatch.setattr("sitecrawler.crawl.renderer.playwright_available", lambda: True)
    assert render_unavailable_reason() is None


def test_crawler_builds_a_renderer_from_the_config() -> None:
    config = CrawlConfig(
        start_url="https://x.test/",
        render=True,
        render_workers=3,
        render_wait="load",
        render_selector="#app",
        render_timeout_seconds=5,
        render_block=("font",),
    )
    crawler = Crawler(config)
    renderer = crawler.renderer
    assert renderer is not None
    assert (renderer.workers, renderer.wait, renderer.selector) == (3, "load", "#app")
    assert renderer.timeout_seconds == 5
    assert renderer.block == {"font"}
    assert renderer.throttle is crawler.fetcher.throttle
    with pytest.raises(ValueError, match="render_wait"):
        Crawler(CrawlConfig(start_url="https://x.test/", render=True, render_wait="never"))
