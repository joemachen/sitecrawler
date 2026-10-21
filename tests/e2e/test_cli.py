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
    assert rows["/loop-a"]["status"] == "redirect_loop"
    assert rows["/orphan"]["found_on"].startswith("sitemap:")
    assert len(rows) == 13


def test_invalid_url_exits_2() -> None:
    result = runner.invoke(app, ["crawl", "nope"])
    assert result.exit_code == 2


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_crawl_with_db_then_resume(site: str, tmp_path: Path) -> None:
    db = tmp_path / "crawl.db"
    first = runner.invoke(app, ["crawl", site, "--db", str(db), "--delay", "0", "--max-pages", "3"])
    assert first.exit_code == 0, first.output
    assert db.exists()

    again = runner.invoke(app, ["crawl", site, "--db", str(db), "--delay", "0"])
    assert again.exit_code == 2
    assert "already exists" in again.output

    out = tmp_path / "pages.csv"
    resumed = runner.invoke(
        app, ["crawl", site, "--db", str(db), "--resume", "--delay", "0", "-o", str(out)]
    )
    assert resumed.exit_code == 0, resumed.output
    with out.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 13  # the CSV comes from the store, so it has both runs
    assert list(rows[0].keys())[:2] == ["url", "status"]


def test_resume_needs_db(site: str, tmp_path: Path) -> None:
    result = runner.invoke(app, ["crawl", site, "--resume"])
    assert result.exit_code == 2
    missing = runner.invoke(app, ["crawl", site, "--db", str(tmp_path / "none.db"), "--resume"])
    assert missing.exit_code == 2
