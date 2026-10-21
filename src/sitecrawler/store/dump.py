"""Flat, export-ready views over a stored crawl.

Writers in :mod:`sitecrawler.export` only serialise what they are given; the
joins that make each table self-explanatory (a page URL next to each hop or
link) live here, inside the store.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from sitecrawler.store.schema import LinkRow, PageRow, RedirectHopRow, SitemapUrlRow

if TYPE_CHECKING:
    from sitecrawler.store.store import Store

Cell = str | int | float | bool | None
"""Values a dumped cell may hold; every writer can serialise these."""

EXPORT_TABLES: tuple[str, ...] = ("pages", "links", "redirects", "sitemap_urls")
"""Names (and order) of the tables every export contains."""


@dataclass(slots=True, frozen=True)
class TableDump:
    """One table ready to write: a name, its column names and its rows."""

    name: str
    columns: tuple[str, ...]
    rows: list[tuple[Cell, ...]]


_PAGE_COLUMNS = (
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
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec="seconds") if value is not None else None


def _page_row(page: PageRow) -> tuple[Cell, ...]:
    html = page.html
    status = str(page.status_code) if page.status_code is not None else (page.outcome or "")
    return (
        page.url,
        status,
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
    )


def dump_tables(store: Store) -> list[TableDump]:
    """Read every export table from ``store`` into memory, in :data:`EXPORT_TABLES` order."""
    with Session(store.engine) as session:
        pages = session.scalars(
            select(PageRow)
            .where(PageRow.state == "done")
            .order_by(PageRow.url)
            .options(selectinload(PageRow.html))
        ).all()
        links = session.execute(
            select(PageRow.url, LinkRow)
            .join(LinkRow, LinkRow.page_id == PageRow.id)
            .order_by(PageRow.url, LinkRow.id)
        ).all()
        hops = session.execute(
            select(PageRow.url, RedirectHopRow)
            .join(RedirectHopRow, RedirectHopRow.page_id == PageRow.id)
            .order_by(PageRow.url, RedirectHopRow.hop_no)
        ).all()
        sitemap_urls = session.scalars(
            select(SitemapUrlRow).order_by(SitemapUrlRow.sitemap_url, SitemapUrlRow.loc)
        ).all()
        return [
            TableDump("pages", _PAGE_COLUMNS, [_page_row(p) for p in pages]),
            TableDump(
                "links",
                ("src_url", "dst_url", "anchor_text", "rel", "nofollow", "is_internal"),
                [
                    (url, link.dst_url, link.anchor_text, link.rel, link.nofollow, link.is_internal)
                    for url, link in links
                ],
            ),
            TableDump(
                "redirects",
                ("url", "hop_no", "from_url", "to_url", "status_code"),
                [(url, h.hop_no, h.from_url, h.to_url, h.status_code) for url, h in hops],
            ),
            TableDump(
                "sitemap_urls",
                ("sitemap_url", "loc"),
                [(s.sitemap_url, s.loc) for s in sitemap_urls],
            ),
        ]
