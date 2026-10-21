"""The web app over the stored fixture crawl, driven through FastAPI's test client."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sitecrawler.store.dump import PAGE_COLUMNS
from sitecrawler.web import create_app
from tests.conftest import site_pages


@pytest.fixture
def client(audited_db: Path) -> Iterator[TestClient]:
    with TestClient(create_app(audited_db)) as c:
        yield c


def test_overview_shows_the_crawl_numbers(client: TestClient, site: str) -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert site in html
    assert f'data-stat="pages">{len(site_pages())}<' in html
    assert 'data-status="4xx">' in html
    assert 'data-severity="high">' in html
    assert "No audit stored yet" not in html


def test_overview_without_an_audit_says_so(crawled_db: Path) -> None:
    with TestClient(create_app(crawled_db)) as client:
        html = client.get("/").text
    assert "No audit stored yet" in html
    assert 'data-stat="issues">0<' in html


def test_pages_tab_and_its_json(client: TestClient, site: str) -> None:
    page = client.get("/pages")
    assert page.status_code == 200
    assert 'data-grid="/api/pages"' in page.text
    for column in PAGE_COLUMNS:
        assert f'"{column}"' in page.text

    rows = client.get("/api/pages").json()
    assert len(rows) == len(site_pages())
    assert {row["url"].removeprefix(site) or "/" for row in rows} == set(site_pages())
    missing = next(row for row in rows if row["url"] == f"{site}/missing")
    assert missing["status_code"] == 404
    assert missing["indexable"] is False
    assert missing["indexability_reason"] == "status 404"


def test_static_assets_are_served(client: TestClient) -> None:
    for name in ("htmx.min.js", "tabulator.min.js", "tabulator.min.css", "app.js", "app.css"):
        assert client.get(f"/static/{name}").status_code == 200, name


def test_no_api_docs_are_exposed(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
