"""The web UI in a native window: the same app as ``serve``, without a browser.

The FastAPI app runs on a private loopback port in a background thread and a
pywebview window (Edge WebView2 on Windows) shows it. Closing the window stops
the server, which stops any crawl still running. This is what the standalone
``sitecrawler.exe`` runs; ``sitecrawler desktop`` runs it from a checkout.
"""

from __future__ import annotations

import ctypes
import socket
import sys
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

from sitecrawler.store import crawl_file_problem
from sitecrawler.web.app import create_app
from sitecrawler.web.prefs import default_prefs_file, load_prefs

if TYPE_CHECKING:
    from webview import Window

HOST = "127.0.0.1"
"""The UI has no login, so it only ever listens on loopback."""

TITLE = "sitecrawler"

DESKTOP_HINT = "The desktop window needs pywebview: run `uv sync --extra desktop`"


class DesktopServer:
    """The UI's HTTP server on a free loopback port, running in a background thread."""

    def __init__(self, db: Path | None, crawls_dir: Path, prefs_file: Path | None = None) -> None:
        """Build the app; nothing listens until :meth:`start`.

        Raises:
            ValueError: when ``db`` holds no crawl.
        """
        app = create_app(db, crawls_dir=crawls_dir, prefs_file=prefs_file)
        # log_config=None: uvicorn's default config writes to sys.stderr,
        # which a windowed exe does not have.
        self._server = uvicorn.Server(uvicorn.Config(app, log_config=None, log_level="warning"))
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Binding here, before the thread starts, picks the port without a race.
        self._socket.bind((HOST, 0))
        port = self._socket.getsockname()[1]
        self.url = f"http://{HOST}:{port}"
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [self._socket]}, daemon=True
        )

    def start(self, timeout: float = 10.0) -> None:
        """Start serving and wait until the port answers.

        Raises:
            RuntimeError: the server did not start within ``timeout`` seconds.
        """
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if time.monotonic() >= deadline or not self._thread.is_alive():
                raise RuntimeError("the sitecrawler server did not start")
            time.sleep(0.05)

    def stop(self, timeout: float = 15.0) -> None:
        """Ask the server to shut down (stopping any crawl) and wait for it."""
        self._server.should_exit = True
        if self._thread.is_alive():
            self._thread.join(timeout)
        self._socket.close()


class DesktopApi:
    """What the page may call in the desktop window, as ``window.pywebview.api``.

    pywebview exposes every public method; attributes starting with ``_``
    stay on the Python side.
    """

    def __init__(self) -> None:
        """Create the API; :func:`run_desktop` attaches the window once it exists."""
        self._window: Window | None = None

    def choose_folder(self, start: str = "") -> str | None:
        """Ask for a folder with the system's folder picker, opened at ``start``.

        Returns:
            The chosen folder, or None when the picker was cancelled.
        """
        import webview  # only ever called from inside the window, so it imports

        if self._window is None:
            return None
        chosen = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start)
        return str(chosen[0]) if chosen else None


def run_desktop(
    db: Path | None = None, *, crawls_dir: Path, prefs_file: Path | None = None
) -> None:
    """Open the UI in a native window and block until the window is closed.

    Args:
        db: A stored crawl to open read-only, or None to start ready to crawl.
        crawls_dir: Where crawls started from the window are written.
        prefs_file: Where a folder chosen in Settings is remembered, or None
            to forget it when the window closes.

    Raises:
        ValueError: when ``db`` holds no crawl.
        RuntimeError: pywebview is not installed, or the server did not start.
    """
    try:
        import webview  # optional dependency: the `desktop` extra
    except ImportError as exc:
        raise RuntimeError(DESKTOP_HINT) from exc

    server = DesktopServer(db, crawls_dir, prefs_file)
    server.start()
    api = DesktopApi()
    try:
        webview.settings["ALLOW_DOWNLOADS"] = True  # the grid's Export CSV button
        api._window = webview.create_window(
            f"{TITLE} - {db.name}" if db else TITLE,
            server.url,
            width=1400,
            height=900,
            min_size=(900, 600),
            maximized=True,  # the grid and sidebar clip below about 1600px wide
            text_select=True,
            js_api=api,
        )
        webview.start()
    finally:
        server.stop()


def default_crawls_dir() -> Path:
    """``crawls`` beside the exe when frozen, else ``crawls`` in the working directory.

    A double-clicked exe can start in any working directory (System32, say),
    so its crawls go next to the exe, where they are easy to find.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "crawls"
    return Path("crawls")


def show_error(message: str) -> None:
    """Tell the user ``message``: a message box on Windows, stderr elsewhere."""
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)  # MB_ICONERROR
    elif sys.stderr is not None:
        sys.stderr.write(f"{message}\n")


def _log_to_file(path: Path) -> None:
    """Send stdout and stderr to ``path``: a windowed exe has neither."""
    stream = path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the standalone exe.

    The only argument is an optional crawl file, which is what Windows passes
    when a ``.db`` is dropped on the exe or opened with it. Crawls go to the
    folder last chosen in Settings, else to :func:`default_crawls_dir`.

    Returns:
        The process exit code: 0, or 2 when the window could not open.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if sys.stderr is None:
        _log_to_file(default_crawls_dir().parent / "sitecrawler.log")
    prefs_file = default_prefs_file()
    crawls_dir = load_prefs(prefs_file).crawls_dir or default_crawls_dir()
    if len(args) > 1:
        show_error("Usage: sitecrawler [CRAWL.db]")
        return 2
    db = Path(args[0]) if args else None
    if db is not None and (problem := crawl_file_problem(db)):
        show_error(problem)
        return 2
    try:
        run_desktop(db, crawls_dir=crawls_dir, prefs_file=prefs_file)
    except (ValueError, RuntimeError, OSError) as exc:
        show_error(str(exc))
        return 2
    return 0
