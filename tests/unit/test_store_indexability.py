"""Reading indexability verdicts back from a store."""

from __future__ import annotations

from pathlib import Path

from sitecrawler.models import CrawlConfig, Indexability, Outcome, PageRecord
from sitecrawler.store import open_store


def _page(url: str) -> PageRecord:
    return PageRecord(url=url, outcome=Outcome.FETCHED, depth=0, found_on="start", status_code=200)


def test_indexability_round_trip(tmp_path: Path) -> None:
    with open_store(tmp_path / "c.db") as store:
        store.begin(CrawlConfig(start_url="https://x.test/"), resume=False)
        store.page_done(_page("https://x.test/a"), [])
        store.page_done(_page("https://x.test/b"), [])
        assert store.indexability() == {}

        store.set_indexability({"https://x.test/a": Indexability(False, "noindex")})

        assert store.indexability() == {"https://x.test/a": Indexability(False, "noindex")}
