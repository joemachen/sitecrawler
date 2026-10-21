"""Run the real CLI against the fixture site and check the CSV it writes."""

from __future__ import annotations

import csv
from pathlib import Path

from typer.testing import CliRunner

from sitecrawler.cli.main import app

runner = CliRunner()


def test_crawl_command_writes_csv(site: str, tmp_path: Path) -> None:
    out = tmp_path / "pages.csv"
    result = runner.invoke(app, ["crawl", site, "-o", str(out), "--delay", "0"])
    assert result.exit_code == 0, result.output

    with out.open(newline="", encoding="utf-8") as fh:
        rows = {row["url"].removeprefix(site): row for row in csv.DictReader(fh)}

    assert rows["/"]["status"] == "200"
    assert rows["/"]["title"] == "Fixture Site Home"
    assert rows["/missing"]["status"] == "404"
    assert rows["/blocked/secret"]["status"] == "blocked"
    assert rows["/orphan"]["found_on"].startswith("sitemap:")
    assert len(rows) == 13


def test_invalid_url_exits_2() -> None:
    result = runner.invoke(app, ["crawl", "nope"])
    assert result.exit_code == 2


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
