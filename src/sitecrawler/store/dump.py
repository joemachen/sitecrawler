"""Flat, export-ready views over a stored crawl.

Writers in :mod:`sitecrawler.export` only serialise what they are given; the
joins that make each table self-explanatory (a page URL next to each hop or
link) live here, inside the store.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from sitecrawler.models import Extraction, PageRecord
from sitecrawler.store.schema import (
    ExtractionRow,
    HreflangRow,
    IssueRow,
    LinkRow,
    PageRow,
    RedirectHopRow,
    SitemapRow,
    SitemapUrlRow,
    StructuredRow,
)
from sitecrawler.store.store import render_diff_from_row

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
    "sitemaps",
    "sitemap_urls",
    "extractions",
    "structured_data",
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
    "render_status",
    "render_changes",
    "inlinks",
    "link_depth",
    "link_score",
    "content_words",
    "content_hash",
    "simhash",
    "structured_types",
)
"""Column names of the ``pages`` dump, in order.

A crawl with custom extractors or searches appends one ``extract_<name>`` or
``search_<name>`` column per name after these, in first-seen order.
"""


def _render_cells(page: PageRow) -> tuple[str, str]:
    """``render_status`` (``rendered``, ``failed`` or empty) and what changed, or the error."""
    row = page.render
    if row is None:
        return "", ""
    diff = render_diff_from_row(row)
    if diff is None:
        return "failed", row.error
    return "rendered", diff.describe()


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
        *_render_cells(page),
        page.inlinks,
        page.link_depth,
        page.link_score,
        html.content_words if html else None,
        html.content_hash if html else None,
        html.simhash if html else None,
        " ".join(dict.fromkeys(t for s in page.structured for t in s.types.split())),
    )


def _extraction_names(session: Session) -> list[tuple[str, str]]:
    rows = session.execute(
        select(ExtractionRow.name, ExtractionRow.kind)
        .group_by(ExtractionRow.name, ExtractionRow.kind)
        .order_by(func.min(ExtractionRow.id))
    ).all()
    return [(name, kind) for name, kind in rows]


def _pages(session: Session) -> TableDump:
    pages = session.scalars(
        select(PageRow)
        .where(PageRow.state == "done")
        .order_by(PageRow.url)
        .options(
            selectinload(PageRow.html),
            selectinload(PageRow.render),
            selectinload(PageRow.extractions),
            selectinload(PageRow.structured),
        )
    ).all()
    names = _extraction_names(session)
    columns = (*PAGE_COLUMNS, *(Extraction(name, kind).column for name, kind in names))
    rows: list[tuple[Cell, ...]] = []
    for page in pages:
        found = {
            (e.name, e.kind): Extraction(e.name, e.kind, tuple(json.loads(e.values_json)), e.count)
            for e in page.extractions
        }
        extra: list[Cell] = [found[key].cell if key in found else None for key in names]
        rows.append((*_page_row(page), *extra))
    return TableDump("pages", columns, rows)


def _extractions(session: Session) -> TableDump:
    found = session.execute(
        select(PageRow.url, ExtractionRow)
        .join(ExtractionRow, ExtractionRow.page_id == PageRow.id)
        .order_by(PageRow.url, ExtractionRow.id)
    ).all()
    return TableDump(
        "extractions",
        ("url", "name", "kind", "count", "value"),
        [(url, e.name, e.kind, e.count, " | ".join(json.loads(e.values_json))) for url, e in found],
    )


def _structured_data(session: Session) -> TableDump:
    found = session.execute(
        select(PageRow.url, StructuredRow)
        .join(StructuredRow, StructuredRow.page_id == PageRow.id)
        .order_by(PageRow.url, StructuredRow.id)
    ).all()
    return TableDump(
        "structured_data",
        ("url", "line", "format", "types", "error", "json"),
        [(url, s.line, s.format, s.types, s.error, s.data_json) for url, s in found],
    )


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
        ("src_url", "dst_url", "anchor_text", "rel", "nofollow", "is_internal", "position"),
        [
            (
                url,
                link.dst_url,
                link.anchor_text,
                link.rel,
                link.nofollow,
                link.is_internal,
                link.position,
            )
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


def _sitemaps(session: Session) -> TableDump:
    files = session.scalars(select(SitemapRow).order_by(SitemapRow.id)).all()
    return TableDump(
        "sitemaps",
        ("url", "found_in", "kind", "status_code", "url_count", "error"),
        [(f.url, f.found_in, f.kind, f.status_code, f.url_count, f.error) for f in files],
    )


def _sitemap_urls(session: Session) -> TableDump:
    sitemap_urls = session.scalars(
        select(SitemapUrlRow).order_by(SitemapUrlRow.sitemap_url, SitemapUrlRow.loc)
    ).all()
    return TableDump(
        "sitemap_urls",
        ("sitemap_url", "loc", "lastmod", "changefreq", "priority"),
        [(s.sitemap_url, s.loc, s.lastmod, s.changefreq, s.priority) for s in sitemap_urls],
    )


_LOADERS: dict[str, Callable[[Session], TableDump]] = {
    "pages": _pages,
    "issues": _issues,
    "links": _links,
    "redirects": _redirects,
    "hreflang": _hreflang,
    "sitemaps": _sitemaps,
    "sitemap_urls": _sitemap_urls,
    "extractions": _extractions,
    "structured_data": _structured_data,
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
