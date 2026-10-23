"""Open, write and read one crawl's SQLite file."""

from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, cast
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine, delete, event, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, selectinload

from sitecrawler import __version__
from sitecrawler.crawl.urls import normalize, same_site
from sitecrawler.models import (
    CrawlConfig,
    CrawlInfo,
    Extraction,
    Fingerprint,
    HreflangRef,
    Indexability,
    Issue,
    LinkMetrics,
    LinkRef,
    Outcome,
    PageRecord,
    QueueItem,
    RedirectHop,
    RenderDiff,
    ResumeState,
    Severity,
    SitemapEntry,
    SitemapFile,
    StructuredData,
    StructuredError,
    StructuredFormat,
    StructuredItem,
)
from sitecrawler.store.schema import (
    Base,
    CrawlRow,
    ExtractionRow,
    HreflangRow,
    IssueRow,
    LinkRow,
    PageHtmlRow,
    PageRenderRow,
    PageRow,
    RedirectHopRow,
    SitemapRow,
    SitemapUrlRow,
    StructuredRow,
)

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
    # ``Any``: SQLAlchemy types the connect event loosely; we only run PRAGMAs.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def missing_tables(path: Path) -> list[str]:
    """Tables this version writes that the crawl file at ``path`` lacks.

    Empty for a current file and for one that is not a crawl yet. Opening a
    file creates missing tables, so an older crawl would otherwise read as one
    that found nothing (no structured data, say) rather than one never looked
    at; callers refuse it instead. Missing columns fail on their own.
    """
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
        names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    if "pages" not in names:
        return []
    return sorted(set(Base.metadata.tables) - names)


def crawl_file_problem(path: Path) -> str | None:
    """Why ``path`` cannot be opened as a stored crawl, or None when it can.

    Does not open the file as a store, so a wrong path is never turned into
    an empty crawl file.
    """
    if not path.is_file():
        return f"{path} is not a file"
    header = path.read_bytes()[:16] if path.stat().st_size else b""
    if not header.startswith(b"SQLite format 3"):
        return f"{path} is not a SQLite database"
    if missing := missing_tables(path):
        return (
            f"{path} was written by an older sitecrawler (no {', '.join(missing)} table); "
            "re-crawl it"
        )
    return None


def open_store(path: Path | str) -> Store:
    """Open (creating if needed) the crawl database at ``path``.

    Use as a context manager so the connection pool is released; on Windows the
    file cannot be deleted or re-opened for resume until it is.
    """
    engine = create_engine(f"sqlite:///{Path(path).as_posix()}")
    event.listen(engine, "connect", _set_pragmas)
    Base.metadata.create_all(engine)
    return Store(engine, Path(path))


