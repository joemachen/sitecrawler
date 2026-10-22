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
        PageRecord(url="https://x/d", outcome=Outcome.REDIRECT_LOOP, depth=1,
                   found_on="https://x/a", error="redirect loop: https://x/d -> https://x/d"),
    ]  # fmt: skip
    out = tmp_path / "pages.csv"
    assert write_csv(records, out) == 4

    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0].keys()) == list(CSV_FIELDS)
    assert rows[0]["status"] == "200"
    assert rows[0]["title"] == "A, with comma"
    assert rows[1]["status"] == "blocked"
    assert rows[2]["status"] == "error"
    assert rows[2]["error"] == "boom"
    assert rows[3]["status"] == "redirect_loop"


def test_extraction_columns_follow_the_fixed_ones(tmp_path: Path) -> None:
    from sitecrawler.models import Extraction

    records = [
        PageRecord(
            url="https://x/a",
            outcome=Outcome.FETCHED,
            depth=0,
            found_on="start",
            status_code=200,
            extractions=(
                Extraction("price", "css", ("$1", "$2"), 2),
                Extraction("ga", "search", ("G-1",), 1),
                Extraction("stray", "css", ("x",), 1),
            ),
        ),
        PageRecord(url="https://x/b", outcome=Outcome.ERROR, depth=1, found_on="https://x/a"),
    ]
    out = tmp_path / "pages.csv"
    assert write_csv(records, out, extra_columns=["extract_price", "search_ga", "url"]) == 2
    with out.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        assert reader.fieldnames == [*CSV_FIELDS, "extract_price", "search_ga"]
    assert (rows[0]["extract_price"], rows[0]["search_ga"]) == ("$1 | $2", "True")
    assert (rows[1]["extract_price"], rows[1]["search_ga"]) == ("", "")
