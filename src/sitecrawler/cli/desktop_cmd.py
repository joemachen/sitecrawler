"""The ``sitecrawler desktop`` command: the web UI in a native window."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from sitecrawler.cli._run import err, fail, require_crawl_db
from sitecrawler.web.desktop import run_desktop
from sitecrawler.web.prefs import default_prefs_file, load_prefs


def desktop(
    db: Annotated[
        Path | None,
        typer.Argument(help="Crawl database to browse read-only. Omit to start from an empty UI."),
    ] = None,
    crawls_dir: Annotated[
        Path | None,
        typer.Option(
            "--crawls-dir",
            help="Where crawls started from the window are written. "
            "Default: the folder last chosen in Settings, else ./crawls.",
        ),
    ] = None,
) -> None:
    """Open the UI in its own window instead of a browser tab."""
    if db is not None:
        require_crawl_db(db)
    prefs_file = default_prefs_file()
    folder = crawls_dir or load_prefs(prefs_file).crawls_dir or Path("crawls")
    err.print(f"Opening the sitecrawler window; new crawls go to {folder} (close it to quit)")
    try:
        run_desktop(db, crawls_dir=folder, prefs_file=prefs_file)
    except (ValueError, RuntimeError) as exc:
        fail(str(exc))
