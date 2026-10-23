"""The ``sitecrawler schema`` commands: ``report``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from sitecrawler.analysis import structured_report
from sitecrawler.audit.structured import KINDS
from sitecrawler.cli._run import err, fail, load_view

schema_app = typer.Typer(
    name="schema",
    help="Structured data: the types a crawl carries and every problem with them.",
    no_args_is_help=True,
)


@schema_app.command()
def report(
    db: Annotated[Path, typer.Argument(help="Crawl database written by crawl --db.")],
    kind: Annotated[
        str | None,
        typer.Option(
            "--kind",
            help=f"Only findings of one kind: {', '.join(KINDS)}.",
        ),
    ] = None,
) -> None:
    """Every structured data finding, one tab-separated line each.

    Columns: kind (the rule id without ``schema.``), URL, schema.org type,
    property path, message. A table of the types found goes to stderr.
    """
    if kind is not None and kind not in KINDS:
        fail(f"--kind must be one of {', '.join(KINDS)}")
    found = structured_report(load_view(db))
    table = Table(title="Structured data types")
    table.add_column("Type")
    table.add_column("Items", justify="right")
    table.add_column("Pages", justify="right")
    table.add_column("Rich result")
    for row in found.types:
        table.add_row(row.type, str(row.items), str(row.pages), row.rich_result or "-")
    err.print(table)
    for url, finding in found.findings:
        if kind is None or finding.kind == kind:
            typer.echo(f"{finding.kind}\t{url}\t{finding.type}\t{finding.path}\t{finding.message}")
    err.print(f"[green]{found.summary()}[/green]")
    err.print(
        "Per-page findings are audit rules: sitecrawler audit, then "
        "sitecrawler issues --rule schema.missing_required"
    )
