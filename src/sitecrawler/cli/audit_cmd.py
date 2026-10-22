"""The ``sitecrawler audit`` and ``sitecrawler issues`` commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from sitecrawler.analysis import link_report, sitemap_report
from sitecrawler.audit import CrawlView, load_rules, rule_by_id, run_audit
from sitecrawler.cli._run import err, fail, require_crawl_db
from sitecrawler.store import open_store


def audit(
    db: Annotated[Path, typer.Argument(help="Crawl database written by crawl --db or list --db.")],
) -> None:
    """Run every audit rule over a stored crawl, store the issues and print the fix list."""
    require_crawl_db(db)
    with open_store(db) as store:
        try:
            crawl = CrawlView.from_store(store)
        except ValueError as exc:
            fail(str(exc))
            return
        result = run_audit(crawl)
        stored = store.replace_issues(result.issues)
        store.set_indexability(result.verdicts)
        store.set_link_metrics(result.links)

    table = Table(title=f"Issues in {db}", show_lines=False)
    table.add_column("Severity")
    table.add_column("Rule")
    table.add_column("URLs", justify="right")
    table.add_column("Summary")
    for row in result.counts():
        table.add_row(row.rule.severity.value, row.rule.id, str(row.count), row.rule.summary)
    err.print(table)
    rendered = [p for p in crawl.pages if p.rendered or p.render_error]
    if rendered:
        changed = sum(1 for p in rendered if p.render is not None and p.render.changed)
        failed = sum(1 for p in rendered if p.render_error)
        err.print(
            f"Rendered {len(rendered)} pages in headless Chromium: {changed} differ from "
            f"their raw HTML (render.differs), {failed} could not be rendered (render.failed)."
        )
    if crawl.sitemap_files:
        err.print(f"{sitemap_report(crawl).summary()} Details: sitecrawler sitemap report {db}")
    err.print(f"{link_report(crawl).summary()} Details: sitecrawler links report {db}")
    non_indexable = sum(1 for v in result.verdicts.values() if not v.indexable)
    err.print(
        f"[green]{stored} issues across {len(result.counts())} rules on "
        f"{len(crawl.pages)} pages[/green] ({non_indexable} non-indexable). "
        f"Details: sitecrawler issues {db} --rule RULE"
    )


def issues(
    db: Annotated[Path, typer.Argument(help="Crawl database that audit has been run on.")],
    rule: Annotated[
        str | None, typer.Option("--rule", "-r", help="Only this rule id, e.g. title.missing.")
    ] = None,
) -> None:
    """List the URLs an audit flagged, one per line: severity, rule, URL, detail."""
    require_crawl_db(db)
    if rule is not None and rule_by_id(rule) is None:
        known = ", ".join(r.id for r in load_rules())
        fail(f"unknown rule {rule!r}; known rules: {known}")
    with open_store(db) as store:
        found = store.iter_issues(rule)
    if not found:
        err.print(
            "[yellow]no issues stored; run `sitecrawler audit` first or widen the filter[/yellow]"
        )
    for issue in found:
        detail = f"\t{issue.message}" if issue.message else ""
        typer.echo(f"{issue.severity.value}\t{issue.rule_id}\t{issue.url}{detail}")
