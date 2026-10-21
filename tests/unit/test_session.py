"""CrawlSession state machine and persistence, driven by a fake crawler."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from sitecrawler.crawl import CrawlControl
from sitecrawler.crawl.crawler import ProgressCallback
from sitecrawler.crawl.sink import CrawlSink
from sitecrawler.models import CrawlConfig, Outcome, PageRecord, QueueItem
from sitecrawler.session import CrawlSession, SessionBusyError, SessionState, SessionStatus
from sitecrawler.store import open_store

SITE = "https://example.test"
CONFIG = CrawlConfig(start_url=f"{SITE}/")


class FakeRunner:
    """Feeds ``pages`` records through the sink, honouring the control like a real crawl."""

    def __init__(
        self,
        config: CrawlConfig,
        sink: CrawlSink,
        control: CrawlControl,
        *,
        pages: int,
        delay: float,
        fail_at: int | None,
    ) -> None:
        self.config = config
        self.sink = sink
        self.control = control
        self.pages = pages
        self.delay = delay
        self.fail_at = fail_at

    async def arun(self, on_progress: ProgressCallback | None = None) -> list[PageRecord]:
        self.sink.begin(self.config, resume=False)
        seeds = [QueueItem(f"{SITE}/p{i}", 0, "start") for i in range(self.pages)]
        self.sink.seeded(seeds, [(f"{SITE}/sitemap.xml", f"{SITE}/p0")])
        done = 0
        for item in seeds:
            while self.control.paused and not self.control.stopping:
                await asyncio.sleep(0.005)
            if self.control.stopping:
                break
            await asyncio.sleep(self.delay)
            if self.fail_at is not None and done == self.fail_at:
                msg = "boom"
                raise RuntimeError(msg)
            record = PageRecord(
                url=item.url,
                outcome=Outcome.FETCHED,
                depth=0,
                found_on="start",
                status_code=200,
                content_type="text/html",
                final_url=item.url,
            )
            self.sink.page_done(record, [])
            done += 1
            if on_progress is not None:
                on_progress(record, done, len(seeds) - done)
        self.sink.finish(pages_done=done, complete=done == len(seeds))
        return []


def _factory(
    pages: int = 5, delay: float = 0.0, fail_at: int | None = None
) -> Callable[[CrawlConfig, CrawlSink, CrawlControl], FakeRunner]:
    def build(config: CrawlConfig, sink: CrawlSink, control: CrawlControl) -> FakeRunner:
        return FakeRunner(config, sink, control, pages=pages, delay=delay, fail_at=fail_at)

    return build


def _session(tmp_path: Path, **kwargs: object) -> CrawlSession:
    return CrawlSession(
        tmp_path / "crawls",
        audit_interval=0.05,
        runner_factory=_factory(**kwargs),  # type: ignore[arg-type]
    )


def wait_until(
    session: CrawlSession, predicate: Callable[[SessionState], bool], timeout: float = 10.0
) -> SessionState:
    deadline = time.monotonic() + timeout
    while True:
        state = session.state()
        if predicate(state):
            return state
        if time.monotonic() > deadline:
            pytest.fail(f"timed out waiting; last state {state}")
        time.sleep(0.005)


def settled(state: SessionState) -> bool:
    return not state.status.active


@pytest.fixture
def session(tmp_path: Path) -> Iterator[CrawlSession]:
    s = _session(tmp_path)
    yield s
    s.close()


def test_idle_state(session: CrawlSession) -> None:
    state = session.state()
    assert state.status is SessionStatus.IDLE
    assert state.db is None
    assert state.done == state.seq == 0
    assert state.elapsed == 0.0
    assert session.records_since(0) == []
    assert session.audit() == (0, None, None)


def test_full_run_reaches_done_and_persists(session: CrawlSession, tmp_path: Path) -> None:
    started = session.start(CONFIG)
    assert started.status is SessionStatus.RUNNING
    assert started.db is not None
    assert started.db.parent == tmp_path / "crawls"
    assert re.fullmatch(r"example\.test-\d{8}-\d{6}\.db", started.db.name)

    state = wait_until(session, settled)

    assert state.status is SessionStatus.DONE
    assert state.done == state.seq == 5
    assert state.queued == 0
    assert state.audit_rev >= 1
    assert state.error == ""
    assert state.finished_at is not None
    assert len(session.records_since(3)) == 2
    assert session.sitemap_urls == {f"{SITE}/p0"}
    rev, result, view = session.audit()
    assert rev == state.audit_rev
    assert result is not None
    assert view is not None
    assert len(result.verdicts) == 5
    with open_store(started.db) as store:
        assert store.crawl().status == "done"
        assert len(store.indexability()) == 5
        assert store.issue_counts()["title.missing"] == 5


def test_audit_reruns_while_pages_arrive(tmp_path: Path) -> None:
    session = _session(tmp_path, pages=30, delay=0.02)
    try:
        session.start(CONFIG)
        state = wait_until(session, settled)
    finally:
        session.close()
    assert state.status is SessionStatus.DONE
    assert state.audit_rev >= 2


def test_pause_and_resume(tmp_path: Path) -> None:
    session = _session(tmp_path, pages=30, delay=0.02)
    try:
        session.start(CONFIG)
        wait_until(session, lambda s: s.done >= 2)

        paused = session.pause()
        assert paused.status is SessionStatus.PAUSED
        time.sleep(0.2)
        held = session.state().done
        assert held - paused.done <= 1, "at most the page in flight completes"
        time.sleep(0.1)
        assert session.state().done == held

        assert session.resume().status is SessionStatus.RUNNING
        state = wait_until(session, settled)
    finally:
        session.close()
    assert state.status is SessionStatus.DONE
    assert state.done == 30


def test_stop_marks_the_file_stopped(tmp_path: Path) -> None:
    session = _session(tmp_path, pages=30, delay=0.02)
    try:
        session.start(CONFIG)
        wait_until(session, lambda s: s.done >= 2)

        stopping = session.stop()
        assert stopping.status in (SessionStatus.STOPPING, SessionStatus.FINISHING)
        state = wait_until(session, settled)
    finally:
        session.close()
    assert state.status is SessionStatus.STOPPED
    assert 2 <= state.done < 30
    assert state.db is not None
    with open_store(state.db) as store:
        assert store.crawl().status == "stopped"
        assert len(store.indexability()) == state.done


def test_illegal_transitions_raise(tmp_path: Path) -> None:
    session = _session(tmp_path, pages=50, delay=0.02)
    try:
        for action in (session.pause, session.resume, session.stop):
            with pytest.raises(SessionBusyError, match="idle"):
                action()
        assert session.clear().status is SessionStatus.IDLE

        session.start(CONFIG)
        for action in (session.resume, session.clear):
            with pytest.raises(SessionBusyError, match="running"):
                action()
        with pytest.raises(SessionBusyError, match="running"):
            session.start(CONFIG)

        session.pause()
        with pytest.raises(SessionBusyError, match="paused"):
            session.pause()
        session.stop()
        wait_until(session, settled)
    finally:
        session.close()


def test_invalid_start_url_leaves_no_file(tmp_path: Path) -> None:
    session = CrawlSession(tmp_path / "crawls", audit_interval=0.05)
    with pytest.raises(ValueError, match="Invalid start URL"):
        session.start(CrawlConfig(start_url="not a url"))
    assert session.state().status is SessionStatus.IDLE
    assert not list((tmp_path / "crawls").iterdir())


def test_runner_failure_is_reported_and_releases_the_file(tmp_path: Path) -> None:
    session = _session(tmp_path, pages=5, fail_at=2)
    try:
        session.start(CONFIG)
        state = wait_until(session, settled)
    finally:
        session.close()
    assert state.status is SessionStatus.ERROR
    assert state.error == "RuntimeError: boom"
    assert state.done == 2
    assert state.db is not None
    with open_store(state.db) as store:
        assert store.crawl().status == "running"
        assert len(store.indexability()) == 2


def test_clear_returns_to_idle(session: CrawlSession) -> None:
    session.start(CONFIG)
    wait_until(session, settled)

    state = session.clear()

    assert state.status is SessionStatus.IDLE
    assert state.db is None
    assert state.done == 0
    assert session.records_since(0) == []
    assert session.audit() == (0, None, None)


def test_restart_opens_a_new_file(session: CrawlSession) -> None:
    first = session.start(CONFIG)
    wait_until(session, settled)

    second = session.start(CONFIG)
    wait_until(session, settled)

    assert first.db is not None
    assert second.db is not None
    assert first.db != second.db
    assert first.db.exists()
    assert second.db.exists()


def test_close_while_running_stops_the_crawl(tmp_path: Path) -> None:
    session = _session(tmp_path, pages=100, delay=0.02)
    session.start(CONFIG)
    wait_until(session, lambda s: s.done >= 1)

    session.close()

    state = session.state()
    assert state.status is SessionStatus.STOPPED
    assert state.db is not None
    with open_store(state.db) as store:
        assert store.crawl().status == "stopped"


def test_db_name_sanitises_the_host(session: CrawlSession) -> None:
    state = session.start(CrawlConfig(start_url="http://127.0.0.1:5000/"))
    wait_until(session, settled)
    assert state.db is not None
    assert state.db.name.startswith("127.0.0.1_5000-")