class Store:
    """One crawl's SQLite file. Implements :class:`~sitecrawler.crawl.sink.CrawlSink`.

    Writes happen per page in their own transaction, so a crash loses at most
    the page in flight and :meth:`begin` with ``resume=True`` picks up from the
    pending rows.
    """

    def __init__(self, engine: Engine, path: Path) -> None:
        """Wrap an engine; prefer :func:`open_store`."""
        self.engine = engine
        self.path = path
        self.crawl_id: int | None = None

    def __enter__(self) -> Store:
        """Enter the context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Release the connection pool."""
        self.close()

    def close(self) -> None:
        """Dispose of the engine, releasing the file."""
        self.engine.dispose()

    # ------------------------------------------------------------- CrawlSink
    def begin(self, config: CrawlConfig, *, resume: bool) -> ResumeState:
        """Create the crawl row, or load the pending work of the existing one.

        Raises:
            ValueError: the file already holds a crawl and ``resume`` is off,
                ``resume`` is on but there is nothing to resume, or the start
                URL differs from the stored crawl's.
        """
        start = normalize(config.start_url, keep_query=config.keep_query) or config.start_url
        mode = "list" if config.seed_urls else "crawl"
        with Session(self.engine) as session:
            existing = session.scalars(select(CrawlRow)).first()
            if existing is None:
                if resume:
                    msg = f"{self.path}: nothing to resume, the file holds no crawl"
                    raise ValueError(msg)
                row = CrawlRow(
                    start_url=start,
                    mode=mode,
                    config_json=json.dumps(asdict(config)),
                    version=__version__,
                    started_at=_now(),
                )
                session.add(row)
                session.commit()
                self.crawl_id = row.id
                return ResumeState()

            if not resume:
                msg = f"{self.path} already contains a crawl; use --resume or a new file"
                raise ValueError(msg)
            if existing.start_url != start:
                msg = (
                    f"cannot resume: {self.path} was crawled from {existing.start_url}, not {start}"
                )
                raise ValueError(msg)
            existing.status = "running"
            existing.finished_at = None
            session.commit()
            self.crawl_id = existing.id
            return ResumeState(
                seen=self.seen_urls(), pending=tuple(self.pending_items()), done=existing.pages_done
            )

    def seeded(
        self,
        items: Sequence[QueueItem],
        sitemap_files: Sequence[SitemapFile],
        sitemap_entries: Sequence[SitemapEntry],
    ) -> None:
        """Insert pending rows for the seeds; remember every sitemap file and entry."""
        crawl_id = self._crawl_id()
        with Session(self.engine) as session:
            self._queue_pending(session, crawl_id, items)
            if sitemap_files:
                session.execute(
                    insert(SitemapRow)
                    .values(
                        [
                            {
                                "crawl_id": crawl_id,
                                "url": f.url,
                                "found_in": f.found_in,
                                "kind": f.kind,
                                "status_code": f.status_code,
                                "error": f.error,
                                "url_count": f.url_count,
                            }
                            for f in sitemap_files
                        ]
                    )
                    .on_conflict_do_nothing()
                )
            if sitemap_entries:
                session.execute(
                    insert(SitemapUrlRow)
                    .values(
                        [
                            {
                                "crawl_id": crawl_id,
                                "sitemap_url": e.sitemap_url,
                                "loc": e.loc,
                                "lastmod": e.lastmod,
                                "changefreq": e.changefreq,
                                "priority": e.priority,
                            }
                            for e in sitemap_entries
                        ]
                    )
                    .on_conflict_do_nothing()
                )
            session.commit()

    def page_done(self, record: PageRecord, discovered: Sequence[QueueItem]) -> None:
        """Write one page with its hops, HTML fields and links; queue what it found."""
        crawl_id = self._crawl_id()
        with Session(self.engine) as session:
            page = session.scalars(
                select(PageRow).where(PageRow.crawl_id == crawl_id, PageRow.url == record.url)
            ).first()
            if page is None:
                page = PageRow(
                    crawl_id=crawl_id, url=record.url, depth=record.depth, found_on=record.found_on
                )
                session.add(page)
            page.state = "done"
            page.outcome = record.outcome.value
            page.status_code = record.status_code
            page.final_url = record.final_url
            page.content_type = record.content_type
            page.size_bytes = record.size_bytes
            page.fetch_ms = record.fetch_ms
            page.error = record.error
            page.x_robots_tag = record.headers.get("x-robots-tag")
            page.last_modified = record.headers.get("last-modified")
            page.headers_json = json.dumps(record.headers)
            page.fetched_at = _now()
            fp = record.fingerprint
            page.hops = [
                RedirectHopRow(
                    hop_no=h.hop_no, from_url=h.from_url, to_url=h.to_url, status_code=h.status_code
                )
                for h in record.redirect_hops
            ]
            page.html = (
                PageHtmlRow(
                    title=record.title,
                    meta_description=record.meta_description,
                    meta_robots=record.meta_robots,
                    canonical=record.canonical,
                    h1=record.h1,
                    h1s_json=json.dumps(list(record.h1s)),
                    h2s_json=json.dumps(list(record.h2s)),
                    lang=record.lang,
                    word_count=record.word_count,
                    internal_links=record.internal_links,
                    title_count=record.title_count,
                    meta_description_count=record.meta_description_count,
                    og_url=record.og_url,
                    canonical_header=record.canonical_header,
                    rel_prev=record.rel_prev,
                    rel_next=record.rel_next,
                    content_hash=fp.content_hash if fp else None,
                    simhash=fp.simhash_hex if fp else None,
                    content_words=fp.words if fp else None,
                )
                if record.outcome is Outcome.FETCHED
                else None
            )
            page.render = _render_row(record)
            page.hreflang = [HreflangRow(lang=h.lang, href=h.href) for h in record.hreflang]
            page.extractions = [
                ExtractionRow(
                    name=e.name, kind=e.kind, count=e.count, values_json=json.dumps(list(e.values))
                )
                for e in record.extractions
            ]
            page.structured = _structured_rows(record.structured)
            src_host = urlparse(record.url).netloc
            page.links = [
                LinkRow(
                    dst_url=link.href,
                    anchor_text=link.text,
                    rel=link.rel,
                    nofollow=link.nofollow,
                    is_internal=same_site(urlparse(link.href).netloc, src_host),
                    position=link.position,
                )
                for link in record.links
            ]
            self._queue_pending(session, crawl_id, discovered)
            crawl = session.get_one(CrawlRow, crawl_id)
            crawl.pages_done += 1
            session.commit()

    def finish(self, *, pages_done: int, complete: bool) -> None:
        """Mark the crawl ``done``, or ``stopped`` when it ended at ``max_pages``."""
        with Session(self.engine) as session:
            crawl = session.get_one(CrawlRow, self._crawl_id())
            crawl.status = "done" if complete else "stopped"
            crawl.finished_at = _now()
            crawl.pages_done = pages_done
            session.commit()

    # ------------------------------------------------------------- reading
    def crawl(self) -> CrawlInfo:
        """Summary of the stored crawl."""
        with Session(self.engine) as session:
            row = session.scalars(select(CrawlRow)).first()
            if row is None:
                msg = f"{self.path} holds no crawl"
                raise ValueError(msg)
            return CrawlInfo(
                start_url=row.start_url,
                mode=row.mode,
                version=row.version,
                status=row.status,
                pages_done=row.pages_done,
                started_at=row.started_at,
                finished_at=row.finished_at,
                config_json=row.config_json,
            )

    def pending_items(self) -> list[QueueItem]:
        """URLs queued but not fetched, in queue order."""
        with Session(self.engine) as session:
            rows = session.scalars(
                select(PageRow).where(PageRow.state == "pending").order_by(PageRow.id)
            )
            return [QueueItem(r.url, r.depth, r.found_on) for r in rows]

    def sitemap_urls(self) -> frozenset[str]:
        """Every URL listed in any sitemap, as written there."""
        with Session(self.engine) as session:
            return frozenset(session.scalars(select(SitemapUrlRow.loc)))

    def sitemap_entries(self) -> list[SitemapEntry]:
        """Every sitemap entry with its file, ordered by file then URL."""
        with Session(self.engine) as session:
            rows = session.scalars(
                select(SitemapUrlRow).order_by(SitemapUrlRow.sitemap_url, SitemapUrlRow.id)
            )
            return [
                SitemapEntry(r.sitemap_url, r.loc, r.lastmod, r.changefreq, r.priority)
                for r in rows
            ]

    def sitemap_files(self) -> list[SitemapFile]:
        """Every sitemap file the crawl tried, in the order it tried them."""
        with Session(self.engine) as session:
            rows = session.scalars(select(SitemapRow).order_by(SitemapRow.id))
            return [
                SitemapFile(r.url, r.found_in, r.kind, r.status_code, r.error, r.url_count)
                for r in rows
            ]

    def replace_issues(self, issues: Sequence[Issue]) -> int:
        """Drop every stored issue and write ``issues``. Returns how many were written."""
        with Session(self.engine) as session:
            session.execute(delete(IssueRow))
            ids = dict(session.execute(select(PageRow.url, PageRow.id)).all())
            rows = [
                IssueRow(
                    page_id=ids[i.url],
                    rule_id=i.rule_id,
                    severity=i.severity.value,
                    message=i.message,
                )
                for i in issues
                if i.url in ids
            ]
            session.add_all(rows)
            session.commit()
        dropped = len(issues) - len(rows)
        if dropped:
            log.warning("%d issue(s) refer to URLs that are not in this crawl; dropped", dropped)
        return len(rows)

    def set_indexability(self, verdicts: dict[str, Indexability]) -> None:
        """Store the audit's indexability verdict per URL."""
        with Session(self.engine) as session:
            for page in session.scalars(select(PageRow).where(PageRow.state == "done")):
                verdict = verdicts.get(page.url)
                if verdict is None:
                    continue
                page.indexable = verdict.indexable
                page.indexability_reason = verdict.reason
            session.commit()

    def set_link_metrics(self, metrics: Mapping[str, LinkMetrics]) -> None:
        """Store the audit's inlink count, click depth and Link Score per URL."""
        with Session(self.engine) as session:
            for page in session.scalars(select(PageRow).where(PageRow.state == "done")):
                found = metrics.get(page.url)
                if found is None:
                    continue
                page.inlinks = found.inlinks
                page.link_depth = found.link_depth
                page.link_score = found.link_score
            session.commit()

    def indexability(self) -> dict[str, Indexability]:
        """Stored indexability verdicts by URL; empty when no audit has been stored."""
        with Session(self.engine) as session:
            rows = session.execute(
                select(PageRow.url, PageRow.indexable, PageRow.indexability_reason).where(
                    PageRow.state == "done", PageRow.indexable.is_not(None)
                )
            ).all()
        return {url: Indexability(bool(flag), reason) for url, flag, reason in rows}

    def iter_issues(self, rule_id: str | None = None) -> list[Issue]:
        """Stored issues, optionally for one rule, ordered by severity then URL."""
        stmt = select(IssueRow, PageRow.url).join(PageRow, IssueRow.page_id == PageRow.id)
        if rule_id is not None:
            stmt = stmt.where(IssueRow.rule_id == rule_id)
        with Session(self.engine) as session:
            issues = [
                Issue(url, row.rule_id, Severity(row.severity), row.message)
                for row, url in session.execute(stmt)
            ]
        return sorted(issues, key=lambda i: (i.severity.rank, i.rule_id, i.url))

    def issue_counts(self) -> dict[str, int]:
        """Number of stored issues per rule id."""
        with Session(self.engine) as session:
            rows = session.execute(
                select(IssueRow.rule_id, func.count()).group_by(IssueRow.rule_id)
            ).all()
        return dict(rows)

    def extraction_names(self) -> list[tuple[str, str]]:
        """Every ``(name, kind)`` the crawl extracted or searched for, in first-seen order."""
        with Session(self.engine) as session:
            rows = session.execute(
                select(ExtractionRow.name, ExtractionRow.kind)
                .group_by(ExtractionRow.name, ExtractionRow.kind)
                .order_by(func.min(ExtractionRow.id))
            ).all()
        return [(name, kind) for name, kind in rows]

    def extraction_columns(self) -> list[str]:
        """The ``extract_<name>`` / ``search_<name>`` columns of this crawl, in first-seen order."""
        return [Extraction(name, kind).column for name, kind in self.extraction_names()]

    def seen_urls(self) -> frozenset[str]:
        """Every URL in the pages table, fetched or not."""
        with Session(self.engine) as session:
            return frozenset(session.scalars(select(PageRow.url)))

    def count_pages(self, state: str | None = None) -> int:
        """Number of page rows, optionally only those in ``state``."""
        stmt = select(func.count()).select_from(PageRow)
        if state is not None:
            stmt = stmt.where(PageRow.state == state)
        with Session(self.engine) as session:
            return session.scalar(stmt) or 0

    def iter_pages(self) -> Iterator[PageRecord]:
        """Fetched pages as :class:`~sitecrawler.models.PageRecord`, sorted by URL.

        Child rows (hops, links, hreflang) are read with plain selects and
        grouped in Python: a 10k-page crawl has hundreds of thousands of links,
        and one ORM object per link made loading slower than auditing.
        """
        stmt = (
            select(PageRow)
            .where(PageRow.state == "done")
            .order_by(PageRow.url)
            .options(selectinload(PageRow.html), selectinload(PageRow.render))
        )
        with Session(self.engine) as session:
            rows = session.scalars(stmt).all()
            hops: dict[int, list[RedirectHop]] = defaultdict(list)
            for page_id, hop_no, from_url, to_url, status in session.execute(
                select(
                    RedirectHopRow.page_id,
                    RedirectHopRow.hop_no,
                    RedirectHopRow.from_url,
                    RedirectHopRow.to_url,
                    RedirectHopRow.status_code,
                ).order_by(RedirectHopRow.page_id, RedirectHopRow.hop_no)
            ):
                hops[page_id].append(RedirectHop(hop_no, from_url, to_url, status))
            links: dict[int, list[LinkRef]] = defaultdict(list)
            for page_id, dst, text, rel, position in session.execute(
                select(
                    LinkRow.page_id,
                    LinkRow.dst_url,
                    LinkRow.anchor_text,
                    LinkRow.rel,
                    LinkRow.position,
                ).order_by(LinkRow.page_id, LinkRow.id)
            ):
                links[page_id].append(LinkRef(dst, text, rel, position))
            hreflang: dict[int, list[HreflangRef]] = defaultdict(list)
            for page_id, lang, href in session.execute(
                select(HreflangRow.page_id, HreflangRow.lang, HreflangRow.href).order_by(
                    HreflangRow.page_id, HreflangRow.id
                )
            ):
                hreflang[page_id].append(HreflangRef(lang, href))
            extractions: dict[int, list[Extraction]] = defaultdict(list)
            for page_id, name, kind, count, values_json in session.execute(
                select(
                    ExtractionRow.page_id,
                    ExtractionRow.name,
                    ExtractionRow.kind,
                    ExtractionRow.count,
                    ExtractionRow.values_json,
                ).order_by(ExtractionRow.page_id, ExtractionRow.id)
            ):
                extractions[page_id].append(
                    Extraction(name, kind, tuple(json.loads(values_json)), count)
                )
            structured: dict[int, list[StructuredRow]] = defaultdict(list)
            for page_id, fmt, types, data_json, error, line in session.execute(
                select(
                    StructuredRow.page_id,
                    StructuredRow.format,
                    StructuredRow.types,
                    StructuredRow.data_json,
                    StructuredRow.error,
                    StructuredRow.line,
                ).order_by(StructuredRow.page_id, StructuredRow.id)
            ):
                structured[page_id].append(
                    StructuredRow(
                        format=fmt, types=types, data_json=data_json, error=error, line=line
                    )
                )
            for row in rows:
                yield _to_record(
                    row,
                    hops[row.id],
                    links[row.id],
                    hreflang[row.id],
                    extractions[row.id],
                    structured[row.id],
                )

    # ------------------------------------------------------------- helpers
    def _crawl_id(self) -> int:
        if self.crawl_id is None:
            msg = "begin() must be called before writing"
            raise RuntimeError(msg)
        return self.crawl_id

    @staticmethod
    def _queue_pending(session: Session, crawl_id: int, items: Sequence[QueueItem]) -> None:
        if not items:
            return
        session.execute(
            insert(PageRow)
            .values(
                [
                    {
                        "crawl_id": crawl_id,
                        "url": item.url,
                        "state": "pending",
                        "depth": item.depth,
                        "found_on": item.found_on,
                    }
                    for item in items
                ]
            )
            .on_conflict_do_nothing()
        )


