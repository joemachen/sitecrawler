"""The desktop window: its server, its window and the exe's entry point, with pywebview faked."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from sitecrawler.store import open_store
from sitecrawler.web import desktop
from sitecrawler.web.desktop import DesktopServer, default_crawls_dir, main, run_desktop


class FakeWebview(types.ModuleType):
    """Stands in for ``webview``: records the window and fetches its page on ``start``."""

    def __init__(self) -> None:
        super().__init__("webview")
        self.settings: dict[str, object] = {}
        self.windows: list[tuple[str, str, dict[str, object]]] = []
        self.pages: list[httpx.Response] = []

    def create_window(self, title: str, url: str, **options: object) -> None:
        self.windows.append((title, url, options))

    def start(self) -> None:
        # The window is open: the server must already answer.
        self.pages.append(httpx.get(self.windows[-1][1]))


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    return fake


def test_server_listens_on_a_free_loopback_port_until_stopped(tmp_path: Path) -> None:
    server = DesktopServer(None, tmp_path)
    assert server.url.startswith("http://127.0.0.1:")
    server.start()
    try:
        assert httpx.get(f"{server.url}/api/crawl").json()["status"] == "idle"
    finally:
        server.stop()
    with pytest.raises(httpx.TransportError):  # Windows times out on a closed port
        httpx.get(server.url, timeout=1)


def test_two_servers_get_different_ports(tmp_path: Path) -> None:
    first, second = DesktopServer(None, tmp_path), DesktopServer(None, tmp_path)
    try:
        assert first.url != second.url
    finally:
        first.stop()
        second.stop()


def test_window_shows_the_ui_and_closing_it_stops_the_server(
    webview: FakeWebview, tmp_path: Path
) -> None:
    run_desktop(crawls_dir=tmp_path)
    title, url, options = webview.windows[0]
    assert title == "sitecrawler"
    assert options["text_select"] is True
    assert webview.settings["ALLOW_DOWNLOADS"] is True
    assert webview.pages[0].status_code == 200
    assert "<title>sitecrawler</title>" in webview.pages[0].text
    with pytest.raises(httpx.TransportError):  # Windows times out on a closed port
        httpx.get(url, timeout=1)


def test_window_over_a_stored_crawl_is_titled_after_the_file(
    webview: FakeWebview, crawled_db: Path, tmp_path: Path
) -> None:
    run_desktop(crawled_db, crawls_dir=tmp_path)
    assert webview.windows[0][0] == f"sitecrawler - {crawled_db.name}"
    assert webview.pages[0].status_code == 200


def test_missing_pywebview_is_a_clear_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "webview", None)  # None makes the import fail
    with pytest.raises(RuntimeError, match="--extra desktop"):
        run_desktop(crawls_dir=tmp_path)


def test_crawls_go_beside_the_frozen_exe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert default_crawls_dir() == Path("crawls")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "sitecrawler.exe"))
    assert default_crawls_dir() == tmp_path.resolve() / "crawls"


@pytest.fixture
def errors(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    shown: list[str] = []
    monkeypatch.setattr(desktop, "show_error", shown.append)
    return shown


def test_main_opens_a_dropped_crawl_file(
    webview: FakeWebview, errors: list[str], crawled_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(crawled_db.parent)
    assert main([str(crawled_db)]) == 0
    assert errors == []
    assert webview.windows[0][0].endswith(crawled_db.name)


@pytest.mark.parametrize(
    ("make_args", "message"),
    [
        (lambda d: [str(d / "nope.db")], "is not a file"),
        (lambda d: ["a.db", "b.db"], "Usage"),
    ],
)
def test_main_reports_bad_arguments_without_a_window(
    webview: FakeWebview,
    errors: list[str],
    tmp_path: Path,
    make_args: Callable[[Path], list[str]],
    message: str,
) -> None:
    assert main(make_args(tmp_path)) == 2
    assert message in errors[0]
    assert webview.windows == []


def test_main_reports_a_file_with_no_crawl(
    webview: FakeWebview, errors: list[str], tmp_path: Path
) -> None:
    empty = tmp_path / "empty.db"
    open_store(empty).close()
    assert main([str(empty)]) == 2
    assert "holds no crawl" in errors[0]


def test_windowed_exe_logs_to_a_file(
    webview: FakeWebview, errors: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(desktop, "default_crawls_dir", lambda: tmp_path / "crawls")
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    assert main([]) == 0
    print("hello")
    assert sys.stdout is not None
    sys.stdout.close()
    assert "hello" in (tmp_path / "sitecrawler.log").read_text(encoding="utf-8")
