"""Crawl the fixture site into a SQLite store, crash, and resume."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer
from sqlalchemy import select
from sqlalchemy.orm import Session

from sitecrawler.crawl import Crawler
from sitecrawler.models import CrawlConfig, PageRecord
from sitecrawler.store import open_store
from sitecrawler.store.schema import PageRow, RedirectHopRow, SitemapUrlRow


def _config(site: str, **extra: object) -> CrawlConfig:
    return CrawlConfig(start_url=site, delay_seconds=0, workers=1, **extra)  # type: ignore[arg-type]


# Pages that other fixture pages redirect to; a resumed run may request them
# while following a hop even though the page itself was fetched earlier.
_REDIRECT_TARGETS = {"/about", "/redirect-middle", "/blog/"}


def _requested_paths(httpserver: HTTPServer) -> set[str]:
    return {request.path for request, _ in httpserver.log} - _REDIRECT_TARGETS


def test_full_crawl_is_stored(site: str, tmp_path: Path) -> None:
    with open_store(tmp_path / "c.db") as store:
        records = Crawler(_config(site), sink=store).run()
        assert store.count_pages("done") == len(records) == 13
        assert store.count_pages("pending") == 0
        stored = {r.url.removeprefix(site): r for r in store.iter_pages()}
        crawl = store.crawl()
    assert crawl.status == "done"
    assert crawl.pages_done == 13
    assert stored["/about"].title == "About the Fixture Site"
    assert stored["/about"].internal_links == 2
    assert stored["/orphan"].found_on.startswith("sitemap:")
    assert stored["/loop-a"].status == "redirect_loop"


def test_redirect_chain_yields_two_hop_rows(site: str, tmp_path: Path) -> None:
    with open_store(tmp_path / "c.db") as store:
        Crawler(_config(site), sink=store).run()
        with Session(store.engine) as s:
            page = s.scalars(select(PageRow).where(PageRow.url == f"{site}/redirect-start")).one()
            hops = s.scalars(
                select(RedirectHopRow)
                .where(RedirectHopRow.page_id == page.id)
                .order_by(RedirectHopRow.hop_no)
            ).all()
    assert [(h.hop_no, h.status_code) for h in hops] == [(1, 302), (2, 302)]
    assert hops[0].to_url == f"{site}/redirect-middle"
    assert hops[1].to_url == f"{site}/about"


def test_headers_and_sitemap_urls_are_stored(site: str, tmp_path: Path) -> None:
    with open_store(tmp_path / "c.db") as store:
        Crawler(_config(site), sink=store).run()
        with Session(store.engine) as s:
            notitle = s.scalars(select(PageRow).where(PageRow.url == f"{site}/notitle")).one()
            assert notitle.x_robots_tag == "noindex"
            assert notitle.last_modified == "Wed, 21 Oct 2026 10:00:00 GMT"
            locs = set(s.scalars(select(SitemapUrlRow.loc)))
    assert locs == {f"{site}/", f"{site}/about", f"{site}/orphan", f"{site}/blocked/secret"}


def test_resume_after_crash_does_not_refetch(
    site: str, tmp_path: Path, httpserver: HTTPServer
) -> None:
    path = tmp_path / "c.db"
    done_first: list[str] = []

    def crash_after_three(record: PageRecord, done: int, queued: int) -> None:
        done_first.append(record.url)
        if done == 3:
            msg = "simulated crash"
            raise RuntimeError(msg)

    with open_store(path) as store, pytest.raises(RuntimeError, match="simulated crash"):
        Crawler(_config(site), sink=store).run(on_progress=crash_after_three)
    assert len(done_first) == 3

    httpserver.clear_log()
    with open_store(path) as store:
        second = Crawler(_config(site), sink=store, resume=True).run()
        assert store.count_pages("done") == 13
        assert store.count_pages("pending") == 0
        assert store.crawl().status == "done"
    assert len(second) == 10
    assert not set(done_first) & {r.url for r in second}

    requested = _requested_paths(httpserver)
    assert "/sitemap.xml" not in requested
    assert not {u.removeprefix(site) for u in done_first} & requested
    assert "/robots.txt" in requested


def test_resume_after_max_pages(site: str, tmp_path: Path, httpserver: HTTPServer) -> None:
    path = tmp_path / "c.db"
    with open_store(path) as store:
        first = Crawler(_config(site, max_pages=4), sink=store).run()
        assert store.count_pages("pending") > 0
    httpserver.clear_log()
    with open_store(path) as store:
        second = Crawler(_config(site, max_pages=100), sink=store, resume=True).run()
        assert store.count_pages("done") == 13
    assert len(first) + len(second) == 13
    assert not {r.url for r in first} & {r.url for r in second}
    assert not {r.url.removeprefix(site) for r in first} & _requested_paths(httpserver)


def test_resume_with_different_start_url_fails(site: str, tmp_path: Path) -> None:
    path = tmp_path / "c.db"
    with open_store(path) as store:
        Crawler(_config(site, max_pages=2), sink=store).run()
    with open_store(path) as store, pytest.raises(ValueError, match="cannot resume"):
        Crawler(_config(f"{site}/blog"), sink=store, resume=True).run()


def test_resume_without_sink_is_rejected(site: str) -> None:
    with pytest.raises(ValueError, match="needs a sink"):
        Crawler(_config(site), resume=True)
