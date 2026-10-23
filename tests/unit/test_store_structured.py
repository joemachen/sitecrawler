"""The structured_data table round-trips items and parse errors and feeds the exports."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from typer.testing import CliRunner

from sitecrawler.cli.main import app
from sitecrawler.models import (
    CrawlConfig,
    Fingerprint,
    Outcome,
    PageRecord,
    StructuredData,
    StructuredError,
    StructuredItem,
)
from sitecrawler.store import missing_tables, open_store
from sitecrawler.store.dump import EXPORT_TABLES, PAGE_COLUMNS, dump_tables

PRODUCT = StructuredItem(
    "json-ld",
    {"@type": ["Product"], "name": ["W"], "offers": [{"@type": ["Offer"], "price": ["9"]}]},
    4,
)
CRUMBS = StructuredItem("microdata", {"@type": ["BreadcrumbList"]}, 9)
BROKEN = StructuredError("Expecting ',' delimiter (line 12, column 3)", 12)


def _page(path: str, **fields: object) -> PageRecord:
    return PageRecord(
        url=f"https://x.test{path}",
        outcome=Outcome.FETCHED,
        depth=0,
        found_on="start",
        status_code=200,
        final_url=f"https://x.test{path}",
        **({"content_type": "text/html"} | fields),  # type: ignore[arg-type]
    )


def test_structured_data_round_trips_and_is_exported(tmp_path: Path) -> None:
    rich = StructuredData((PRODUCT, CRUMBS), (BROKEN,))
    with open_store(tmp_path / "c.db") as store:
        store.begin(CrawlConfig(start_url="https://x.test/"), resume=False)
        store.page_done(_page("/rich", fingerprint=Fingerprint(), structured=rich), [])
        store.page_done(_page("/plain", fingerprint=Fingerprint(), structured=StructuredData()), [])
        store.page_done(_page("/pdf", content_type="application/pdf"), [])
        pages = {p.url.removeprefix("https://x.test"): p for p in store.iter_pages()}
        dumps = {d.name: d for d in dump_tables(store)}

    assert pages["/rich"].structured == rich
    assert pages["/plain"].structured == StructuredData()
    assert pages["/pdf"].structured is None

    assert EXPORT_TABLES[-1] == "structured_data"
    table = dumps["structured_data"]
    assert table.columns == ("url", "line", "format", "types", "error", "json")
    assert [row[:5] for row in table.rows] == [
        ("https://x.test/rich", 4, "json-ld", "Product", None),
        ("https://x.test/rich", 9, "microdata", "BreadcrumbList", None),
        ("https://x.test/rich", 12, "json-ld", "", BROKEN.message),
    ]
    assert table.rows[2][5] is None

    assert PAGE_COLUMNS[-1] == "structured_types"
    types = {row[0]: row[len(PAGE_COLUMNS) - 1] for row in dumps["pages"].rows}
    assert types == {
        "https://x.test/rich": "Product BreadcrumbList",
        "https://x.test/plain": "",
        "https://x.test/pdf": "",
    }


def test_a_crawl_file_from_before_the_table_is_refused(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    with open_store(db) as store:
        store.begin(CrawlConfig(start_url="https://x.test/"), resume=False)
        store.page_done(_page("/", fingerprint=Fingerprint()), [])
    assert missing_tables(db) == []
    with closing(sqlite3.connect(db)) as conn:
        conn.execute("DROP TABLE structured_data")
        conn.commit()
    assert missing_tables(db) == ["structured_data"]
    result = CliRunner().invoke(app, ["schema", "report", str(db)])
    assert result.exit_code == 2
    assert "older sitecrawler" in result.output
    assert "re-crawl" in result.output
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert missing_tables(empty) == []  # not a crawl yet
