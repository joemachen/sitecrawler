"""The ``sitecrawler serve`` command: the local web UI over a stored crawl."""

from __future__ import annotations

import threading
import time
import webbrowser
from pathlib import Path
from typing import Annotated, Protocol

import typer
import uvicorn

from sitecrawler.cli._run import err, fail, require_crawl_db
from sitecrawler.web import create_app

HOST = "127.0.0.1"
"""The UI has no login, so it only ever listens on loopback."""


class _Startable(Protocol):
    started: bool


def open_when_started(server: _Startable, url: str, *, timeout: float = 10.0) -> bool:
    """Open ``url`` in the browser once ``server`` reports it is listening.

    Returns False without opening anything when the server did not start
    within ``timeout`` seconds (the port was busy, say), so the user sees the
    error instead of a browser tab on a dead address.
    """
    deadline = time.monotonic() + timeout
    while not server.started:
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    webbrowser.open(url)
    return True


def serve(
    db: Annotated[Path, typer.Argument(help="Crawl database to browse; run audit on it first.")],
    port: Annotated[int, typer.Option("--port", help="Port on 127.0.0.1 to listen on.")] = 8765,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the UI in your browser.")
    ] = True,
) -> None:
    """Open the local web UI on a stored crawl."""
    require_crawl_db(db)
    try:
        app = create_app(db)
    except ValueError as exc:
        fail(str(exc))
        return
    url = f"http://{HOST}:{port}"
    err.print(f"Serving {db} at [bold]{url}[/bold]  (Ctrl+C to stop)")
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning"))
    if open_browser:
        threading.Thread(target=open_when_started, args=(server, url), daemon=True).start()
    server.run()
