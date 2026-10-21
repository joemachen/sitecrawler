"""The ``sitecrawler list`` command: fetch exactly the URLs you give it."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from sitecrawler.cli._run import fail, run_crawl
from sitecrawler.crawl.urls import parse_url_list
from sitecrawler.models import CrawlConfig


def list_urls(
    source: Annotated[str, typer.Argument(help="Text file with one URL per line, or - for stdin.")],
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
    follow: Annotated[
        bool, typer.Option("--follow", help="Also follow links, staying on the listed hosts.")
    ] = False,
    max_pages: Annotated[int, typer.Option(help="Stop after this many pages.")] = 5000,
    delay: Annotated[float, typer.Option(help="Minimum seconds between requests per host.")] = 0.5,
    workers: Annotated[int, typer.Option(help="Concurrent fetchers.")] = 4,
    timeout: Annotated[float, typer.Option(help="Per-request timeout in seconds.")] = 20.0,
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
    """Fetch exactly the URLs in SOURCE (no link following unless --follow)."""
    if source == "-":
        text = sys.stdin.read()
    else:
        path = Path(source)
        if not path.is_file():
            fail(f"{path} is not a file")
        text = path.read_text(encoding="utf-8")
    urls = parse_url_list(text.splitlines())
    if not urls:
        fail("no URLs found in the list")

    config = CrawlConfig(
        seed_urls=tuple(urls),
        follow_links=follow,
        max_pages=max_pages,
        delay_seconds=delay,
        workers=workers,
        timeout_seconds=timeout,
        use_sitemap=False,
        keep_query=keep_query,
        respect_robots=not ignore_robots,
        max_redirects=max_redirects,
        http2=not no_http2,
    )
    run_crawl(config, db=db, resume=resume, output=output)