def _render_row(record: PageRecord) -> PageRenderRow | None:
    """The ``page_render`` row for ``record``, or None when rendering was not tried."""
    diff = record.render
    if diff is None:
        if not record.render_error:
            return None
        return PageRenderRow(ok=False, render_ms=record.render_ms, error=record.render_error)
    return PageRenderRow(
        ok=True,
        render_ms=record.render_ms,
        raw_title=diff.raw_title,
        rendered_title=diff.rendered_title,
        raw_meta_description=diff.raw_meta_description,
        rendered_meta_description=diff.rendered_meta_description,
        raw_meta_robots=diff.raw_meta_robots,
        rendered_meta_robots=diff.rendered_meta_robots,
        raw_canonical=diff.raw_canonical,
        rendered_canonical=diff.rendered_canonical,
        raw_h1=diff.raw_h1,
        rendered_h1=diff.rendered_h1,
        raw_word_count=diff.raw_word_count,
        rendered_word_count=diff.rendered_word_count,
        raw_link_count=diff.raw_link_count,
        rendered_link_count=diff.rendered_link_count,
        links_added_json=json.dumps(list(diff.links_added)),
        links_removed_json=json.dumps(list(diff.links_removed)),
    )


def render_diff_from_row(row: PageRenderRow | None) -> RenderDiff | None:
    """Rebuild the :class:`~sitecrawler.models.RenderDiff` stored in ``row``, if it rendered."""
    if row is None or not row.ok:
        return None
    return RenderDiff(
        raw_title=row.raw_title,
        rendered_title=row.rendered_title,
        raw_meta_description=row.raw_meta_description,
        rendered_meta_description=row.rendered_meta_description,
        raw_meta_robots=row.raw_meta_robots,
        rendered_meta_robots=row.rendered_meta_robots,
        raw_canonical=row.raw_canonical,
        rendered_canonical=row.rendered_canonical,
        raw_h1=row.raw_h1,
        rendered_h1=row.rendered_h1,
        raw_word_count=row.raw_word_count,
        rendered_word_count=row.rendered_word_count,
        raw_link_count=row.raw_link_count,
        rendered_link_count=row.rendered_link_count,
        links_added=tuple(json.loads(row.links_added_json)),
        links_removed=tuple(json.loads(row.links_removed_json)),
    )


