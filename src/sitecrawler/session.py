"""One crawl from Start to an audited file, steerable from another thread.

:class:`CrawlSession` is what the web UI drives. It runs a
:class:`~sitecrawler.crawl.Crawler` in a worker thread, keeps every finished
page in memory, re-runs the audit while pages arrive, and writes the final
issues and verdicts to the SQLite file when the crawl ends. It can also open
a finished file read-only, so a stored crawl and a live one look the same to
whoever is reading. ADR-0007 has the reasoning.

Thread model: the caller's thread (uvicorn's, a test's) starts, pauses, stops
and reads; the crawl thread writes the store and appends records; the audit
thread only reads records and publishes results. One lock guards the shared
state and readers copy what they need out from under it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from sitecrawler.audit import AuditResult, CrawlView, load_rules, run_audit
from sitecrawler.audit.rule import Rule
from sitecrawler.crawl import CrawlControl, Crawler
from sitecrawler.crawl.crawler import ProgressCallback
from sitecrawler.crawl.sink import CrawlSink
from sitecrawler.models import (
    CrawlConfig,
    ExtractorSpec,
    PageRecord,
    QueueItem,
    ResumeState,
    SearchSpec,
    SitemapEntry,
    SitemapFile,
)
from sitecrawler.store import Store, open_store

log = logging.getLogger(__name__)


class SessionStatus(StrEnum):
    """Where a session is in its life."""

    IDLE = "idle"
    """No crawl loaded; ready for :meth:`CrawlSession.start`."""
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    """Stop requested; in-flight fetches are being cancelled."""
    FINISHING = "finishing"
    """The crawl loop has ended; the final audit is running and being written."""
    DONE = "done"
    """Finished with an empty frontier."""
    STOPPED = "stopped"
    """Ended early: stopped on request or capped by ``max_pages``."""
    ERROR = "error"

    @property
    def active(self) -> bool:
        """True while a crawl thread is doing something."""
        return self in _ACTIVE


_ACTIVE = frozenset(
    {
        SessionStatus.RUNNING,
        SessionStatus.PAUSED,
        SessionStatus.STOPPING,
        SessionStatus.FINISHING,
    }
)
_SETTLED = frozenset(
    {SessionStatus.IDLE, SessionStatus.DONE, SessionStatus.STOPPED, SessionStatus.ERROR}
)


class SessionBusyError(RuntimeError):
    """The requested transition is not allowed in the session's current status."""


class CrawlRunner(Protocol):
    """What the session needs from a crawler; :class:`Crawler` satisfies it."""

    async def arun(self, on_progress: ProgressCallback | None = None) -> list[PageRecord]:
        """Run the crawl to completion, reporting to the sink as it goes."""
        ...


RunnerFactory = Callable[[CrawlConfig, CrawlSink, CrawlControl], CrawlRunner]
"""Builds the crawler for one run. Tests inject a fake; raises ``ValueError`` on a bad config."""


def _default_runner(config: CrawlConfig, sink: CrawlSink, control: CrawlControl) -> CrawlRunner:
    return Crawler(config, sink=sink, control=control)


@dataclass(slots=True, frozen=True)
class SessionState:
    """A consistent snapshot of a session, safe to hand to another thread."""

    status: SessionStatus
    start_url: str = ""
    db: Path | None = None
    read_only: bool = False
    """True for a stored crawl opened with :meth:`CrawlSession.open`."""
    done: int = 0
    """Pages fetched so far. Records are numbered in arrival order, so this is
    also the next position for :meth:`CrawlSession.records_since`."""
    queued: int = 0
    audit_rev: int = 0
    """Incremented every time the audit has run; 0 until it has."""
    started_at: float | None = None
    """Unix time."""
    finished_at: float | None = None
    error: str = ""

    @property
    def elapsed(self) -> float:
        """Seconds the crawl has run (or ran)."""
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0.0, end - self.started_at)


@dataclass(slots=True, frozen=True)
class AuditSnapshot:
    """The latest audit a session has run. ``result`` and ``view`` are None until the first."""

    rev: int
    result: AuditResult | None = None
    view: CrawlView | None = None


class _SessionSink:
    """Writes to the store, then tells the session. Called on the crawl thread only."""

    def __init__(self, store: Store, session: CrawlSession) -> None:
        self._store = store
        self._session = session

    def begin(self, config: CrawlConfig, *, resume: bool) -> ResumeState:
        return self._store.begin(config, resume=resume)

    def seeded(
        self,
        items: Sequence[QueueItem],
        sitemap_files: Sequence[SitemapFile],
        sitemap_entries: Sequence[SitemapEntry],
    ) -> None:
        self._store.seeded(items, sitemap_files, sitemap_entries)
        self._session._seeded(items, sitemap_files, sitemap_entries)

    def page_done(self, record: PageRecord, discovered: Sequence[QueueItem]) -> None:
        self._store.page_done(record, discovered)
        self._session._page_done(record)

    def finish(self, *, pages_done: int, complete: bool) -> None:
        self._store.finish(pages_done=pages_done, complete=complete)
        self._session._finished(complete)


