"""Store writes and reads, without a crawler."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from sitecrawler.models import (
    CrawlConfig,
    LinkRef,
    Outcome,
    PageRecord,
    QueueItem,
    RedirectHop,
)
from sitecrawler.store import Store, open_store
from sitecrawler.store.schema import LinkRow, PageHtmlRow, PageRow, RedirectHopRow, SitemapUrlRow

CONFIG = CrawlConfig(start_url="https://www.x.test/")


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    s = open_store(tmp_path / "crawl.db")
    yield s
    s.close()


def _page(url: str, **extra: object) -> PageRecord:
    return PageRecord(url=url, outcome=Outcome.FETCHED, depth=0, found_on="start", **extra)  # type: ignore[arg-type]


def test_begin_creates_one_crawl(store: Store) -> None:
    state = store.begin(CONFIG, resume=False)
    assert state.done == 0
    assert state.pending == ()
    crawl = store.crawl()
    assert crawl.start_url == "https://x.test/"
    assert crawl.status == "running"
    assert '"max_pages": 5000' in crawl.config_json


def test_second_begin_without_resume_fails(store: Store) -> None:
    store.begin(CONFIG, resume=False)
    with pytest.raises(ValueError, match="already contains a crawl"):
        store.begin(CONFIG, resume=False)


def test_resume_on_empty_file_fails(store: Store) -> None:
    with pytest.raises(ValueError, match="nothing to resume"):
        store.begin(CONFIG, resume=True)


def test_resume_with_other_start_url_fails(store: Store) -> None:
    store.begin(CONFIG, resume=False)
    with pytest.raises(ValueError, match="cannot resume"):
        store.begin(CrawlConfig(start_url="https://other.test/"), resume=True)


def test_page_done_writes_every_table(store: Store) -> None:
    store.begin(CONFIG, resume=False)
    store.seeded(
        [QueueItem("https://x.test/", 0, "start"), QueueItem("https://x.test/a", 0, "sitemap:s")],
        [("https://x.test/sitemap.xml", "https://x.test/a")],
    )
    record = _page(
        "https://x.test/",
        status_code=200,
        title="Home",
        h1="H",
        h1s=("H", "H2"),
        headers={"x-robots-tag": "noindex", "last-modified": "yesterday"},
        redirect_hops=(RedirectHop(1, "https://x.test/", "https://x.test/home", 301),),
        links=(LinkRef("https://x.test/a", "A", "nofollow"), LinkRef("https://o.test/", "O")),
    )
    store.page_done(record, [QueueItem("https://x.test/b", 1, "https://x.test/")])

    with Session(store.engine) as s:
        pages = {p.url: p for p in s.scalars(select(PageRow))}
        assert set(pages) == {"https://x.test/", "https://x.test/a", "https://x.test/b"}
        assert pages["https://x.test/"].state == "done"
        assert pages["https://x.test/"].x_robots_tag == "noindex"
        assert pages["https://x.test/"].last_modified == "yesterday"
        assert pages["https://x.test/a"].state == "pending"
        assert pages["https://x.test/b"].state == "pending"
        assert s.scalar(select(RedirectHopRow.to_url)) == "https://x.test/home"
        html = s.scalars(select(PageHtmlRow)).one()
        assert html.title == "Home"
        assert html.h1s_json == '["H", "H2"]'
        links = s.scalars(select(LinkRow).order_by(LinkRow.id)).all()
        assert [(link.dst_url, link.nofollow, link.is_internal) for link in links] == [
            ("https://x.test/a", True, True),
            ("https://o.test/", False, False),
        ]
        assert s.scalars(select(SitemapUrlRow.loc)).all() == ["https://x.test/a"]
    assert store.count_pages() == 3
    assert store.count_pages("done") == 1


def test_blocked_page_has_no_html_row(store: Store) -> None:
    store.begin(CONFIG, resume=False)
    store.page_done(
        PageRecord(url="https://x.test/b", outcome=Outcome.BLOCKED, depth=0, found_on="s"), []
    )
    with Session(store.engine) as s:
        assert s.scalars(select(PageHtmlRow)).first() is None


def test_resume_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "r.db"
    with open_store(path) as store:
        store.begin(CONFIG, resume=False)
        store.seeded([QueueItem("https://x.test/", 0, "start")], [])
        store.page_done(
            _page("https://x.test/", status_code=200),
            [
                QueueItem("https://x.test/p1", 1, "https://x.test/"),
                QueueItem("https://x.test/p2", 1, "https://x.test/"),
            ],
        )
    with open_store(path) as store:
        state = store.begin(CONFIG, resume=True)
    assert state.done == 1
    assert state.seen == {"https://x.test/", "https://x.test/p1", "https://x.test/p2"}
    assert [i.url for i in state.pending] == ["https://x.test/p1", "https://x.test/p2"]
    assert state.pending[0].depth == 1


def test_iter_pages_rebuilds_records_sorted(store: Store) -> None:
    store.begin(CONFIG, resume=False)
    store.page_done(
        _page(
            "https://x.test/z",
            status_code=200,
            title="Z",
            word_count=3,
            internal_links=2,
            h2s=("sub",),
            lang="en",
            redirect_hops=(RedirectHop(1, "https://x.test/z", "https://x.test/zz", 302),),
            links=(LinkRef("https://x.test/a", "A"),),
        ),
        [],
    )
    store.page_done(
        PageRecord(
            url="https://x.test/a",
            outcome=Outcome.REDIRECT_LOOP,
            depth=1,
            found_on="z",
            error="loop",
        ),
        [],
    )
    records = list(store.iter_pages())
    assert [r.url for r in records] == ["https://x.test/a", "https://x.test/z"]
    assert records[0].status == "redirect_loop"
    z = records[1]
    assert z.title == "Z"
    assert z.word_count == 3
    assert z.internal_links == 2
    assert z.h2s == ("sub",)
    assert z.lang == "en"
    assert z.redirect_hops[0].to_url == "https://x.test/zz"
    assert z.links[0].href == "https://x.test/a"


def test_finish_marks_done(store: Store) -> None:
    store.begin(CONFIG, resume=False)
    store.finish(pages_done=7, complete=True)
    crawl = store.crawl()
    assert crawl.status == "done"
    assert crawl.pages_done == 7
    assert crawl.finished_at is not None


def test_finish_incomplete_is_stopped(store: Store) -> None:
    store.begin(CONFIG, resume=False)
    store.finish(pages_done=2, complete=False)
    assert store.crawl().status == "stopped"


def test_issues_for_unknown_urls_are_dropped_with_a_warning(
    store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    from sitecrawler.models import Issue, Severity

    store.begin(CONFIG, resume=False)
    store.page_done(_page("https://x.test/", status_code=200), [])
    issues = [
        Issue("https://x.test/", "r.one", Severity.LOW),
        Issue("https://x.test/not-crawled", "r.one", Severity.LOW),
    ]
    assert store.replace_issues(issues) == 1
    assert "1 issue(s) refer to URLs that are not in this crawl" in caplog.text


def test_writing_before_begin_fails(store: Store) -> None:
    with pytest.raises(RuntimeError, match="begin"):
        store.seeded([QueueItem("https://x.test/", 0, "start")], [])