def fingerprint_from_row(html: PageHtmlRow | None) -> Fingerprint | None:
    """The :class:`~sitecrawler.models.Fingerprint` stored on ``html``, if the page was parsed."""
    if html is None or html.content_hash is None:
        return None
    return Fingerprint(html.content_hash, int(html.simhash or "0", 16), html.content_words or 0)


def _structured_rows(data: StructuredData | None) -> list[StructuredRow]:
    if data is None:
        return []
    rows = [
        StructuredRow(
            format=item.format,
            types=" ".join(item.types),
            data_json=json.dumps(item.data),
            line=item.line,
        )
        for item in data.items
    ]
    rows += [StructuredRow(format="json-ld", error=e.message, line=e.line) for e in data.errors]
    return rows


def structured_from_rows(
    html: PageHtmlRow | None, rows: Sequence[StructuredRow]
) -> StructuredData | None:
    """The :class:`~sitecrawler.models.StructuredData` stored for a page, if it was parsed."""
    if fingerprint_from_row(html) is None:
        return None
    items = tuple(
        StructuredItem(cast("StructuredFormat", row.format), json.loads(row.data_json), row.line)
        for row in rows
        if row.data_json is not None
    )
    errors = tuple(StructuredError(row.error, row.line) for row in rows if row.error is not None)
    return StructuredData(items, errors)


