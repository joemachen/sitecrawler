"""The desktop command's wiring; the window itself is tested in tests/unit/web."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from sitecrawler.cli import desktop_cmd
from sitecrawler.cli.main import app
from sitecrawler.web.prefs import Prefs, save_prefs

runner = CliRunner()

Call = tuple[Path | None, Path, Path | None]


@pytest.fixture(autouse=True)
def prefs_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep every test away from the real %APPDATA% settings file."""
    path = tmp_path / "appdata" / "settings.json"
    monkeypatch.setattr(desktop_cmd, "default_prefs_file", lambda: path)
    return path


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[Call]:
    made: list[Call] = []

    def fake(db: Path | None, *, crawls_dir: Path, prefs_file: Path | None = None) -> None:
        made.append((db, crawls_dir, prefs_file))

    monkeypatch.setattr(desktop_cmd, "run_desktop", fake)
    return made


def test_desktop_rejects_a_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["desktop", str(tmp_path / "nope.db")])
    assert result.exit_code == 2
    assert "not a file" in " ".join(result.output.split())


def test_desktop_opens_the_window_over_the_file(
    crawled_db: Path, tmp_path: Path, calls: list[Call], prefs_file: Path
) -> None:
    result = runner.invoke(app, ["desktop", str(crawled_db), "--crawls-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == [(crawled_db, tmp_path, prefs_file)]


def test_desktop_defaults_to_the_folder_chosen_last_time(
    tmp_path: Path, calls: list[Call], prefs_file: Path
) -> None:
    assert runner.invoke(app, ["desktop"]).exit_code == 0
    save_prefs(prefs_file, Prefs(crawls_dir=tmp_path / "chosen"))
    assert runner.invoke(app, ["desktop"]).exit_code == 0
    assert [folder for _, folder, _ in calls] == [Path("crawls"), tmp_path / "chosen"]


def test_desktop_reports_a_window_that_cannot_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(db: Path | None, *, crawls_dir: Path, prefs_file: Path | None = None) -> None:
        raise RuntimeError("The desktop window needs pywebview")

    monkeypatch.setattr(desktop_cmd, "run_desktop", fail)
    result = runner.invoke(app, ["desktop"])
    assert result.exit_code == 2
    assert "needs pywebview" in result.output
