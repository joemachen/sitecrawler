"""SQLite schema, declared with SQLAlchemy 2.0.

One file holds one crawl. Row classes end in ``Row`` so they never clash with
the dataclasses in :mod:`sitecrawler.models`, which remain the records that
cross package boundaries. JSON columns are plain ``TEXT`` holding ``json.dumps``
output; enums are stored by their string value.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for every table."""


class CrawlRow(Base):
    """One row per crawl run; a file holds exactly one."""

    __tablename__ = "crawls"

    id: Mapped[int] = mapped_column(primary_key=True)
    start_url: Mapped[str]
    mode: Mapped[str] = mapped_column(default="crawl")
    """``crawl`` (spider from a start URL) or ``list`` (fetch given URLs)."""
    config_json: Mapped[str]
    version: Mapped[str]
    """sitecrawler version that wrote the file; doubles as the schema version."""
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(default="running")
    """``running`` until :meth:`~sitecrawler.store.Store.finish`; then ``done``."""
    pages_done: Mapped[int] = mapped_column(default=0)


class PageRow(Base):
    """One row per URL the crawl queued; ``state`` says whether it was fetched."""

    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("crawl_id", "url"),
        Index("ix_pages_crawl_state", "crawl_id", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    crawl_id: Mapped[int] = mapped_column(ForeignKey("crawls.id"))
    url: Mapped[str]
    state: Mapped[str] = mapped_column(default="pending")
    """``pending`` (queued, not fetched) or ``done``."""
    depth: Mapped[int]
    found_on: Mapped[str]
    outcome: Mapped[str | None] = mapped_column(default=None)
    status_code: Mapped[int | None] = mapped_column(default=None)
    final_url: Mapped[str] = mapped_column(default="")
    content_type: Mapped[str] = mapped_column(default="")
    size_bytes: Mapped[int] = mapped_column(default=0)
    fetch_ms: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(default="")
    x_robots_tag: Mapped[str | None] = mapped_column(default=None)
    last_modified: Mapped[str | None] = mapped_column(default=None)
    headers_json: Mapped[str] = mapped_column(default="{}")
    fetched_at: Mapped[datetime | None] = mapped_column(default=None)
    indexable: Mapped[bool | None] = mapped_column(default=None)
    """Set by ``audit``: can this page appear in search results?"""
    indexability_reason: Mapped[str] = mapped_column(default="")
    inlinks: Mapped[int | None] = mapped_column(default=None)
    """Set by ``audit``: distinct other pages linking here (ADR-0011)."""
    link_depth: Mapped[int | None] = mapped_column(default=None)
    """Set by ``audit``: fewest clicks from the start page; NULL when unreachable."""
    link_score: Mapped[int | None] = mapped_column(default=None)
    """Set by ``audit``: PageRank over the follow graph, 0-100."""

    html: Mapped[PageHtmlRow | None] = relationship(
        back_populates="page", cascade="all, delete-orphan", uselist=False
    )
    render: Mapped[PageRenderRow | None] = relationship(
        back_populates="page", cascade="all, delete-orphan", uselist=False
    )
    hops: Mapped[list[RedirectHopRow]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="RedirectHopRow.hop_no"
    )
    links: Mapped[list[LinkRow]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="LinkRow.id"
    )
    hreflang: Mapped[list[HreflangRow]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="HreflangRow.id"
    )
    extractions: Mapped[list[ExtractionRow]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="ExtractionRow.id"
    )


class RedirectHopRow(Base):
    """One hop of a redirect chain that started at ``page``."""

    __tablename__ = "redirect_hops"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    hop_no: Mapped[int]
    from_url: Mapped[str]
    to_url: Mapped[str]
    status_code: Mapped[int]

    page: Mapped[PageRow] = relationship(back_populates="hops")


class PageHtmlRow(Base):
    """What the HTML parser extracted; one row per fetched page."""

    __tablename__ = "page_html"

    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), primary_key=True)
    title: Mapped[str] = mapped_column(default="")
    meta_description: Mapped[str] = mapped_column(default="")
    meta_robots: Mapped[str] = mapped_column(default="")
    canonical: Mapped[str] = mapped_column(default="")
    h1: Mapped[str] = mapped_column(default="")
    h1s_json: Mapped[str] = mapped_column(default="[]")
    h2s_json: Mapped[str] = mapped_column(default="[]")
    lang: Mapped[str] = mapped_column(default="")
    word_count: Mapped[int] = mapped_column(default=0)
    internal_links: Mapped[int] = mapped_column(default=0)
    title_count: Mapped[int] = mapped_column(default=0)
    meta_description_count: Mapped[int] = mapped_column(default=0)
    og_url: Mapped[str] = mapped_column(default="")
    canonical_header: Mapped[str] = mapped_column(default="")
    rel_prev: Mapped[str] = mapped_column(default="")
    rel_next: Mapped[str] = mapped_column(default="")

    page: Mapped[PageRow] = relationship(back_populates="html")


