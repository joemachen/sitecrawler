"""Flat, export-ready views over a stored crawl.

Writers in :mod:`sitecrawler.export` only serialise what they are given; the
joins that make each table self-explanatory (a page URL next to each hop or
link) live here, inside the store.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sitecrawler.models import PageRecord
from sitecrawler.store.schema import (
    HreflangRow,
    IssueRow,
    LinkRow,
    PageRow,
    RedirectHopRow,
    SitemapUrlRow,
)

if TYPE_CHECKING:
    from sitecrawler.store.store import Store

Cell = str | int | float | bool | None
"""Values a dumped cell may hold; every writer can serialise these."""

EXPORT_TABLES: tuple[str, ...] = (
    "pages",
    "issues",
    "links",
    "redirects",
    "hreflang",
    "sitemap_urls",
)
"""Names (and order) of the tables every export contains."""


@dataclass(slots=True, frozen=True)
class TableDump:
    """One table ready to write: a name, its column names and its rows."""

    name: str
    columns: tuple[str, ...]
    rows: list[tuple[Cell, ...]]


PAGE_COLUMNS: tuple[str, ...] = (
    "url",
    "status",
    "outcome",
    "status_code",
    "final_url",
    "content_type",
    "size_bytes",
    "depth",
    "found_on",
    "title",
    "meta_description",
    "meta_robots",
    "canonical",
    "h1",
    "lang",
    "word_count",
    "internal_links",
    "x_robots_tag",
    "last_modified",
    "fetch_ms",
    "error",
    "fetched_at",
    "indexable",
    "indexability_reason",
)
"""Column names of the ``pages`` dump, in order."""


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value is not None else None


def _page_row(page: PageRow) -> tuple[Cell, ...]:
    html = page.html
    return (
        page.url,
        PageRecord.status_text(page.status_code, page.outcome or ""),
        page.outcome,
        page.status_code,
        page.final_url,
        page.content_type,
        page.size_bytes,
        page.depth,
        page.found_on,
        html.title if html else "",
        html.meta_description if html else "",
        html.meta_robots if html else "",
        html.canonical if html else "",
        html.h1 if html else "",
        html.lang if html else "",
        html.word_count if html else 0,
        html.internal_links if html else 0,
        page.x_robots_tag,
        page.last_modified,
        page.fetch_ms,
        page.error,
        _iso(page.fetched_at),
        page.indexable,
        page.indexability_reason,
    )


def _pages(session: Session) -> TableDump:
    pages = session.scalars(
        select(PageRow)
        .where(PageRow.state == "done")
        .order_by(PageRow.url)
        .options(selectinload(PageRow.html))
    ).all()
    return TableDump("pages", PAGE_COLUMNS, [_page_row(p) for p in pages])


def _issues(session: Session) -> TableDump:
    issues = session.execute(
        select(PageRow.url, IssueRow)
        .join(IssueRow, IssueRow.page_id == PageRow.id)
        .order_by(IssueRow.rule_id, PageRow.url)
    ).all()
    return TableDump(
        "issues",
        ("url", "rule_id", "severity", "message"),
        [(url, i.rule_id, i.severity, i.message) for url, i in issues],
    )


def _links(session: Session) -> TableDump:
    links = session.execute(
        select(PageRow.url, LinkRow)
        .join(LinkRow, LinkRow.page_id == PageRow.id)
        .order_by(PageRow.url, LinkRow.id)
    ).all()
    return TableDump(
        "links",
        ("src_url", "dst_url", "anchor_text", "rel", "nofollow", "is_internal"),
        [
            (url, link.dst_url, link.anchor_text, link.rel, link.nofollow, link.is_internal)
            for url, link in links
        ],
    )


def _redirects(session: Session) -> TableDump:
    hops = session.execute(
        select(PageRow.url, RedirectHopRow)
        .join(RedirectHopRow, RedirectHopRow.page_id == PageRow.id)
        .order_by(PageRow.url, RedirectHopRow.hop_no)
    ).all()
    return TableDump(
        "redirects",
        ("url", "hop_no", "from_url", "to_url", "status_code"),
        [(url, h.hop_no, h.from_url, h.to_url, h.status_code) for url, h in hops],
    )


def _hreflang(session: Session) -> TableDump:
    hreflang = session.execute(
        select(PageRow.url, HreflangRow)
        .join(HreflangRow, HreflangRow.page_id == PageRow.id)
        .order_by(PageRow.url, HreflangRow.id)
    ).all()
    return TableDump(
        "hreflang", ("url", "lang", "href"), [(url, h.lang, h.href) for url, h in hreflang]
    )


def _sitemap_urls(session: Session) -> TableDump:
    sitemap_urls = session.scalars(
        select(SitemapUrlRow).order_by(SitemapUrlRow.sitemap_url, SitemapUrlRow.loc)
    ).all()
    return TableDump(
        "sitemap_urls", ("sitemap_url", "loc"), [(s.sitemap_url, s.loc) for s in sitemap_urls]
    )


_LOADERS: dict[str, Callable[[Session], TableDump]] = {
    "pages": _pages,
    "issues": _issues,
    "links": _links,
    "redirects": _redirects,
    "hreflang": _hreflang,
    "sitemap_urls": _sitemap_urls,
}


def dump_tables(store: Store, names: Iterable[str] = EXPORT_TABLES) -> list[TableDump]:
    """Read export tables from ``store`` into memory, in :data:`EXPORT_TABLES` order.

    Args:
        store: An open store.
        names: Which tables to read; default all. Readers that only need a
            few (the web UI) skip the links table, by far the largest.

    Raises:
        ValueError: for a name that is not in :data:`EXPORT_TABLES`.
    """
    wanted = set(names)
    if unknown := wanted - set(EXPORT_TABLES):
        msg = f"unknown export tables: {sorted(unknown)}"
        raise ValueError(msg)
    with Session(store.engine) as session:
        return [_LOADERS[name](session) for name in EXPORT_TABLES if name in wanted]
