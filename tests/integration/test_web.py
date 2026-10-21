"""The web app over the stored fixture crawl, driven through FastAPI's test client."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sitecrawler.web import TABS, create_app
from sitecrawler.web.tabs import rule_filters
from tests.conftest import site_pages
from tests.integration.test_audit import TRIGGERS


@pytest.fixture
def client(audited_db: Path) -> Iterator[TestClient]:
    with TestClient(create_app(audited_db)) as c:
        yield c


def test_shell_renders_every_tab_and_the_specs(client: TestClient, site: str) -> None:
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert site in html
    assert 'data-status="done"' in html
    assert "read-only" in html
    for tab in TABS:
        assert f'data-tab="{tab.id}"' in html
    assert 'id="tab-specs"' in html
    assert '"column": "rules"' in html


def test_crawl_state_of_a_stored_file(client: TestClient, site: str, audited_db: Path) -> None:
    state = client.get("/api/crawl").json()
    assert state["status"] == "done"
    assert state["read_only"] is True
    assert state["start_url"] == site
    assert state["db"] == str(audited_db)
    assert state["done"] == state["seq"] == len(site_pages())
    assert state["audit_rev"] == 1
    assert state["queued"] == 0


def test_unaudited_file_is_audited_in_memory(crawled_db: Path) -> None:
    with TestClient(create_app(crawled_db)) as client:
        assert client.get("/api/crawl").json()["audit_rev"] == 1
        summary = client.get("/api/summary").json()
        assert summary["tabs"]["titles"]["missing"] == len(TRIGGERS["title.missing"])
        assert "No audit has run yet" not in client.get("/issues").text


def test_rows_carry_base_and_audit_cells(client: TestClient, site: str) -> None:
    page = client.get("/api/rows").json()
    assert page["seq"] == len(site_pages())
    assert page["audit_rev"] == 1
    assert page["patches"] == []
    assert page["full"] is False
    rows = page["rows"]
    assert {row["url"].removeprefix(site) or "/" for row in rows} == set(site_pages())
    missing = next(row for row in rows if row["url"] == f"{site}/missing")
    assert missing["status_code"] == 404
    assert missing["status_class"] == "4xx"
    assert missing["indexable"] is False
    assert missing["indexability_reason"] == "status 404"
    assert "response.4xx" in missing["rules"]
    assert missing["inlinks"] >= 1
    assert "title_length" in missing

    assert client.get("/api/rows", params={"since": len(rows), "rev": 1}).json()["rows"] == []


@pytest.mark.parametrize(
    ("tab", "filter_id", "rule"), [(t.id, f.id, f.rule) for t, f in rule_filters()]
)
def test_summary_counts_match_the_audit(
    client: TestClient, tab: str, filter_id: str, rule: str
) -> None:
    summary = client.get("/api/summary").json()
    assert summary["tabs"][tab][filter_id] == len(TRIGGERS[rule]), rule


def test_summary_totals(client: TestClient) -> None:
    summary = client.get("/api/summary").json()
    assert summary["pages"] == len(site_pages())
    assert summary["seq"] == len(site_pages())
    assert summary["audit_rev"] == 1
    assert summary["status"]["4xx"] == 1
    assert summary["status"]["blocked"] == 2
    assert summary["tabs"]["internal"]["all"] == len(site_pages())
    assert summary["tabs"]["response_codes"]["4xx"] == 1
    assert summary["indexable"] + summary["non_indexable"] == len(site_pages())
    assert summary["issues"]["high"] >= 1
    assert summary["tabs"]["issues"]["all"] == len({r for r, p in TRIGGERS.items() if p})


def test_external_rows_list_off_site_link_targets(client: TestClient) -> None:
    rows = client.get("/api/external").json()
    assert rows, "the fixture site links off-site"
    assert all(not r["url"].startswith("http://127.0.0.1") for r in rows)
    assert all(r["inlinks"] >= 1 for r in rows)


def test_static_assets_are_served(client: TestClient) -> None:
    for name in ("htmx.min.js", "tabulator.min.js", "tabulator.min.css", "app.js", "app.css"):
        assert client.get(f"/static/{name}").status_code == 200, name


def test_no_api_docs_are_exposed(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
