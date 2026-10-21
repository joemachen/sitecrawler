"""The serve command's wiring; the server itself is exercised by the web tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import uvicorn
from typer.testing import CliRunner

from sitecrawler.cli.main import app
from sitecrawler.cli.serve_cmd import open_when_started
from sitecrawler.store import open_store

runner = CliRunner()


def test_serve_rejects_a_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["serve", str(tmp_path / "nope.db")])
    assert result.exit_code == 2
    assert "not a file" in " ".join(result.output.split())


def test_serve_rejects_an_empty_store(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    open_store(path).close()
    result = runner.invoke(app, ["serve", str(path), "--no-open"])
    assert result.exit_code == 2
    assert "holds no crawl" in " ".join(result.output.split())


def test_serve_binds_loopback_on_the_given_port(
    crawled_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configs: list[uvicorn.Config] = []
    opened: list[str] = []

    def fake_run(self: uvicorn.Server) -> None:
        configs.append(self.config)

    monkeypatch.setattr(uvicorn.Server, "run", fake_run)
    monkeypatch.setattr("webbrowser.open", lambda url, *_a, **_k: opened.append(url))
    result = runner.invoke(app, ["serve", str(crawled_db), "--port", "8999", "--no-open"])
    assert result.exit_code == 0, result.output
    assert len(configs) == 1
    assert (configs[0].host, configs[0].port, configs[0].log_level) == (
        "127.0.0.1",
        8999,
        "warning",
    )
    assert "http://127.0.0.1:8999" in " ".join(result.output.split())
    assert opened == []


class _Server:
    def __init__(self, started: bool) -> None:
        self.started = started


def test_browser_opens_only_once_the_server_is_up(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url, *_a, **_k: opened.append(url))
    assert open_when_started(_Server(started=True), "http://127.0.0.1:1")
    assert opened == ["http://127.0.0.1:1"]
    assert not open_when_started(_Server(started=False), "http://127.0.0.1:2", timeout=0.1)
    assert opened == ["http://127.0.0.1:1"]
