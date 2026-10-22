"""The extractions table round-trips results and widens the pages dump."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from sitecrawler.models import (
    CrawlConfig,
    Extraction,
    ExtractorSpec,
    Outcome,
    PageRecord,
    SearchSpec,
)
from sitecrawler.session import CrawlSession
from sitecrawler.store import Store, open_store
from sitecrawler.store.dump import EXPORT_TABLES, PAGE_COLUMNS, dump_tables
from sitecrawler.store.schema import ExtractionRow

CONFIG = CrawlConfig(
    start_url="https://x.test/",
    extract=(ExtractorSpec("price", "css", ".price"), ExtractorSpec("ga", "regex", "G-[A-Z0-9]+")),
    search=(SearchSpec("gtag", "gtag"),),
)
FOUND = (
    Extraction("price", "css", ("$19.99",), 2),
    Extraction("ga", "regex", ("G-7F3K9Q2M1X",), 1),
    Extraction("gtag", "search", ("gtag",), 3),
)
MISSING = (
    Extraction("price", "css", ("$5.50",), 1),
    Extraction("ga", "regex", (), 0),
    Extraction("gtag", "search", (), 0),
)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with open_store(tmp_path / "c.db") as s:
        s.begin(CONFIG, resume=False)
        yield s


def _page(path: str, content_type: str = "text/html", **fields: object) -> PageRecord:
    return PageRecord(
        url=f"https://x.test{path}",
        outcome=Outcome.FETCHED,
        depth=0,
        found_on="start",
        status_code=200,
        content_type=content_type,
        final_url=f"https://x.test{path}",
        **fields,  # type: ignore[arg-type]
    )


def test_extractions_round_trip(store: Store) -> None:
    store.page_done(_page("/a", extractions=FOUND), [])
    store.page_done(_page("/b", extractions=MISSING), [])
    store.page_done(_page("/c.pdf", content_type="application/pdf"), [])

    with Session(store.engine) as s:
        stored = s.scalars(
            select(ExtractionRow.values_json).where(ExtractionRow.name == "ga")
        ).all()
    assert stored == ['["G-7F3K9Q2M1X"]', "[]"]
    records = {r.url.removeprefix("https://x.test"): r for r in store.iter_pages()}
    assert records["/a"].extractions == FOUND
    assert records["/b"].extractions == MISSING
    assert records["/c.pdf"].extractions == ()
    assert store.extraction_names() == [("price", "css"), ("ga", "regex"), ("gtag", "search")]
    assert store.extraction_columns() == ["extract_price", "extract_ga", "search_gtag"]


def test_pages_dump_appends_one_column_per_name(store: Store) -> None:
    store.page_done(_page("/a", extractions=FOUND), [])
    store.page_done(_page("/b", extractions=MISSING), [])
    store.page_done(_page("/c.pdf", content_type="application/pdf"), [])

    pages, extractions = dump_tables(store, ("pages", "extractions"))
    assert pages.columns == (*PAGE_COLUMNS, "extract_price", "extract_ga", "search_gtag")
    by_url = {row[0]: row[len(PAGE_COLUMNS) :] for row in pages.rows}
    assert by_url["https://x.test/a"] == ("$19.99", "G-7F3K9Q2M1X", True)
    assert by_url["https://x.test/b"] == ("$5.50", "", False)
    assert by_url["https://x.test/c.pdf"] == (None, None, None)
    assert "extractions" in EXPORT_TABLES
    assert extractions.columns == ("url", "name", "kind", "count", "value")
    assert extractions.rows[:3] == [
        ("https://x.test/a", "price", "css", 2, "$19.99"),
        ("https://x.test/a", "ga", "regex", 1, "G-7F3K9Q2M1X"),
        ("https://x.test/a", "gtag", "search", 3, "gtag"),
    ]
    assert len(extractions.rows) == 6


def test_without_extractors_the_dump_is_unchanged(store: Store) -> None:
    store.page_done(_page("/a"), [])
    (pages,) = dump_tables(store, ("pages",))
    assert pages.columns == PAGE_COLUMNS
    assert store.extraction_columns() == []


def test_stored_config_rebuilds_the_specs(store: Store, tmp_path: Path) -> None:
    store.page_done(_page("/a", extractions=FOUND), [])
    store.finish(pages_done=1, complete=True)
    store.close()
    session = CrawlSession.open(store.path, tmp_path / "crawls")
    try:
        assert session.config.extract == CONFIG.extract
        assert session.config.search == CONFIG.search
        assert session.records_since(0)[0].extractions == FOUND
    finally:
        session.close()
