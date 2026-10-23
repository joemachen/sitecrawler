"""The ``sitecrawler desktop`` command: the web UI in a native window."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from sitecrawler.cli._run import err, fail, require_crawl_db
from sitecrawler.web.desktop import run_desktop


def desktop(
    db: Annotated[
        Path | None,
        typer.Argument(help="Crawl database to browse read-only. Omit to start from an empty UI."),
    ] = None,
    crawls_dir: Annotated[
        Path,
        typer.Option("--crawls-dir", help="Where crawls started from the window are written."),
    ] = Path("crawls"),
) -> None:
    """Open the UI in its own window instead of a browser tab."""
    if db is not None:
        require_crawl_db(db)
    err.print("Opening the sitecrawler window (close it to quit)")
    try:
        run_desktop(db, crawls_dir=crawls_dir)
    except (ValueError, RuntimeError) as exc:
        fail(str(exc))
