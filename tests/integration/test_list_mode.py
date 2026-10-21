"""List mode: fetch exactly the given URLs, optionally following links."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pytest_httpserver import HTTPServer

from sitecrawler.crawl import Crawler
from sitecrawler.models import CrawlConfig, Outcome


def _config(seeds: list[str], *, follow_links: bool = True) -> CrawlConfig:
    return CrawlConfig(
        start_url="",
        seed_urls=tuple(seeds),
        follow_links=follow_links,
        delay_seconds=0,
        workers=1,
        use_sitemap=False,
    )


def test_fetches_exactly_the_listed_urls(site: str, httpserver: HTTPServer) -> None:
    seeds = [f"{site}/", f"{site}/about", f"{site}/orphan", f"{site}/blocked/secret"]
    records = Crawler(_config(seeds, follow_links=False)).run()

    assert sorted(r.url for r in records) == sorted(seeds)
    by_path = {r.url.removeprefix(site): r for r in records}
    assert by_path["/about"].title == "About the Fixture Site"
    assert by_path["/blocked/secret"].outcome is Outcome.BLOCKED
    assert all(r.found_on == "list" and r.depth == 0 for r in records)
    requested = {request.path for request, _ in httpserver.log}
    assert requested == {"/robots.txt", "/", "/about", "/orphan"}


def test_follow_stays_on_listed_hosts(site: str) -> None:
    records = Crawler(_config([f"{site}/blog/"], follow_links=True)).run()
    paths = {r.url.removeprefix(site) for r in records}
    assert {"/blog", "/blog/post-1", "/blog/post-2"} <= paths
    assert "/orphan" not in paths  # no sitemap seeding in list mode


def test_invalid_seed_is_rejected_before_any_request(httpserver: HTTPServer) -> None:
    with pytest.raises(ValueError, match="line 2: 'nope'"):
        Crawler(_config(["https://a.test/", "nope"]))
    assert httpserver.log == []


def test_empty_list_is_rejected() -> None:
    config = CrawlConfig(start_url="", seed_urls=(), delay_seconds=0)
    with pytest.raises(ValueError, match="Invalid start URL"):
        Crawler(config)


@pytest.fixture
def second_site() -> Iterator[HTTPServer]:
    server = HTTPServer(host="127.0.0.1", port=0)
    server.start()
    server.expect_request("/robots.txt").respond_with_data(
        b"User-agent: *\nDisallow: /private\n", content_type="text/plain"
    )
    server.expect_request("/").respond_with_data(
        b'<html><title>Second</title><a href="/private/x">p</a><a href="/open">o</a></html>',
        content_type="text/html",
    )
    server.expect_request("/open").respond_with_data(
        b"<title>Open</title>", content_type="text/html"
    )
    try:
        yield server
    finally:
        server.stop()


def test_two_hosts_each_get_their_own_robots(site: str, second_site: HTTPServer) -> None:
    other = second_site.url_for("/").rstrip("/")
    seeds = [f"{site}/blocked/secret", f"{other}/", f"{other}/private/x"]
    records = Crawler(_config(seeds, follow_links=True)).run()
    by_url = {r.url: r for r in records}

    assert by_url[f"{site}/blocked/secret"].outcome is Outcome.BLOCKED
    assert by_url[f"{other}/private/x"].outcome is Outcome.BLOCKED
    assert by_url[f"{other}/"].title == "Second"
    assert by_url[f"{other}/open"].title == "Open"  # followed, same host
    assert by_url[f"{other}/"].internal_links == 2  # counted against the page's own host
    assert f"{site}/blocked/deeper" not in by_url  # blocked page's links never seen