def _config_from_json(start_url: str, config_json: str) -> CrawlConfig:
    """Rebuild the config a stored crawl was run with, tolerating unknown keys."""
    data: dict[str, Any] = json.loads(config_json or "{}")  # Any: asdict(CrawlConfig) round-trip
    names = {f.name for f in fields(CrawlConfig)}
    kwargs = {k: v for k, v in data.items() if k in names}
    # JSON turned every tuple field into a list; CrawlConfig is hashable only with tuples.
    tuple_fields = {f.name for f in fields(CrawlConfig) if str(f.type).startswith("tuple")}
    for name in tuple_fields & kwargs.keys():
        kwargs[name] = tuple(kwargs[name])
    # Nested specs come back as dicts; rebuild the dataclasses (unknown keys dropped).
    if "extract" in kwargs:
        kwargs["extract"] = tuple(_spec(ExtractorSpec, item) for item in kwargs["extract"])
    if "search" in kwargs:
        kwargs["search"] = tuple(_spec(SearchSpec, item) for item in kwargs["search"])
    kwargs.setdefault("start_url", start_url)
    return CrawlConfig(**kwargs)


def _spec[T: (ExtractorSpec, SearchSpec)](cls: type[T], data: dict[str, Any]) -> T:
    # Any: one entry of the asdict() list stored in config_json.
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


