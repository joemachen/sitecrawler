"""The ``sitecrawler duplicates`` commands: ``report``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from sitecrawler.analysis import duplicate_report, member_status
from sitecrawler.audit import CrawlView
from sitecrawler.audit.duplicates import NEAR_DUPLICATE_DISTANCE, Cluster, DuplicateIndex
from sitecrawler.cli._run import err, fail, require_crawl_db
from sitecrawler.parse.fingerprint import BITS
from sitecrawler.store import open_store

duplicates_app = typer.Typer(
    name="duplicates",
    help="Duplicate and near-duplicate content: every cluster, with each member's indexability.",
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


def _print_cluster(crawl: CrawlView, kind: str, cluster: Cluster) -> None:
    representative = next(p for p in cluster.members if p.url == cluster.representative)
    for member in cluster.members:
        distance = DuplicateIndex.distance(representative, member)
        typer.echo(
            f"{kind}\t{cluster.representative}\t{member.url}\t{distance}\t"
            f"{member_status(crawl, member)}"
        )


@duplicates_app.command()
def report(
    db: Annotated[Path, typer.Argument(help="Crawl database written by crawl --db.")],
    max_distance: Annotated[
        int,
        typer.Option(
            "--max-distance",
            help=f"SimHash bits (of {BITS}) two near-duplicates may differ by.",
        ),
    ] = NEAR_DUPLICATE_DISTANCE,
) -> None:
    """Every duplicate group and near-duplicate cluster, one tab-separated line per member.

    Columns: kind (exact or near), representative URL, member URL, SimHash
    distance from the representative, the member's indexability.
    """
    if not 0 <= max_distance < BITS:
        fail(f"--max-distance must be between 0 and {BITS - 1}")
    crawl = _view(db)
    found = duplicate_report(crawl, max_distance)
    for cluster in found.exact:
        _print_cluster(crawl, "exact", cluster)
    for cluster in found.near:
        _print_cluster(crawl, "near", cluster)
    err.print(f"[green]{found.summary()}[/green]")
    err.print(
        "Per-page findings (duplicate, near-duplicate and low-content pages) are audit "
        "rules: sitecrawler audit, then sitecrawler issues --rule content.duplicate"
    )
