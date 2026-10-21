"""dump_tables reads only the tables asked for, in export order."""

from __future__ import annotations

from pathlib import Path

import pytest

from sitecrawler.models import CrawlConfig
from sitecrawler.store import open_store
from sitecrawler.store.dump import EXPORT_TABLES, dump_tables


def test_dump_tables_subset_keeps_export_order(tmp_path: Path) -> None:
    with open_store(tmp_path / "c.db") as store:
        store.begin(CrawlConfig(start_url="https://x.test/"), resume=False)
        assert [t.name for t in dump_tables(store)] == list(EXPORT_TABLES)
        assert [t.name for t in dump_tables(store, ("redirects", "pages"))] == [
            "pages",
            "redirects",
        ]
        with pytest.raises(ValueError, match="unknown export tables"):
            dump_tables(store, ("pages", "nope"))
