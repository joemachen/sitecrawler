"""The ``sitecrawler`` command."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.logging import RichHandler

from sitecrawler import __version__
from sitecrawler.cli._run import err, extraction_config, run_crawl
from sitecrawler.cli.audit_cmd import audit, issues
from sitecrawler.cli.desktop_cmd import desktop
from sitecrawler.cli.duplicates_cmd import duplicates_app
from sitecrawler.cli.export_cmd import export
from sitecrawler.cli.links_cmd import links_app
from sitecrawler.cli.list_urls import list_urls
from sitecrawler.cli.schema_cmd import schema_app
from sitecrawler.cli.serve_cmd import serve
from sitecrawler.cli.sitemap_cmd import sitemap_app
from sitecrawler.models import CrawlConfig

app = typer.Typer(
    name="sitecrawler",
    help="Crawl a site and report on every page.",
    no_args_is_help=True,
    add_completion=False,
)


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
    render: Annotated[
        bool,
        typer.Option(
            "--render",
            help="Also load each HTML page in headless Chromium and parse the rendered DOM.",
        ),
    ] = False,
    render_workers: Annotated[
        int, typer.Option(help="Browser tabs open at once (with --render).")
    ] = 2,
    render_wait: Annotated[
        str,
        typer.Option(help="When a page counts as loaded: load, domcontentloaded or networkidle."),
    ] = "networkidle",
    render_selector: Annotated[
        str, typer.Option(help="CSS selector to wait for after the page loads (with --render).")
    ] = "",
    render_timeout: Annotated[
        float, typer.Option(help="Seconds before a render is given up (with --render).")
    ] = 30.0,
    extract: Annotated[
        list[str] | None,
        typer.Option(
            "--extract",
            help="Custom extractor NAME=css:SELECTOR, NAME=xpath:EXPR or NAME=regex:PATTERN; "
            "repeatable. Modifiers go in brackets: css[attr=src,all]:img.",
        ),
    ] = None,
    extract_file: Annotated[
        Path | None,
        typer.Option("--extract-file", help="TOML file with [extract] and [search] tables."),
    ] = None,
    search: Annotated[
        list[str] | None,
        typer.Option(
            "--search",
            help="Flag pages whose HTML matches this regex (case-insensitive); "
            "NAME=PATTERN names the column. Repeatable.",
        ),
    ] = None,
) -> None:
    """Spider a site from URL and write every page found to a CSV."""
    extractors, searches = extraction_config(extract or [], extract_file, search or [])
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
        render=render,
        render_workers=render_workers,
        render_wait=render_wait,
        render_selector=render_selector,
        render_timeout_seconds=render_timeout,
        extract=extractors,
        search=searches,
    )
    run_crawl(config, db=db, resume=resume, output=output)


app.command("list")(list_urls)
app.command("export")(export)
app.command("audit")(audit)
app.command("issues")(issues)
app.command("serve")(serve)
app.command("desktop")(desktop)
app.add_typer(sitemap_app, name="sitemap")
app.add_typer(links_app, name="links")
app.add_typer(duplicates_app, name="duplicates")
app.add_typer(schema_app, name="schema")
