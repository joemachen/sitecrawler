"""Crawl into a store, then export it in every format."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from openpyxl import load_workbook
from typer.testing import CliRunner

from sitecrawler.cli.main import app
from sitecrawler.export import CSV_FIELDS
from tests.conftest import site_pages

runner = CliRunner()


def test_export_xlsx_has_a_sheet_per_table(crawled_db: Path) -> None:
    result = runner.invoke(app, ["export", str(crawled_db), "--format", "xlsx"])
    assert result.exit_code == 0, result.output
    out = crawled_db.with_suffix(".xlsx")
    workbook = load_workbook(out, read_only=True)
    try:
        assert workbook.sheetnames == [
            "pages",
            "issues",
            "links",
            "redirects",
            "hreflang",
            "sitemaps",
            "sitemap_urls",
            "extractions",
            "structured_data",
        ]
        pages = list(workbook["pages"].iter_rows(values_only=True))
        assert pages[0][0] == "url"
        assert len(pages) == 1 + len(site_pages())
        redirects = list(workbook["redirects"].iter_rows(values_only=True))
        # chain 2, loop 2, /blog and /audit trailing-slash 301s, redirect-to-missing, off-site
        assert len(redirects) == 1 + 9
        assert redirects[0] == ("url", "hop_no", "from_url", "to_url", "status_code")
        # 7 in sitemap.xml, 2 in the gzipped extra sitemap (one page twice, one other host)
        assert len(list(workbook["sitemap_urls"].iter_rows(values_only=True))) == 1 + 9
        sitemaps = list(workbook["sitemaps"].iter_rows(values_only=True))
        assert sitemaps[0] == ("url", "found_in", "kind", "status_code", "url_count", "error")
        assert len(sitemaps) == 1 + 4
    finally:
        workbook.close()


def test_export_csv_matches_crawl_output(crawled_db: Path, site: str, tmp_path: Path) -> None:
    out = tmp_path / "pages.csv"
    result = runner.invoke(app, ["export", str(crawled_db), "-f", "csv", "-o", str(out)])
    assert result.exit_code == 0, result.output
    with out.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = {row["url"].removeprefix(site): row for row in reader}
        assert reader.fieldnames == list(CSV_FIELDS)
    assert len(rows) == len(site_pages())
    assert rows["/about"]["title"] == "About the Fixture Site"
    assert rows["/loop-a"]["status"] == "redirect_loop"


def test_export_json(crawled_db: Path, site: str) -> None:
    result = runner.invoke(app, ["export", str(crawled_db), "-f", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(crawled_db.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["crawl"]["status"] == "done"
    assert data["crawl"]["start_url"] == site + "/"
    assert len(data["pages"]) == len(site_pages())
    assert {row["url"].removeprefix(site) for row in data["redirects"]} == {
        "/redirect-start",
        "/loop-a",
        "/blog",
        "/products",
        "/audit",
        "/audit/redirect-to-missing",
        "/audit/redirect-off-site",
    }
    assert all(row["src_url"] for row in data["links"])


def test_export_rejects_missing_or_empty_db(tmp_path: Path) -> None:
    assert runner.invoke(app, ["export", str(tmp_path / "none.db")]).exit_code == 2
    empty = tmp_path / "empty.db"
    empty.write_bytes(b"")
    assert runner.invoke(app, ["export", str(empty)]).exit_code == 2
