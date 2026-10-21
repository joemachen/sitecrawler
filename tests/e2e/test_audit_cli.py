"""The audit and issues commands against a stored fixture crawl."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from sitecrawler.cli.main import app

runner = CliRunner()


def test_audit_then_issues(crawled_db: Path, site: str) -> None:
    audit = runner.invoke(app, ["audit", str(crawled_db)])
    assert audit.exit_code == 0, audit.output
    flat = " ".join(audit.output.split())
    assert "response.4xx" in flat
    assert "response.5xx" in flat
    assert "non-indexable" in flat

    listing = runner.invoke(app, ["issues", str(crawled_db), "--rule", "response.4xx"])
    assert listing.exit_code == 0, listing.output
    lines = [line for line in listing.output.splitlines() if line.startswith("high\t")]
    assert len(lines) == 1
    severity, rule_id, url, detail = lines[0].split("\t")
    assert (severity, rule_id, url) == ("high", "response.4xx", f"{site}/missing")
    assert detail.startswith("404, linked from")

    everything = runner.invoke(app, ["issues", str(crawled_db)])
    assert everything.exit_code == 0
    assert len(everything.output.splitlines()) >= 4


def test_issues_before_audit_and_unknown_rule(crawled_db: Path, tmp_path: Path) -> None:
    empty = runner.invoke(app, ["issues", str(crawled_db)])
    assert empty.exit_code == 0
    assert "no issues stored" in " ".join(empty.output.split())

    unknown = runner.invoke(app, ["issues", str(crawled_db), "--rule", "nope.nope"])
    assert unknown.exit_code == 2
    assert "unknown rule" in " ".join(unknown.output.split())

    assert runner.invoke(app, ["audit", str(tmp_path / "none.db")]).exit_code == 2
    not_db = tmp_path / "notes.txt"
    not_db.write_text("hello", encoding="utf-8")
    assert runner.invoke(app, ["audit", str(not_db)]).exit_code == 2
    assert not_db.read_text(encoding="utf-8") == "hello"  # left untouched
    missing_crawl = tmp_path / "empty.db"
    from sitecrawler.store import open_store

    with open_store(missing_crawl):
        pass
    assert runner.invoke(app, ["audit", str(missing_crawl)]).exit_code == 2