class PageRenderRow(Base):
    """The rendered-vs-raw comparison of one page; present only when rendering was tried."""

    __tablename__ = "page_render"

    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), primary_key=True)
    ok: Mapped[bool] = mapped_column(default=False)
    """False when the browser did not deliver a DOM; ``error`` says why."""
    render_ms: Mapped[int] = mapped_column(default=0)
    error: Mapped[str] = mapped_column(default="")
    raw_title: Mapped[str] = mapped_column(default="")
    rendered_title: Mapped[str] = mapped_column(default="")
    raw_meta_description: Mapped[str] = mapped_column(default="")
    rendered_meta_description: Mapped[str] = mapped_column(default="")
    raw_meta_robots: Mapped[str] = mapped_column(default="")
    rendered_meta_robots: Mapped[str] = mapped_column(default="")
    raw_canonical: Mapped[str] = mapped_column(default="")
    rendered_canonical: Mapped[str] = mapped_column(default="")
    raw_h1: Mapped[str] = mapped_column(default="")
    rendered_h1: Mapped[str] = mapped_column(default="")
    raw_word_count: Mapped[int] = mapped_column(default=0)
    rendered_word_count: Mapped[int] = mapped_column(default=0)
    raw_link_count: Mapped[int] = mapped_column(default=0)
    rendered_link_count: Mapped[int] = mapped_column(default=0)
    links_added_json: Mapped[str] = mapped_column(default="[]")
    links_removed_json: Mapped[str] = mapped_column(default="[]")

    page: Mapped[PageRow] = relationship(back_populates="render")


class HreflangRow(Base):
    """One hreflang alternate declared on ``page``."""

    __tablename__ = "hreflang"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    lang: Mapped[str]
    href: Mapped[str]

    page: Mapped[PageRow] = relationship(back_populates="hreflang")


class ExtractionRow(Base):
    """What one custom extractor or search found on ``page``; one row per name per parsed page."""

    __tablename__ = "extractions"
    __table_args__ = (Index("ix_extractions_name", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    name: Mapped[str]
    kind: Mapped[str]
    """``css``, ``xpath``, ``regex`` or ``search``."""
    count: Mapped[int] = mapped_column(default=0)
    """Matches on the page; 0 means the extractor or search found nothing."""
    values_json: Mapped[str] = mapped_column(default="[]")
    """The kept values (first, or all) as a JSON list of strings."""

    page: Mapped[PageRow] = relationship(back_populates="extractions")


class IssueRow(Base):
    """One audit finding; the table is rebuilt on every ``audit`` run."""

    __tablename__ = "issues"
    __table_args__ = (Index("ix_issues_rule", "rule_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    rule_id: Mapped[str]
    severity: Mapped[str]
    message: Mapped[str] = mapped_column(default="")

    page: Mapped[PageRow] = relationship()


class LinkRow(Base):
    """One anchor found on ``page``."""

    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    dst_url: Mapped[str]
    anchor_text: Mapped[str] = mapped_column(default="")
    rel: Mapped[str] = mapped_column(default="")
    nofollow: Mapped[bool] = mapped_column(default=False)
    is_internal: Mapped[bool] = mapped_column(default=False)
    position: Mapped[str] = mapped_column(default="")
    """``header``, ``nav``, ``body``, ``aside`` or ``footer``."""

    page: Mapped[PageRow] = relationship(back_populates="links")


class SitemapRow(Base):
    """One sitemap or sitemap index the crawl tried to read."""

    __tablename__ = "sitemaps"
    __table_args__ = (UniqueConstraint("crawl_id", "url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    crawl_id: Mapped[int] = mapped_column(ForeignKey("crawls.id"))
    url: Mapped[str]
    found_in: Mapped[str]
    """``robots.txt``, ``default`` or the index that listed it."""
    kind: Mapped[str] = mapped_column(default="")
    """``urlset``, ``index`` or empty when unusable."""
    status_code: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str] = mapped_column(default="")
    url_count: Mapped[int] = mapped_column(default=0)


class SitemapUrlRow(Base):
    """One URL from one sitemap file. A URL listed twice in one file is one row."""

    __tablename__ = "sitemap_urls"
    __table_args__ = (UniqueConstraint("crawl_id", "sitemap_url", "loc"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    crawl_id: Mapped[int] = mapped_column(ForeignKey("crawls.id"))
    sitemap_url: Mapped[str]
    loc: Mapped[str]
    lastmod: Mapped[str] = mapped_column(default="")
    changefreq: Mapped[str] = mapped_column(default="")
    priority: Mapped[str] = mapped_column(default="")
