"""The desktop window: its server, its window and the exe's entry point, with pywebview faked."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import cast

import httpx
import pytest

from sitecrawler.store import open_store
from sitecrawler.web import desktop
from sitecrawler.web.desktop import (
    DesktopApi,
    DesktopServer,
    default_crawls_dir,
    main,
    run_desktop,
)
from sitecrawler.web.prefs import Prefs, load_prefs, save_prefs


class FakeWindow:
    """Answers the folder picker with ``chosen``."""

    def __init__(self, chosen: tuple[str, ...] | None = None) -> None:
        self.chosen = chosen
        self.dialogs: list[tuple[int, str]] = []

    def create_file_dialog(self, dialog_type: int, directory: str = "") -> tuple[str, ...] | None:
        self.dialogs.append((dialog_type, directory))
        return self.chosen


class FakeWebview(types.ModuleType):
    """Stands in for ``webview``: records the window and fetches its page on ``start``."""

    class FileDialog:
        FOLDER = 20

    def __init__(self) -> None:
        super().__init__("webview")
        self.settings: dict[str, object] = {}
        self.windows: list[tuple[str, str, dict[str, object]]] = []
        self.pages: list[httpx.Response] = []
        self.window = FakeWindow()

    def create_window(self, title: str, url: str, **options: object) -> FakeWindow:
        self.windows.append((title, url, options))
        return self.window

    def start(self) -> None:
        # The window is open: the server must already answer.
        self.pages.append(httpx.get(self.windows[-1][1]))


@pytest.fixture
def webview(monkeypatch: pytest.MonkeyPatch) -> FakeWebview:
    fake = FakeWebview()
    monkeypatch.setitem(sys.modules, "webview", fake)
    return fake


@pytest.fixture(autouse=True)
def prefs_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep every test away from the real %APPDATA% settings file."""
    path = tmp_path / "appdata" / "settings.json"
    monkeypatch.setattr(desktop, "default_prefs_file", lambda: path)
    return path


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
    assert isinstance(options["js_api"], DesktopApi)
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


def test_browse_opens_the_folder_picker_at_the_current_folder(webview: FakeWebview) -> None:
    api = DesktopApi()
    assert api.choose_folder("C:/start") is None  # no window yet
    api._window = webview.window  # type: ignore[assignment]  # stands in for webview.Window
    webview.window.chosen = ("D:/SEO/crawls",)
    assert api.choose_folder("C:/start") == "D:/SEO/crawls"
    assert webview.window.dialogs == [(20, "C:/start")]
    webview.window.chosen = None  # cancelled
    assert api.choose_folder("C:/start") is None


def test_window_api_hides_the_window_handle(webview: FakeWebview, tmp_path: Path) -> None:
    run_desktop(crawls_dir=tmp_path)
    api = webview.windows[0][2]["js_api"]
    assert isinstance(api, DesktopApi)
    assert cast(object, api._window) is webview.window
    public = [name for name in dir(api) if not name.startswith("_")]
    assert public == ["choose_folder"]  # all that pywebview hands the page


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


def test_main_uses_the_folder_chosen_last_time(
    webview: FakeWebview, errors: list[str], prefs_file: Path, tmp_path: Path
) -> None:
    save_prefs(prefs_file, Prefs(crawls_dir=tmp_path / "chosen"))
    assert main([]) == 0
    assert webview.pages[0].status_code == 200
    assert str(tmp_path / "chosen") in webview.pages[0].text


def test_main_remembers_a_folder_chosen_in_the_window(
    monkeypatch: pytest.MonkeyPatch, errors: list[str], prefs_file: Path, tmp_path: Path
) -> None:
    class ChoosingWebview(FakeWebview):
        def start(self) -> None:
            url = self.windows[-1][1]
            httpx.post(f"{url}/api/crawls-dir", json={"path": str(tmp_path / "picked")})

    monkeypatch.setitem(sys.modules, "webview", ChoosingWebview())
    assert main([]) == 0
    assert load_prefs(prefs_file) == Prefs(crawls_dir=(tmp_path / "picked").resolve())


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
