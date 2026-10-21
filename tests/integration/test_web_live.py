"""Crawling the fixture site from the web app: start, pause, stop, clear, and the numbers."""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sitecrawler.store import open_store
from sitecrawler.web import create_app
from sitecrawler.web.tabs import rule_filters
from tests.conftest import site_pages
from tests.integration.test_audit import TRIGGERS

Crawl = dict[str, Any]  # Any: the /api/crawl JSON payload
ACTIVE = {"running", "paused", "stopping", "finishing"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(crawls_dir=tmp_path / "crawls")) as c:
        yield c


def start(client: TestClient, site: str, **options: object) -> Crawl:
    body: dict[str, object] = {"url": site, "delay_seconds": 0, "workers": 1, **options}
    response = client.post("/api/crawl/start", json=body)
    assert response.status_code == 200, response.text
    crawl: Crawl = response.json()
    return crawl


def wait(client: TestClient, predicate: Callable[[Crawl], bool], timeout: float = 60.0) -> Crawl:
    deadline = time.monotonic() + timeout
    while True:
        crawl: Crawl = client.get("/api/crawl").json()
        if predicate(crawl):
            return crawl
        if time.monotonic() > deadline:
            pytest.fail(f"timed out; last state {crawl}")
        time.sleep(0.05)


def settled(crawl: Crawl) -> bool:
    return crawl["status"] not in ACTIVE


def test_idle_app(client: TestClient) -> None:
    crawl = client.get("/api/crawl").json()
    assert crawl["status"] == "idle"
    assert crawl["db"] is None
    assert crawl["done"] == crawl["seq"] == 0
    assert client.get("/api/rows").json()["rows"] == []
    assert client.get("/api/summary").json()["pages"] == 0
    assert client.get("/").status_code == 200
    assert 'data-status="idle"' in client.get("/").text


def test_full_crawl_from_the_ui(client: TestClient, site: str, tmp_path: Path) -> None:
    started = start(client, site)
    assert started["status"] == "running"
    assert started["read_only"] is False

    crawl = wait(client, settled)

    assert crawl["status"] == "done"
    assert crawl["done"] == crawl["seq"] == len(site_pages())
    assert crawl["audit_rev"] >= 1
    assert crawl["error"] == ""
    rows = client.get("/api/rows").json()
    assert rows["seq"] == len(site_pages())
    assert {r["url"].removeprefix(site) or "/" for r in rows["rows"]} == set(site_pages())
    summary = client.get("/api/summary").json()
    for tab, f in rule_filters():
        assert summary["tabs"][tab.id][f.id] == len(TRIGGERS[f.rule]), f.rule
    counts = Counter(i["rule_id"] for i in client.get("/api/issues").json())
    assert counts == {r: len(p) for r, p in TRIGGERS.items() if p}

    db = Path(str(crawl["db"]))
    assert db.parent == tmp_path / "crawls"
    assert db.name.startswith("127.0.0.1_")
    with open_store(db) as store:
        assert store.crawl().status == "done"
        assert store.issue_counts() == dict(counts)
        assert len(store.indexability()) == len(site_pages())


def test_rows_arrive_incrementally(client: TestClient, site: str) -> None:
    start(client, site, delay_seconds=0.1)
    first = wait(client, lambda c: int(c["done"]) >= 3)
    page = client.get("/api/rows", params={"since": 0, "rev": 0}).json()
    assert 3 <= len(page["rows"]) <= first["done"] + 2
    seq, rev = page["seq"], page["audit_rev"]

    wait(client, lambda c: int(c["done"]) >= seq + 2)
    delta = client.get("/api/rows", params={"since": seq, "rev": rev}).json()
    if not delta["full"]:
        assert len(delta["rows"]) >= 2
        assert all("title_length" in r for r in delta["rows"])
        assert all(set(p) >= {"url", "rules", "indexable"} for p in delta["patches"])
    assert delta["seq"] >= seq + 2
    client.post("/api/crawl/stop")
    wait(client, settled)


def test_stop_mid_crawl(client: TestClient, site: str) -> None:
    start(client, site, delay_seconds=0.2)
    wait(client, lambda c: int(c["done"]) >= 3)

    stopping = client.post("/api/crawl/stop").json()
    assert stopping["status"] in ("stopping", "finishing", "stopped")
    crawl = wait(client, settled)

    assert crawl["status"] == "stopped"
    assert 3 <= int(crawl["done"]) < len(site_pages())
    assert len(client.get("/api/rows").json()["rows"]) == crawl["done"]
    with open_store(Path(str(crawl["db"]))) as store:
        assert store.crawl().status == "stopped"
        assert store.count_pages("pending") > 0


def test_pause_and_resume(client: TestClient, site: str) -> None:
    start(client, site, delay_seconds=0.2)
    wait(client, lambda c: int(c["done"]) >= 2)

    paused = client.post("/api/crawl/pause").json()
    assert paused["status"] == "paused"
    time.sleep(0.6)
    held = client.get("/api/crawl").json()
    assert held["status"] == "paused"
    assert held["done"] - paused["done"] <= 1

    assert client.post("/api/crawl/resume").json()["status"] == "running"
    crawl = wait(client, settled)
    assert crawl["status"] == "done"
    assert crawl["done"] == len(site_pages())


def test_illegal_transitions_are_409_and_bad_input_400(client: TestClient, site: str) -> None:
    assert client.post("/api/crawl/pause").status_code == 409
    assert client.post("/api/crawl/stop").status_code == 409
    assert client.post("/api/crawl/nope").status_code == 404
    bad = client.post("/api/crawl/start", json={"url": "not a url"})
    assert bad.status_code == 400
    assert "Invalid start URL" in bad.json()["detail"]
    assert client.post("/api/crawl/start", json={"url": site, "workers": 0}).status_code == 422

    start(client, site, delay_seconds=0.2)
    busy = client.post("/api/crawl/start", json={"url": site})
    assert busy.status_code == 409
    assert "running" in busy.json()["detail"]
    assert client.post("/api/crawl/clear").status_code == 409
    client.post("/api/crawl/stop")
    wait(client, settled)


def test_clear_returns_to_idle(client: TestClient, site: str) -> None:
    start(client, site)
    wait(client, settled)

    cleared = client.post("/api/crawl/clear").json()

    assert cleared["status"] == "idle"
    assert cleared["db"] is None
    assert client.get("/api/rows").json()["rows"] == []
    assert client.get("/api/summary").json()["pages"] == 0


def test_starting_over_a_stored_file_leaves_it_untouched(
    audited_db: Path, site: str, tmp_path: Path
) -> None:
    before = audited_db.stat().st_mtime_ns
    with open_store(audited_db) as store:
        counts = store.issue_counts()
    with TestClient(create_app(audited_db, crawls_dir=tmp_path / "crawls")) as client:
        assert client.get("/api/crawl").json()["read_only"] is True
        started = start(client, site, max_pages=5)
        assert started["read_only"] is False
        assert started["db"] != str(audited_db)
        crawl = wait(client, settled)
        assert crawl["status"] == "stopped"  # capped by max_pages
        assert crawl["done"] == 5
        assert len(client.get("/api/rows").json()["rows"]) == 5
    assert audited_db.stat().st_mtime_ns == before
    with open_store(audited_db) as store:
        assert store.issue_counts() == counts
