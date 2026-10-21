import json
from datetime import datetime
from pathlib import Path

from sitecrawler.export import write_json
from sitecrawler.models import CrawlInfo
from sitecrawler.store.dump import TableDump


def test_json_document_shape(tmp_path: Path) -> None:
    crawl = CrawlInfo(
        start_url="https://x/",
        mode="crawl",
        version="0.1.0",
        status="done",
        pages_done=1,
        started_at=datetime(2026, 10, 21, 10, 0, 0),
        finished_at=None,
    )
    tables = [TableDump("pages", ("url", "title"), [("https://x/", "Hé")])]
    out = tmp_path / "crawl.json"
    assert write_json(crawl, tables, out) == 1

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["crawl"]["start_url"] == "https://x/"
    assert data["crawl"]["started_at"] == "2026-10-21T10:00:00"
    assert data["crawl"]["finished_at"] is None
    assert data["pages"] == [{"url": "https://x/", "title": "Hé"}]
