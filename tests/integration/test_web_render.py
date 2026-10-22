"""Rendering from the web UI: the Settings checkbox reaches the crawler, the pane shows the diff.

Needs Chromium (marker ``browser``). The crawl runs on the session's worker
thread, so Playwright's async API never meets the test client's loop.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sitecrawler.web import create_app
from tests.integration.test_web_live import settled, start, wait

pytestmark = pytest.mark.browser


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(crawls_dir=tmp_path / "crawls")) as c:
        yield c


def test_render_setting_renders_the_crawl_and_fills_the_javascript_tab(
    client: TestClient, site: str
) -> None:
    start(client, site, render=True, max_pages=60)
    crawl = wait(client, settled, timeout=120)
    assert crawl["status"] == "done", crawl
    page = f"{site}/js-injected"

    rows = {row["url"]: row for row in client.get("/api/rows").json()["rows"]}
    row = rows[page]
    assert row["render_status"] == "rendered"
    assert row["render_changes"] == "title, canonical, links +3"
    assert row["title"] == "Rendered title set by JavaScript on load"
    assert row["raw_title"] == "Raw title before JavaScript runs on this page"
    assert row["canonical"] == page
    assert row["raw_canonical"] == ""
    assert "render.differs" in row["rules"]
    assert rows[f"{site}/about"]["render_status"] == "rendered"
    assert rows[f"{site}/about"]["render_changes"] == ""
    assert rows[f"{site}/missing"]["render_status"] == ""
    download = rows[f"{site}/audit/render-download"]
    assert download["render_status"] == "failed"
    assert download["render_error"].startswith("render failed: ")
    assert "render.failed" in download["rules"]

    tabs = client.get("/api/summary").json()["tabs"]["javascript"]
    assert tabs["differs"] == 1
    assert tabs["failed"] == 1
    assert tabs["rendered"] == tabs["same"] + 1
    assert tabs["rendered"] > 1

    pane = client.get("/detail/render", params={"url": page}).text
    assert 'data-render="changed"' in pane
    assert "title, canonical, links +3" in pane
    assert f"<li>{site}/about</li>" in pane
    assert 'data-links="removed"' not in pane
    same = client.get("/detail/render", params={"url": f"{site}/about"}).text
    assert 'data-render="same"' in same
    assert client.get("/page", params={"url": page}).status_code == 200


def test_unrendered_crawl_shows_the_hint_in_the_pane(client: TestClient, site: str) -> None:
    start(client, site, max_pages=2)
    wait(client, settled)
    pane = client.get("/detail/render", params={"url": f"{site}/"}).text
    assert 'data-render="none"' in pane
    assert "--render" in pane