def _to_record(
    row: PageRow,
    hops: Sequence[RedirectHop],
    links: Sequence[LinkRef],
    hreflang: Sequence[HreflangRef],
    extractions: Sequence[Extraction] = (),
    structured: Sequence[StructuredRow] = (),
) -> PageRecord:
    html = row.html
    headers: dict[str, str] = json.loads(row.headers_json)
    return PageRecord(
        url=row.url,
        outcome=Outcome(row.outcome or Outcome.ERROR.value),
        depth=row.depth,
        found_on=row.found_on,
        status_code=row.status_code,
        title=html.title if html else "",
        meta_description=html.meta_description if html else "",
        h1=html.h1 if html else "",
        canonical=html.canonical if html else "",
        content_type=row.content_type,
        internal_links=html.internal_links if html else 0,
        word_count=html.word_count if html else 0,
        fetch_ms=row.fetch_ms,
        error=row.error,
        final_url=row.final_url,
        size_bytes=row.size_bytes,
        headers=headers,
        redirect_hops=tuple(hops),
        links=tuple(links),
        h1s=tuple(json.loads(html.h1s_json)) if html else (),
        h2s=tuple(json.loads(html.h2s_json)) if html else (),
        meta_robots=html.meta_robots if html else "",
        lang=html.lang if html else "",
        title_count=html.title_count if html else 0,
        meta_description_count=html.meta_description_count if html else 0,
        og_url=html.og_url if html else "",
        canonical_header=html.canonical_header if html else "",
        hreflang=tuple(hreflang),
        rel_prev=html.rel_prev if html else "",
        rel_next=html.rel_next if html else "",
        fingerprint=fingerprint_from_row(html),
        render=render_diff_from_row(row.render),
        render_ms=row.render.render_ms if row.render else 0,
        render_error=row.render.error if row.render else "",
        extractions=tuple(extractions),
        structured=structured_from_rows(html, structured),
    )
