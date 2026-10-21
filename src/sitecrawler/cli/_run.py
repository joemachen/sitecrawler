"""Shared glue for the ``crawl`` and ``list`` commands: run, store, export, summarise."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from sitecrawler.crawl import Crawler
from sitecrawler.export import write_csv
from sitecrawler.models import CrawlConfig, Outcome, PageRecord
from sitecrawler.store import open_store

err = Console(stderr=True)


def fail(message: str) -> None:
    """Print ``message`` in red and exit with status 2 (configuration error)."""
    err.print(f"[red]{message}[/red]")
    raise typer.Exit(code=2)


def require_crawl_db(path: Path) -> None:
    """Exit 2 unless ``path`` is an existing SQLite file (does not open it)."""
    if not path.is_file():
        fail(f"{path} is not a file")
    header = path.read_bytes()[:16] if path.stat().st_size else b""
    if not header.startswith(b"SQLite format 3"):
        fail(f"{path} is not a SQLite database")


def run_crawl(config: CrawlConfig, *, db: Path | None, resume: bool, output: Path | None) -> None:
    """Run ``config`` to completion, storing and/or exporting as asked.

    Without ``db`` the records stay in memory and go to ``output`` (default
    ``pages.csv``). With ``db`` they go to the store, and ``output`` (if given)
    is written from the store so it is right after a resume.
    """
    if resume and db is None:
        fail("--resume needs --db to say which crawl to continue")
    if db is not None and resume and not db.exists():
        fail(f"{db} does not exist, so there is nothing to resume")

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
                where = f"{store.count_pages('done')} pages in {db}"
                if output is not None:
                    written = write_csv(store.iter_pages(), output)
                    where += f", {written} written to {output}"
                _summary(records, where)
    except ValueError as exc:
        fail(str(exc))


def _summary(records: list[PageRecord], where: str) -> None:
    ok = sum(1 for r in records if r.status_code == 200)
    blocked = sum(1 for r in records if r.outcome is Outcome.BLOCKED)
    err.print(f"[green]{where}[/green] (this run: {ok} returned 200, {blocked} blocked)")
