"""Crawl the fixture site end to end through the library API."""

from __future__ import annotations

import pytest

from sitecrawler.crawl import Crawler
from sitecrawler.models import CrawlConfig, Outcome, PageRecord


@pytest.fixture
def crawled(site: str) -> dict[str, PageRecord]:
    config = CrawlConfig(start_url=site, delay_seconds=0, workers=2)
    records = Crawler(config).run()
    return {r.url.removeprefix(site): r for r in records}


def test_discovers_every_in_scope_page(crawled: dict[str, PageRecord]) -> None:
    assert set(crawled) == {
        "/",
        "/about",
        "/blog",
        "/blog/post-1",
        "/blog/post-2",
        "/notitle",
        "/dup-title-1",
        "/dup-title-2",
        "/redirect-start",
        "/loop-a",
        "/missing",
        "/blocked/secret",
        "/orphan",  # sitemap only
    }


def test_ignores_out_of_scope_links(crawled: dict[str, PageRecord]) -> None:
    assert not any(url.endswith((".pdf", ".png")) for url in crawled)
    assert "/blocked/deeper" not in crawled  # never fetched the blocked page, so never saw it


def test_statuses(crawled: dict[str, PageRecord]) -> None:
    assert crawled["/"].status_code == 200
    assert crawled["/missing"].status_code == 404
    assert crawled["/blocked/secret"].outcome is Outcome.BLOCKED
    assert crawled["/blocked/secret"].status_code is None
    assert crawled["/loop-a"].outcome is Outcome.ERROR
    assert "redirect" in crawled["/loop-a"].error.lower()


def test_redirect_chain_resolves_to_final_url(crawled: dict[str, PageRecord], site: str) -> None:
    hop = crawled["/redirect-start"]
    assert hop.status_code == 200
    # the page at the end declares its own canonical, which wins
    assert hop.canonical == "https://www.fixture.test/about"
    assert hop.title == "About the Fixture Site"


def test_parsed_fields(crawled: dict[str, PageRecord]) -> None:
    about = crawled["/about"]
    assert about.title == "About the Fixture Site"
    assert about.meta_description == "Who we are and what we do."
    assert about.h1 == "About us"
    assert about.word_count == 20
    assert about.internal_links == 2

    home = crawled["/"]
    # 12 page anchors collapse to 9 distinct URLs, plus the same-site PDF and image links.
    assert home.internal_links == 11
    assert "ignored" not in home.title

    assert crawled["/notitle"].title == ""


def test_depth_and_provenance(crawled: dict[str, PageRecord], site: str) -> None:
    assert crawled["/"].depth == 0
    assert crawled["/orphan"].depth == 0
    assert crawled["/orphan"].found_on.startswith("sitemap:")
    assert crawled["/blog/post-2"].depth == 2
    assert crawled["/blog/post-2"].found_on == f"{site}/blog"


def test_max_pages_caps_the_crawl(site: str) -> None:
    records = Crawler(CrawlConfig(start_url=site, max_pages=3, delay_seconds=0)).run()
    assert len(records) == 3


def test_no_sitemap_means_no_orphan(site: str) -> None:
    records = Crawler(CrawlConfig(start_url=site, use_sitemap=False, delay_seconds=0)).run()
    assert not any(r.url.endswith("/orphan") for r in records)


def test_ignore_robots_fetches_blocked_page(site: str) -> None:
    records = Crawler(CrawlConfig(start_url=site, respect_robots=False, delay_seconds=0)).run()
    by_path = {r.url.removeprefix(site): r for r in records}
    assert by_path["/blocked/secret"].status_code == 200
    assert "/blocked/deeper" in by_path


def test_invalid_start_url() -> None:
    with pytest.raises(ValueError, match="Invalid start URL"):
        Crawler(CrawlConfig(start_url="not a url"))
