"""CrawlSession over the real crawler and the fixture site."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from sitecrawler.models import CrawlConfig
from sitecrawler.session import CrawlSession, SessionState, SessionStatus
from sitecrawler.store import open_store
from tests.conftest import settled, site_pages, wait_until
from tests.integration.test_audit import TRIGGERS


@pytest.fixture
def session(tmp_path: Path) -> Iterator[CrawlSession]:
    s = CrawlSession(tmp_path / "crawls", audit_interval=0.2)
    yield s
    s.close()


def _wait(session: CrawlSession, predicate: Callable[[SessionState], bool]) -> SessionState:
    return wait_until(session, predicate, timeout=60.0)


def test_live_crawl_matches_the_cli_audit(
    session: CrawlSession, site: str, pages: frozenset[str]
) -> None:
    session.start(CrawlConfig(start_url=site, delay_seconds=0, workers=1))
    state = _wait(session, settled)

    assert state.status is SessionStatus.DONE
    assert state.done == len(pages)
    assert state.queued == 0
    result = session.audit().result
    assert result is not None
    counts = Counter(i.rule_id for i in result.issues)
    for rule_id, paths in TRIGGERS.items():
        assert counts[rule_id] == len(paths), rule_id
    assert state.db is not None
    assert state.db.name.startswith("127.0.0.1_")
    with open_store(state.db) as store:
        assert store.crawl().status == "done"
        assert store.issue_counts() == dict(counts)
        assert len(store.indexability()) == len(pages)


def test_stop_mid_crawl_leaves_a_resumable_file(
    session: CrawlSession, site: str, pages: frozenset[str]
) -> None:
    session.start(CrawlConfig(start_url=site, delay_seconds=0.2, workers=1))
    _wait(session, lambda s: s.done >= 3)

    session.stop()
    state = _wait(session, settled)

    assert state.status is SessionStatus.STOPPED
    assert 3 <= state.done < len(pages)
    assert state.db is not None
    with open_store(state.db) as store:
        assert store.crawl().status == "stopped"
        assert store.count_pages("pending") > 0


def test_open_audited_file_is_read_only_and_complete(audited_db: Path, tmp_path: Path) -> None:
    session = CrawlSession.open(audited_db, tmp_path / "crawls")

    state = session.state()
    assert state.status is SessionStatus.DONE
    assert state.read_only
    assert state.db == audited_db
    assert state.done == len(site_pages())
    assert state.audit_rev == 1
    assert state.started_at is not None
    assert state.finished_at is not None
    assert abs(time.time() - state.started_at) < 600, "store datetimes are UTC, not local"
    assert state.finished_at >= state.started_at
    result, view = session.audit().result, session.audit().view
    assert result is not None
    assert view is not None
    with open_store(audited_db) as store:
        assert Counter(i.rule_id for i in result.issues) == Counter(store.issue_counts())
        assert result.verdicts == store.indexability()
    assert session.sitemap_urls
    session.close()


def test_open_unaudited_file_audits_in_memory_only(crawled_db: Path, tmp_path: Path) -> None:
    session = CrawlSession.open(crawled_db, tmp_path / "crawls")

    result = session.audit().result
    assert result is not None
    assert len(result.verdicts) == len(site_pages())
    assert Counter(i.rule_id for i in result.issues)["title.missing"] == len(
        TRIGGERS["title.missing"]
    )
    with open_store(crawled_db) as store:
        assert store.issue_counts() == {}
        assert store.indexability() == {}
    session.close()


def test_open_empty_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    with open_store(path):
        pass
    with pytest.raises(ValueError, match="holds no crawl"):
        CrawlSession.open(path, tmp_path / "crawls")
