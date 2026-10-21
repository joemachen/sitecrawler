"""The ``sitecrawler`` command."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.logging import RichHandler

from sitecrawler import __version__
from sitecrawler.crawl import Crawler
from sitecrawler.export import write_csv
from sitecrawler.models import CrawlConfig, Outcome, PageRecord
from sitecrawler.store import open_store

app = typer.Typer(
    name="sitecrawler",
    help="Crawl a site and report on every page.",
    no_args_is_help=True,
    add_completion=False,
)
err = Console(stderr=True)


def _print_version(value: bool) -> None:
    if value:
        err.print(f"sitecrawler {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    _version: Annotated[
        bool,
        typer.Option("--version", callback=_print_version, is_eager=True, help="Show version."),
    ] = False,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Debug logging.")] = False,
) -> None:
    """Crawl a site and report on every page."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        handlers=[RichHandler(console=err, show_path=False, show_time=False)],
    )


@app.command()
def crawl(
    url: Annotated[str, typer.Argument(help="Start URL, e.g. https://example.com")],
    output: Annotated[
        Path | None,
        typer.Option("-o", "--output", help="CSV to write. Default pages.csv unless --db is set."),
    ] = None,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="SQLite file to store the crawl in (one crawl per file)."),
    ] = None,
    resume: Annotated[
        bool, typer.Option("--resume", help="Continue the crawl already in --db.")
    ] = False,
    max_pages: Annotated[int, typer.Option(help="Stop after this many pages.")] = 5000,
    delay: Annotated[float, typer.Option(help="Minimum seconds between requests.")] = 0.5,
    workers: Annotated[int, typer.Option(help="Concurrent fetchers.")] = 4,
    timeout: Annotated[float, typer.Option(help="Per-request timeout in seconds.")] = 20.0,
    no_sitemap: Annotated[bool, typer.Option("--no-sitemap", help="Skip sitemap seeding.")] = False,
    keep_query: Annotated[
        bool, typer.Option("--keep-query", help="Treat different query strings as pages.")
    ] = False,
    ignore_robots: Annotated[
        bool, typer.Option("--ignore-robots", help="Do not honour robots.txt.")
    ] = False,
    max_redirects: Annotated[
        int, typer.Option(help="Report redirect_loop after this many hops.")
    ] = 10,
    no_http2: Annotated[bool, typer.Option("--no-http2", help="Use HTTP/1.1 only.")] = False,
) -> None:
    """Spider a site from URL and write every page found to a CSV."""
    config = CrawlConfig(
        start_url=url,
        max_pages=max_pages,
        delay_seconds=delay,
        workers=workers,
        timeout_seconds=timeout,
        use_sitemap=not no_sitemap,
        keep_query=keep_query,
        respect_robots=not ignore_robots,
        max_redirects=max_redirects,
        http2=not no_http2,
    )
    if resume and db is None:
        _fail("--resume needs --db to say which crawl to continue")
    if db is not None and db.exists() and not resume:
        _fail(f"{db} already exists; pass --resume to continue it or choose a new file")
    if db is not None and resume and not db.exists():
        _fail(f"{db} does not exist, so there is nothing to resume")

    def progress(record: PageRecord, done: int, queued: int) -> None:
        if done % 25 == 0 or queued == 0:
            err.print(f"[dim]{done} fetched, {queued} queued[/dim]  {record.status} {record.url}")

    try:
        if db is None:
            output = output or Path("pages.csv")
            records = Crawler(config).run(on_progress=progress)
            written = write_csv(records, output)
            _summary(records, f"{written} pages written to {output}")
        else:
            with open_store(db) as store:
                records = Crawler(config, sink=store, resume=resume).run(on_progress=progress)
                total = store.count_pages("done")
                where = f"{total} pages in {db}"
                if output is not None:
                    written = write_csv(store.iter_pages(), output)
                    where += f", {written} written to {output}"
                _summary(records, where)
    except ValueError as exc:
        _fail(str(exc))


def _fail(message: str) -> None:
    err.print(f"[red]{message}[/red]")
    raise typer.Exit(code=2)


def _summary(records: list[PageRecord], where: str) -> None:
    ok = sum(1 for r in records if r.status_code == 200)
    blocked = sum(1 for r in records if r.outcome is Outcome.BLOCKED)
    err.print(f"[green]{where}[/green] (this run: {ok} returned 200, {blocked} blocked)")
