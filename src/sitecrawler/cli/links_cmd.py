"""The ``sitecrawler links`` commands: ``report`` and ``anchors``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from sitecrawler.analysis import anchor_texts, link_report
from sitecrawler.audit import CrawlView
from sitecrawler.cli._run import err, fail, require_crawl_db
from sitecrawler.models import LinkMetrics
from sitecrawler.store import open_store

links_app = typer.Typer(
    name="links",
    help="Internal linking: Link Score, links to errors and redirects, anchor text per page.",
    no_args_is_help=True,
)


def _view(db: Path) -> CrawlView:
    """The stored crawl as a view."""
    require_crawl_db(db)
    with open_store(db) as store:
        try:
            return CrawlView.from_store(store)
        except ValueError as exc:
            fail(str(exc))
            raise  # unreachable: fail() exits


@links_app.command()
def report(
    db: Annotated[Path, typer.Argument(help="Crawl database written by crawl --db.")],
    top: Annotated[
        int, typer.Option("--top", help="Pages to show at each end of the Link Score table.")
    ] = 10,
) -> None:
    """Link Score extremes, then every internal link to an error or a redirect, with its anchor."""
    crawl = _view(db)
    found = link_report(crawl)
    metrics = crawl.link_graph.metrics
    ranked = sorted(metrics.items(), key=lambda kv: (-kv[1].link_score, kv[0]))
    if top <= 0:
        shown: list[tuple[str, LinkMetrics] | None] = []
    elif len(ranked) <= 2 * top:
        shown = list(ranked)
    else:
        shown = [*ranked[:top], None, *ranked[len(ranked) - top :]]
    table = Table(title=f"Link Score in {db}")
    table.add_column("URL")
    table.add_column("Score", justify="right")
    table.add_column("Inlinks", justify="right")
    table.add_column("Depth", justify="right")
    for entry in shown:
        if entry is None:
            table.add_row("...", "", "", "")
            continue
        url, m = entry
        table.add_row(
            url,
            str(m.link_score),
            str(m.inlinks),
            "" if m.link_depth is None else str(m.link_depth),
        )
    err.print(table)
    for problem in found.broken:
        typer.echo(
            f"error\t{problem.src}\t{problem.link.href}\t{problem.target}\t{problem.link.text}"
        )
    for problem in found.redirecting:
        typer.echo(
            f"redirect\t{problem.src}\t{problem.link.href}\t{problem.target}\t{problem.link.text}"
        )
    err.print(f"[green]{found.summary()}[/green]")
    err.print(
        "Per-page findings (few inlinks, deep pages, generic anchors, nofollow links) are "
        "audit rules: sitecrawler audit, then sitecrawler issues --rule link.few_inlinks"
    )


@links_app.command()
def anchors(
    db: Annotated[Path, typer.Argument(help="Crawl database written by crawl --db.")],
    url: Annotated[
        str | None, typer.Argument(help="Only this target page (any form of its URL).")
    ] = None,
) -> None:
    """What the site calls each page: one line per target URL and anchor text, with a count."""
    crawl = _view(db)
    texts = anchor_texts(crawl)
    if url is not None:
        page = crawl.page_for(url)
        if page is None:
            fail(f"{url} is not a page in {db}")
            return
        texts = {page.url: texts.get(page.url, [])}
    for target, counted in texts.items():
        for text, count in counted:
            typer.echo(f"{target}\t{count}\t{text}")
    pages = sum(1 for counted in texts.values() if counted)
    err.print(f"[green]{pages} linked page(s)[/green]")
