"""Shared glue for the ``crawl`` and ``list`` commands: run, store, export, summarise."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import typer
from rich.console import Console

from sitecrawler.audit import CrawlView
from sitecrawler.crawl import Crawler
from sitecrawler.export import write_csv
from sitecrawler.models import CrawlConfig, ExtractorSpec, Outcome, PageRecord, SearchSpec
from sitecrawler.parse import compile_extractors, load_extract_toml, parse_extractor, parse_searches
from sitecrawler.store import crawl_file_problem, open_store

err = Console(stderr=True)


def fail(message: str) -> None:
    """Print ``message`` in red and exit with status 2 (configuration error)."""
    err.print(f"[red]{message}[/red]")
    raise typer.Exit(code=2)


def require_crawl_db(path: Path) -> None:
    """Exit 2 unless ``path`` is an existing SQLite file (does not open it)."""
    if problem := crawl_file_problem(path):
        fail(problem)


def load_view(db: Path) -> CrawlView:
    """The stored crawl at ``db`` as a view; exits 2 when it cannot be read."""
    require_crawl_db(db)
    with open_store(db) as store:
        try:
            return CrawlView.from_store(store)
        except ValueError as exc:
            fail(str(exc))
            raise  # unreachable: fail() exits


def extraction_config(
    extract: Sequence[str], extract_file: Path | None, search: Sequence[str]
) -> tuple[tuple[ExtractorSpec, ...], tuple[SearchSpec, ...]]:
    """Parse ``--extract``, ``--extract-file`` and ``--search``.

    Exits 2 on anything that does not compile. File entries come first, then
    the command-line ones, so columns follow that order.
    """
    extractors: list[ExtractorSpec] = []
    searches: list[SearchSpec] = []
    if extract_file is not None and not extract_file.is_file():
        fail(f"{extract_file} is not a file")
    try:
        if extract_file is not None:
            from_file = load_extract_toml(extract_file.read_text(encoding="utf-8"))
            extractors.extend(from_file[0])
            searches.extend(from_file[1])
        extractors.extend(parse_extractor(text) for text in extract)
        searches.extend(parse_searches(search))
        compile_extractors(extractors, searches)  # rejects a name used twice
    except ValueError as exc:
        fail(str(exc))
    return tuple(extractors), tuple(searches)


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
            columns = [*(s.column for s in config.extract), *(s.column for s in config.search)]
            written = write_csv(records, output, extra_columns=columns)
            _summary(records, f"{written} pages written to {output}", config)
        else:
            with open_store(db) as store:
                records = Crawler(config, sink=store, resume=resume).run(on_progress=progress)
                where = f"{store.count_pages('done')} pages in {db}"
                if output is not None:
                    written = write_csv(
                        store.iter_pages(), output, extra_columns=store.extraction_columns()
                    )
                    where += f", {written} written to {output}"
                _summary(records, where, config)
    except ValueError as exc:
        fail(str(exc))


def _summary(records: list[PageRecord], where: str, config: CrawlConfig) -> None:
    ok = sum(1 for r in records if r.status_code == 200)
    blocked = sum(1 for r in records if r.outcome is Outcome.BLOCKED)
    err.print(f"[green]{where}[/green] (this run: {ok} returned 200, {blocked} blocked)")
    for spec in config.search:
        checked = [e for r in records for e in r.extractions if e.name == spec.name]
        hits = sum(1 for e in checked if e.matched)
        err.print(
            f"search {spec.name}: {hits} of {len(checked)} HTML pages contain it, "
            f"{len(checked) - hits} do not"
        )
