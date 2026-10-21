"""The serve command's wiring; the server itself is exercised by the web tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from sitecrawler.cli.main import app
from sitecrawler.store import open_store

runner = CliRunner()


def test_serve_rejects_a_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", str(tmp_path / "nope.db")])
    assert result.exit_code == 2
    assert "not a file" in result.output


def test_serve_rejects_an_empty_store(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    open_store(path).close()
    result = runner.invoke(app, ["serve", str(path), "--no-open"])
    assert result.exit_code == 2
    assert "holds no crawl" in result.output


def test_serve_binds_loopback_on_the_given_port(
    crawled_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: dict[str, object] = {}

    def fake_run(_app: object, **kwargs: object) -> None:
        calls.update(kwargs)

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr("webbrowser.open", lambda *_a, **_k: calls.setdefault("opened", True))
    result = runner.invoke(app, ["serve", str(crawled_db), "--port", "8999", "--no-open"])
    assert result.exit_code == 0, result.output
    assert calls == {"host": "127.0.0.1", "port": 8999, "log_level": "warning"}
    assert "http://127.0.0.1:8999" in result.output
