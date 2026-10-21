"""The ``sitecrawler export`` command."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from sitecrawler.cli._run import err, fail
from sitecrawler.export import write_csv, write_json, write_xlsx
from sitecrawler.store import open_store
from sitecrawler.store.dump import dump_tables


class ExportFormat(StrEnum):
    """Output formats ``export`` can write."""

    CSV = "csv"
    XLSX = "xlsx"
    JSON = "json"


def export(
    db: Annotated[Path, typer.Argument(help="Crawl database written by crawl --db or list --db.")],
    fmt: Annotated[
        ExportFormat, typer.Option("--format", "-f", help="csv (pages only), xlsx or json.")
    ] = ExportFormat.CSV,
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="File to write. Default: the DB name with the format's extension.",
        ),
    ] = None,
) -> None:
    """Export a stored crawl: csv (the pages table), xlsx (one sheet per table) or json."""
    if not db.is_file():
        fail(f"{db} is not a file")
    output = output or db.with_suffix(f".{fmt.value}")
    with open_store(db) as store:
        try:
            crawl = store.crawl()
        except ValueError as exc:
            fail(str(exc))
            return
        if fmt is ExportFormat.CSV:
            rows = write_csv(store.iter_pages(), output)
        elif fmt is ExportFormat.XLSX:
            rows = write_xlsx(dump_tables(store), output)
        else:
            rows = write_json(crawl, dump_tables(store), output)
    source = crawl.start_url or "a URL list"
    err.print(f"[green]{rows} rows written to {output}[/green] ({fmt.value}, crawl of {source})")
