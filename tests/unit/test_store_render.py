"""The page_render table round-trips a RenderDiff or a render failure."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from sitecrawler.models import CrawlConfig, Outcome, PageRecord, RenderDiff
from sitecrawler.store import Store, open_store
from sitecrawler.store.dump import PAGE_COLUMNS, dump_tables
from sitecrawler.store.schema import PageRenderRow

CONFIG = CrawlConfig(start_url="https://x.test/", render=True)
DIFF = RenderDiff(
    raw_title="Raw",
    rendered_title="Rendered",
    raw_canonical="",
    rendered_canonical="https://x.test/a",
    raw_word_count=10,
    rendered_word_count=12,
    raw_link_count=1,
    rendered_link_count=3,
    links_added=("https://x.test/b", "https://x.test/c"),
)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with open_store(tmp_path / "c.db") as s:
        s.begin(CONFIG, resume=False)
        yield s


def _page(path: str, **fields: object) -> PageRecord:
    return PageRecord(
        url=f"https://x.test{path}",
        outcome=Outcome.FETCHED,
        depth=0,
        found_on="start",
        status_code=200,
        content_type="text/html",
        final_url=f"https://x.test{path}",
        **fields,  # type: ignore[arg-type]
    )


def test_diff_and_failure_round_trip(store: Store) -> None:
    store.page_done(_page("/a", title="Rendered", render=DIFF, render_ms=120), [])
    store.page_done(_page("/b", render_error="render timed out after 5s", render_ms=5000), [])
    store.page_done(_page("/c"), [])

    with Session(store.engine) as s:
        rows = {r.page_id: r for r in s.scalars(select(PageRenderRow))}
        assert len(rows) == 2
    records = {r.url.removeprefix("https://x.test"): r for r in store.iter_pages()}
    assert records["/a"].render == DIFF
    assert records["/a"].render_ms == 120
    assert records["/a"].rendered
    assert records["/b"].render is None
    assert records["/b"].render_error == "render timed out after 5s"
    assert records["/b"].render_ms == 5000
    assert not records["/b"].rendered
    assert records["/c"].render is None
    assert records["/c"].render_error == ""

    pages = dump_tables(store, ("pages",))[0]
    assert pages.columns == PAGE_COLUMNS
    cells = {row[0]: dict(zip(pages.columns, row, strict=True)) for row in pages.rows}
    assert cells["https://x.test/a"]["render_status"] == "rendered"
    assert cells["https://x.test/a"]["render_changes"] == "title, canonical, links +2"
    assert cells["https://x.test/b"]["render_status"] == "failed"
    assert cells["https://x.test/b"]["render_changes"] == "render timed out after 5s"
    assert cells["https://x.test/c"]["render_status"] == ""


def test_render_config_survives_the_json_round_trip(store: Store) -> None:
    from sitecrawler.session import _config_from_json

    info = store.crawl()
    config = _config_from_json(info.start_url, info.config_json)
    assert config == CONFIG
    assert config.render_block == ("image", "font", "media")
