import csv
from pathlib import Path

from sitecrawler.export import CSV_FIELDS, write_csv
from sitecrawler.models import Outcome, PageRecord


def test_write_csv_round_trip(tmp_path: Path) -> None:
    records = [
        PageRecord(url="https://x/a", outcome=Outcome.FETCHED, depth=0, found_on="start",
                   status_code=200, title="A, with comma", word_count=3),
        PageRecord(url="https://x/b", outcome=Outcome.BLOCKED, depth=1, found_on="https://x/a",
                   error="disallowed by robots.txt"),
        PageRecord(url="https://x/c", outcome=Outcome.ERROR, depth=1, found_on="https://x/a",
                   error="boom"),
    ]  # fmt: skip
    out = tmp_path / "pages.csv"
    assert write_csv(records, out) == 3

    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0].keys()) == list(CSV_FIELDS)
    assert rows[0]["status"] == "200"
    assert rows[0]["title"] == "A, with comma"
    assert rows[1]["status"] == "blocked"
    assert rows[2]["status"] == "error"
    assert rows[2]["error"] == "boom"
