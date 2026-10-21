"""The ``sitecrawler serve`` command: the local web UI over a stored crawl."""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from sitecrawler.cli._run import err, fail, require_crawl_db
from sitecrawler.web import create_app

HOST = "127.0.0.1"
"""The UI has no login, so it only ever listens on loopback."""


def serve(
    db: Annotated[Path, typer.Argument(help="Crawl database to browse; run audit on it first.")],
    port: Annotated[int, typer.Option("--port", help="Port on 127.0.0.1 to listen on.")] = 8765,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the UI in your browser.")
    ] = True,
) -> None:
    """Open the local web UI (Overview, Pages, Issues, ...) on a stored crawl."""
    require_crawl_db(db)
    try:
        app = create_app(db)
    except ValueError as exc:
        fail(str(exc))
        return
    url = f"http://{HOST}:{port}"
    err.print(f"Serving {db} at [bold]{url}[/bold]  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")
