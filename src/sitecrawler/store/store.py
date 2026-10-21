"""Open, write and read one crawl's SQLite file."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine, event, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session, selectinload

from sitecrawler import __version__
from sitecrawler.crawl.urls import normalize, same_site
from sitecrawler.models import (
    CrawlConfig,
    LinkRef,
    Outcome,
    PageRecord,
    QueueItem,
    RedirectHop,
    ResumeState,
)
from sitecrawler.store.schema import (
    Base,
    CrawlRow,
    LinkRow,
    PageHtmlRow,
    PageRow,
    RedirectHopRow,
    SitemapUrlRow,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
    # ``Any``: SQLAlchemy types the connect event loosely; we only run PRAGMAs.
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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
    def begin(self, config: CrawlConfig, *, resume: bool, mode: str = "crawl") -> ResumeState:
        """Create the crawl row, or load the pending work of the existing one.

        Raises:
            ValueError: the file already holds a crawl and ``resume`` is off,
                ``resume`` is on but there is nothing to resume, or the start
                URL differs from the stored crawl's.
        """
        start = normalize(config.start_url, keep_query=config.keep_query) or config.start_url
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

    def seeded(self, items: Sequence[QueueItem], sitemap_urls: Sequence[tuple[str, str]]) -> None:
        """Insert pending rows for the seeds and remember every sitemap URL."""
        crawl_id = self._crawl_id()
        with Session(self.engine) as session:
            self._queue_pending(session, crawl_id, items)
            if sitemap_urls:
                session.execute(
                    insert(SitemapUrlRow)
                    .values(
                        [
                            {"crawl_id": crawl_id, "sitemap_url": sm, "loc": loc}
                            for sm, loc in sitemap_urls
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
                )
                if record.outcome is Outcome.FETCHED
                else None
            )
            src_host = urlparse(record.url).netloc
            page.links = [
                LinkRow(
                    dst_url=link.href,
                    anchor_text=link.text,
                    rel=link.rel,
                    nofollow=link.nofollow,
                    is_internal=same_site(urlparse(link.href).netloc, src_host),
                )
                for link in record.links
            ]
            self._queue_pending(session, crawl_id, discovered)
            crawl = session.get_one(CrawlRow, crawl_id)
            crawl.pages_done += 1
            session.commit()

    def finish(self, *, pages_done: int) -> None:
        """Mark the crawl done."""
        with Session(self.engine) as session:
            crawl = session.get_one(CrawlRow, self._crawl_id())
            crawl.status = "done"
            crawl.finished_at = _now()
            crawl.pages_done = pages_done
            session.commit()

    # ------------------------------------------------------------- reading
    def crawl(self) -> CrawlRow:
        """The crawl row (detached; its columns are loaded)."""
        with Session(self.engine, expire_on_commit=False) as session:
            row = session.scalars(select(CrawlRow)).first()
            if row is None:
                msg = f"{self.path} holds no crawl"
                raise ValueError(msg)
            session.expunge(row)
            return row

    def pending_items(self) -> list[QueueItem]:
        """URLs queued but not fetched, in queue order."""
        with Session(self.engine) as session:
            rows = session.scalars(
                select(PageRow).where(PageRow.state == "pending").order_by(PageRow.id)
            )
            return [QueueItem(r.url, r.depth, r.found_on) for r in rows]

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
        """Fetched pages as :class:`~sitecrawler.models.PageRecord`, sorted by URL."""
        stmt = (
            select(PageRow)
            .where(PageRow.state == "done")
            .order_by(PageRow.url)
            .options(
                selectinload(PageRow.html), selectinload(PageRow.hops), selectinload(PageRow.links)
            )
        )
        with Session(self.engine) as session:
            for row in session.scalars(stmt):
                yield _to_record(row)

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


def _to_record(row: PageRow) -> PageRecord:
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
        redirect_hops=tuple(
            RedirectHop(h.hop_no, h.from_url, h.to_url, h.status_code) for h in row.hops
        ),
        links=tuple(LinkRef(link.dst_url, link.anchor_text, link.rel) for link in row.links),
        h1s=tuple(json.loads(html.h1s_json)) if html else (),
        h2s=tuple(json.loads(html.h2s_json)) if html else (),
        meta_robots=html.meta_robots if html else "",
        lang=html.lang if html else "",
    )
