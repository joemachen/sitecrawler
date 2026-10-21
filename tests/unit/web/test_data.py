"""The snapshot's derived numbers, computed from hand-built dump tables."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from sitecrawler.audit import CrawlView
from sitecrawler.models import CrawlInfo
from sitecrawler.store import open_store
from sitecrawler.store.dump import PAGE_COLUMNS, Cell, TableDump
from sitecrawler.web import CrawlSnapshot, load_snapshot, to_rows

ISSUE_COLUMNS = ("url", "rule_id", "severity", "message")
REDIRECT_COLUMNS = ("url", "hop_no", "from_url", "to_url", "status_code")


def page_row(url: str, **cells: Cell) -> tuple[Cell, ...]:
    values: dict[str, Cell] = dict.fromkeys(PAGE_COLUMNS, None)
    values.update(url=url, status_code=200, outcome="fetched", depth=0)
    values.update(cells)
    return tuple(values[c] for c in PAGE_COLUMNS)


def snapshot(
    pages: list[tuple[Cell, ...]], issues: list[tuple[Cell, ...]] | None = None
) -> CrawlSnapshot:
    return CrawlSnapshot(
        path=Path("crawl.db"),
        info=CrawlInfo(
            start_url="https://site.test/",
            mode="crawl",
            version="0",
            status="done",
            pages_done=len(pages),
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        view=CrawlView.from_records([]),
        pages=TableDump("pages", PAGE_COLUMNS, pages),
        issues=TableDump("issues", ISSUE_COLUMNS, issues or []),
        redirects=TableDump("redirects", REDIRECT_COLUMNS, []),
        rules={},
        issue_counts={},
    )


def test_overview_buckets_status_depth_and_verdicts() -> None:
    snap = snapshot(
        [
            page_row("https://site.test/", depth=0, indexable=True),
            page_row("https://site.test/a", depth=1, indexable=True),
            page_row("https://site.test/b", status_code=301, depth=1, indexable=False),
            page_row("https://site.test/c", status_code=404, depth=2, indexable=False),
            page_row("https://site.test/d", status_code=None, outcome="blocked", depth=2),
        ],
        [
            ("https://site.test/c", "response.4xx", "high", ""),
            ("https://site.test/b", "page.non_indexable", "info", "redirect"),
            ("https://site.test/c", "page.non_indexable", "info", "status 404"),
        ],
    )
    overview = snap.overview()
    assert overview.pages == 5
    assert overview.status_buckets == {"2xx": 2, "3xx": 1, "4xx": 1, "blocked": 1}
    assert overview.depth_histogram == {0: 1, 1: 2, 2: 2}
    assert overview.issues_by_severity == {
        "critical": 0,
        "high": 1,
        "medium": 0,
        "low": 0,
        "info": 2,
    }
    assert overview.issues == 3
    assert (overview.indexable, overview.non_indexable) == (2, 2)
    assert snap.audited


def test_unaudited_snapshot_has_no_verdicts() -> None:
    snap = snapshot([page_row("https://site.test/")])
    assert not snap.audited
    assert snap.overview().issues == 0


def test_to_rows_zips_columns() -> None:
    table = TableDump("t", ("a", "b"), [(1, "x"), (2, None)])
    assert to_rows(table) == [{"a": 1, "b": "x"}, {"a": 2, "b": None}]


def test_load_snapshot_rejects_an_empty_store(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    open_store(path).close()
    with pytest.raises(ValueError, match="holds no crawl"):
        load_snapshot(path)