class CrawlSession:
    """Run, steer and read one crawl; see the module docstring for the thread model."""

    def __init__(
        self,
        crawls_dir: Path,
        *,
        audit_interval: float = 2.0,
        runner_factory: RunnerFactory = _default_runner,
    ) -> None:
        """Create an idle session.

        Args:
            crawls_dir: Where new crawl files go, as ``<host>-<timestamp>.db``.
                Created on first use.
            audit_interval: Minimum seconds between audit re-runs while pages
                arrive. The gap grows to three times the last run's duration
                on big crawls, so auditing never dominates.
            runner_factory: Builds the crawler; tests pass a fake.
        """
        self.crawls_dir = Path(crawls_dir)
        self._audit_interval = audit_interval
        self._runner_factory = runner_factory
        self._rules: Sequence[Rule] = load_rules()
        self._lock = threading.Lock()
        """Guards every field set in :meth:`_reset_state`; held briefly, never while joining."""
        self._cond = threading.Condition()
        """Wakes the audit thread; guards ``_dirty``, ``_audit_stop`` and ``_next_audit_at``."""
        self._transition = threading.RLock()
        """Serialises start, clear and close, which join threads and rebuild the state."""
        self._crawl_thread: threading.Thread | None = None
        self._audit_thread: threading.Thread | None = None
        self._reset_state()

    def _reset_state(self) -> None:
        """Forget everything. Only called when no worker thread is alive."""
        self._status = SessionStatus.IDLE
        self._config = CrawlConfig()
        self._db: Path | None = None
        self._read_only = False
        self._records: list[PageRecord] = []
        self._sitemap_files: list[SitemapFile] = []
        self._sitemap_entries: list[SitemapEntry] = []
        self._queued = 0
        self._audit_rev = 0
        self._audit_result: AuditResult | None = None
        self._audit_view: CrawlView | None = None
        self._started_at: float | None = None
        self._finished_at: float | None = None
        self._error = ""
        self._complete: bool | None = None
        self._control = CrawlControl()
        self._dirty = False
        self._audit_stop = False
        self._next_audit_at = 0.0

    # ----------------------------------------------------------- construction
    @classmethod
    def open(cls, db: Path, crawls_dir: Path, *, audit_interval: float = 2.0) -> CrawlSession:
        """Load a stored crawl read-only, so it reads like a finished live one.

        A file that was never audited is audited in memory; nothing is
        written back.

        Raises:
            ValueError: the file holds no crawl.
        """
        session = cls(crawls_dir, audit_interval=audit_interval)
        with open_store(db) as store:
            info = store.crawl()
            config = _config_from_json(info.start_url, info.config_json)
            records = list(store.iter_pages())
            sitemap_files = store.sitemap_files()
            sitemap_entries = store.sitemap_entries()
            issues = store.iter_issues()
            verdicts = store.indexability()
        view = CrawlView.from_records(
            records,
            sitemap_entries=sitemap_entries,
            sitemap_files=sitemap_files,
            keep_query=config.keep_query,
        )
        result = (
            AuditResult(issues, verdicts, session._rules)
            if verdicts
            else run_audit(view, session._rules)
        )
        session._config = config
        session._db = Path(db)
        session._read_only = True
        session._records = records
        session._sitemap_files = sitemap_files
        session._sitemap_entries = sitemap_entries
        session._audit_rev = 1
        session._audit_result = result
        session._audit_view = view
        session._complete = info.status == "done"
        session._status = SessionStatus.DONE if session._complete else SessionStatus.STOPPED
        session._started_at = _timestamp(info.started_at)
        session._finished_at = _timestamp(info.finished_at)
        return session

    # ------------------------------------------------------------- control
    def start(self, config: CrawlConfig) -> SessionState:
        """Start crawling ``config`` into a new file under ``crawls_dir``.

        From a settled status (idle, done, stopped, error) this first clears
        the session; a stored crawl that was open is left untouched on disk.

        Raises:
            SessionBusyError: a crawl is running.
            ValueError: the config is invalid (bad start URL). No file is left behind.
        """
        with self._transition:
            with self._lock:
                self._require("start", *_SETTLED)
            self._join_threads()
            self._reset_state()
            path = self._new_db_path(config)
            store = open_store(path)
            control = CrawlControl()
            try:
                runner = self._runner_factory(config, _SessionSink(store, self), control)
            except ValueError:
                store.close()
                for side in ("", "-wal", "-shm"):
                    path.with_name(path.name + side).unlink(missing_ok=True)
                raise
            with self._lock:
                self._config = config
                self._db = path
                self._control = control
                self._status = SessionStatus.RUNNING
                self._started_at = time.time()
            with self._cond:
                self._next_audit_at = time.monotonic() + self._audit_interval
            self._audit_thread = threading.Thread(
                target=self._audit_loop, name="sitecrawler-audit", daemon=True
            )
            self._crawl_thread = threading.Thread(
                target=self._run_crawl,
                args=(runner, store),
                name="sitecrawler-crawl",
                daemon=True,
            )
            self._audit_thread.start()
            self._crawl_thread.start()
            return self.state()

    def pause(self) -> SessionState:
        """Hold the crawl once in-flight fetches finish. ``SessionBusyError`` unless running."""
        with self._lock:
            self._require("pause", SessionStatus.RUNNING)
            self._control.pause()
            self._status = SessionStatus.PAUSED
        return self.state()

    def resume(self) -> SessionState:
        """Continue a paused crawl. Raises ``SessionBusyError`` unless paused."""
        with self._lock:
            self._require("resume", SessionStatus.PAUSED)
            self._control.resume()
            self._status = SessionStatus.RUNNING
        return self.state()

    def stop(self) -> SessionState:
        """End the crawl early; the file is marked ``stopped`` and can be resumed by the CLI.

        Raises:
            SessionBusyError: nothing is running.
        """
        with self._lock:
            self._require("stop", SessionStatus.RUNNING, SessionStatus.PAUSED)
            self._control.stop()
            self._status = SessionStatus.STOPPING
        return self.state()

    def clear(self) -> SessionState:
        """Forget the loaded crawl and go back to idle. Raises ``SessionBusyError`` while active."""
        with self._transition:
            with self._lock:
                self._require("clear", *_SETTLED)
            self._join_threads()
            self._reset_state()
            return self.state()

    def close(self) -> None:
        """Stop whatever is running and wait for the threads to finish."""
        with self._transition:
            with self._lock:
                self._control.stop()
                if self._status in (SessionStatus.RUNNING, SessionStatus.PAUSED):
                    self._status = SessionStatus.STOPPING
            self._join_threads()

    # ------------------------------------------------------------- reading
    def state(self) -> SessionState:
        """A snapshot of where the session is."""
        with self._lock:
            return SessionState(
                status=self._status,
                start_url=self._config.start_url,
                db=self._db,
                read_only=self._read_only,
                done=len(self._records),
                queued=self._queued,
                audit_rev=self._audit_rev,
                started_at=self._started_at,
                finished_at=self._finished_at,
                error=self._error,
            )

    def records_since(self, seq: int) -> list[PageRecord]:
        """Pages fetched from position ``seq`` on, in arrival order."""
        with self._lock:
            return self._records[seq:]

    def audit(self) -> AuditSnapshot:
        """The latest audit."""
        with self._lock:
            return AuditSnapshot(self._audit_rev, self._audit_result, self._audit_view)

    @property
    def config(self) -> CrawlConfig:
        """The config of the loaded or running crawl."""
        with self._lock:
            return self._config

    @property
    def sitemap_urls(self) -> frozenset[str]:
        """Every URL seen in a sitemap so far, as written there."""
        with self._lock:
            return frozenset(e.loc for e in self._sitemap_entries)

    @property
    def sitemap_entries(self) -> tuple[SitemapEntry, ...]:
        """Every sitemap entry seen so far, with its file."""
        with self._lock:
            return tuple(self._sitemap_entries)

    @property
    def rules(self) -> Sequence[Rule]:
        """The rules the audit runs."""
        return self._rules

    # ------------------------------------------------------------ callbacks
    def _seeded(
        self,
        items: Sequence[QueueItem],
        sitemap_files: Sequence[SitemapFile],
        sitemap_entries: Sequence[SitemapEntry],
    ) -> None:
        with self._lock:
            self._sitemap_files.extend(sitemap_files)
            self._sitemap_entries.extend(sitemap_entries)
            self._queued = len(items)

    def _page_done(self, record: PageRecord) -> None:
        with self._lock:
            self._records.append(record)
        with self._cond:
            self._dirty = True
            self._cond.notify_all()

    def _progress(self, _record: PageRecord, _done: int, queued: int) -> None:
        with self._lock:
            self._queued = queued

    def _finished(self, complete: bool) -> None:
        with self._lock:
            self._complete = complete
            self._queued = 0 if complete else self._queued

    # ------------------------------------------------------------- threads
    def _run_crawl(self, runner: CrawlRunner, store: Store) -> None:
        error = ""
        try:
            asyncio.run(runner.arun(self._progress))
        except Exception as exc:  # deliberately total: the thread must always finish the file
            log.exception("crawl failed")
            error = f"{type(exc).__name__}: {exc}"
        self._finish(store, error)

    def _finish(self, store: Store, error: str) -> None:
        with self._lock:
            self._status = SessionStatus.FINISHING
        self._stop_auditor()
        try:
            with self._cond:
                stale = self._dirty
            if stale or self.audit().result is None:
                self._run_audit()
            result = self.audit().result
            if result is not None:
                store.replace_issues(result.issues)
                store.set_indexability(result.verdicts)
        except Exception as exc:  # deliberately total, same reason as above
            log.exception("final audit failed")
            error = error or f"audit failed: {type(exc).__name__}: {exc}"
        finally:
            store.close()
        with self._lock:
            self._finished_at = time.time()
            self._error = error
            if error:
                self._status = SessionStatus.ERROR
            elif self._complete:
                self._status = SessionStatus.DONE
            else:
                self._status = SessionStatus.STOPPED

    def _audit_loop(self) -> None:
        while True:
            with self._cond:
                while not self._audit_stop and (
                    not self._dirty or time.monotonic() < self._next_audit_at
                ):
                    timeout = (
                        max(0.0, self._next_audit_at - time.monotonic()) if self._dirty else None
                    )
                    self._cond.wait(timeout)
                if self._audit_stop:
                    return
                self._dirty = False
            duration = self._run_audit()
            with self._cond:
                self._next_audit_at = time.monotonic() + max(self._audit_interval, 3 * duration)

    def _run_audit(self) -> float:
        """Audit a copy of the records so far; returns how long it took."""
        started = time.monotonic()
        with self._lock:
            records = list(self._records)
            sitemap_files = tuple(self._sitemap_files)
            sitemap_entries = tuple(self._sitemap_entries)
            keep_query = self._config.keep_query
        view = CrawlView.from_records(
            records,
            sitemap_entries=sitemap_entries,
            sitemap_files=sitemap_files,
            keep_query=keep_query,
        )
        result = run_audit(view, self._rules)
        with self._lock:
            self._audit_rev += 1
            self._audit_result = result
            self._audit_view = view
        return time.monotonic() - started

    def _stop_auditor(self) -> None:
        with self._cond:
            self._audit_stop = True
            self._cond.notify_all()
        thread = self._audit_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join()

    def _join_threads(self) -> None:
        if self._crawl_thread is not None:
            self._crawl_thread.join()
            self._crawl_thread = None
        self._stop_auditor()
        self._audit_thread = None

    # ------------------------------------------------------------- helpers
    def _require(self, action: str, *allowed: SessionStatus) -> None:
        if self._status not in allowed:
            msg = f"cannot {action} while the session is {self._status.value}"
            raise SessionBusyError(msg)

    def _new_db_path(self, config: CrawlConfig) -> Path:
        first = config.start_url or (config.seed_urls[0] if config.seed_urls else "")
        host = re.sub(r"[^A-Za-z0-9.-]", "_", urlparse(first).netloc) or "crawl"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.crawls_dir.mkdir(parents=True, exist_ok=True)
        path = self.crawls_dir / f"{host}-{stamp}.db"
        n = 1
        while path.exists():
            path = self.crawls_dir / f"{host}-{stamp}-{n}.db"
            n += 1
        return path


def _timestamp(value: datetime | None) -> float | None:
    """Unix time of a store datetime, which is UTC with the tzinfo stripped."""
    return value.replace(tzinfo=UTC).timestamp() if value is not None else None
