"""The desktop command's wiring; the window itself is tested in tests/unit/web."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from sitecrawler.cli import desktop_cmd
from sitecrawler.cli.main import app

runner = CliRunner()


def test_desktop_rejects_a_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["desktop", str(tmp_path / "nope.db")])
    assert result.exit_code == 2
    assert "not a file" in " ".join(result.output.split())


def test_desktop_opens_the_window_over_the_file(
    crawled_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path | None, Path]] = []
    monkeypatch.setattr(
        desktop_cmd, "run_desktop", lambda db, *, crawls_dir: calls.append((db, crawls_dir))
    )
    result = runner.invoke(app, ["desktop", str(crawled_db), "--crawls-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == [(crawled_db, tmp_path)]


def test_desktop_reports_a_window_that_cannot_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(db: Path | None, *, crawls_dir: Path) -> None:
        raise RuntimeError("The desktop window needs pywebview")

    monkeypatch.setattr(desktop_cmd, "run_desktop", fail)
    result = runner.invoke(app, ["desktop"])
    assert result.exit_code == 2
    assert "needs pywebview" in result.output
