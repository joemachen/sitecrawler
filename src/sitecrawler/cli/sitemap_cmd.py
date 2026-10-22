"""The ``sitecrawler sitemap`` commands: ``report`` and ``generate``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from sitecrawler.analysis import sitemap_report
from sitecrawler.audit import CrawlView
from sitecrawler.cli._run import err, fail, require_crawl_db
from sitecrawler.export import site_origin, sitemap_urls_for, write_sitemap
from sitecrawler.store import open_store

sitemap_app = typer.Typer(
    name="sitemap",
    help="Compare a crawl with the site's sitemaps, or write a sitemap from a crawl.",
    no_args_is_help=True,
)


def _view(db: Path) -> tuple[CrawlView, str]:
    """The stored crawl as a view, plus its start URL (empty in list mode)."""
    require_crawl_db(db)
    with open_store(db) as store:
        try:
            return CrawlView.from_store(store), store.crawl().start_url
        except ValueError as exc:
            fail(str(exc))
            raise  # unreachable: fail() exits


@sitemap_app.command()
def report(
    db: Annotated[Path, typer.Argument(help="Crawl database written by crawl --db.")],
) -> None:
    """Which sitemap files the crawl read, and the entries that match no page."""
    crawl, _ = _view(db)
    found = sitemap_report(crawl)
    table = Table(title=f"Sitemap files in {db}")
    table.add_column("Sitemap")
    table.add_column("Found in")
    table.add_column("Kind")
    table.add_column("Status", justify="right")
    table.add_column("URLs", justify="right")
    table.add_column("Problem")
    for file in found.files:
        table.add_row(
            file.url,
            file.found_in,
            file.kind,
            "" if file.status_code is None else str(file.status_code),
            str(file.url_count) if file.ok else "",
            file.error,
        )
    err.print(table)
    for entry in found.other_host:
        typer.echo(f"other host\t{entry.loc}\t{entry.sitemap_url}")
    for entry in found.not_crawled:
        typer.echo(f"not crawled\t{entry.loc}\t{entry.sitemap_url}")
    for entries in found.duplicates.values():
        files = ", ".join(e.sitemap_url for e in entries)
        typer.echo(f"duplicate\t{entries[0].loc}\t{files}")
    err.print(f"[green]{found.summary()}[/green]")
    err.print(
        "Per-page findings (orphans, non-indexable entries, missing pages) are audit "
        "rules: sitecrawler audit, then sitecrawler issues --rule sitemap.orphan"
    )


@sitemap_app.command()
def generate(
    db: Annotated[Path, typer.Argument(help="Crawl database written by crawl --db.")],
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="File to write. Default: sitemap.xml next to DB."),
    ] = None,
    lastmod: Annotated[
        bool,
        typer.Option("--lastmod", help="Add <lastmod> from each page's Last-Modified header."),
    ] = False,
    base_url: Annotated[
        str,
        typer.Option(
            "--base-url",
            help="Where the files will be served from, for the index when over 50,000 URLs. "
            "Default: the crawl's start URL origin.",
        ),
    ] = "",
) -> None:
    """Write a sitemap of every indexable 200 page in the crawl (an index when over 50,000)."""
    crawl, start_url = _view(db)
    output = output or db.with_name("sitemap.xml")
    base_url = base_url or site_origin(start_url)
    urls = sitemap_urls_for(crawl, lastmod=lastmod)
    try:
        written = write_sitemap(urls, output, base_url=base_url)
    except (ValueError, OSError) as exc:
        fail(f"cannot write {output}: {exc}" if isinstance(exc, OSError) else str(exc))
        return
    files = ", ".join(str(path) for path in written)
    err.print(f"[green]{len(urls)} URLs written to {files}[/green]")
