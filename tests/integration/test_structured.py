"""Phase 10 end to end: structured data over the fixture crawl, CLI, store and web UI."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from sitecrawler.analysis import structured_report
from sitecrawler.audit import CrawlView, run_audit
from sitecrawler.cli.main import app
from sitecrawler.store import open_store
from sitecrawler.store.dump import PAGE_COLUMNS, dump_tables
from sitecrawler.web import create_app
from tests.integration.test_audit import TRIGGERS

runner = CliRunner()

SCHEMA_PAGES = (
    "/audit/schema-article",
    "/audit/schema-conflict",
    "/audit/schema-invalid-json",
    "/audit/schema-no-price",
    "/audit/schema-product",
    "/audit/schema-unknown",
)


def test_a_product_missing_offers_price_is_flagged_and_a_complete_one_passes(
    crawled_db: Path, site: str
) -> None:
    with open_store(crawled_db) as store:
        crawl = CrawlView.from_store(store)
    index = crawl.structured
    assert index.findings_for(f"{site}/audit/schema-product") == []
    (missing,) = index.findings_for(f"{site}/audit/schema-no-price")
    assert (missing.kind, missing.type) == ("missing_required", "Product")
    assert missing.path.startswith("offers.price")

    by_rule: dict[str, set[str]] = {}
    for issue in run_audit(crawl).issues:
        by_rule.setdefault(issue.rule_id, set()).add(issue.url.removeprefix(site))
    assert by_rule["schema.missing_required"] == {"/audit/schema-no-price"}
    flagged_complete = {r for r, paths in by_rule.items() if "/audit/schema-product" in paths}
    assert not any(r.startswith("schema.") for r in flagged_complete)


def test_every_syntax_is_read_from_the_fixture_site(crawled_db: Path, site: str) -> None:
    with open_store(crawled_db) as store:
        crawl = CrawlView.from_store(store)
    found = {
        p.url.removeprefix(site): p.structured
        for p in crawl.structured.pages
        if p.structured is not None and not p.structured.empty
    }
    assert set(found) == set(SCHEMA_PAGES)
    assert found["/audit/schema-article"].formats == ("rdfa",)
    assert found["/audit/schema-conflict"].formats == ("json-ld", "microdata")
    assert found["/audit/schema-unknown"].types == ("WebPage", "Prodcut")
    assert found["/audit/schema-invalid-json"].items == ()
    (error,) = found["/audit/schema-invalid-json"].errors
    assert error.line == 12  # the stray comma
    assert error.message.startswith("Illegal trailing comma")
    report = structured_report(crawl)
    assert report.with_items == 5
    assert report.formats == {"json-ld": 3, "microdata": 2, "rdfa": 1}
    counts = {t.type: (t.items, t.pages, t.rich_result) for t in report.types}
    assert [t.type for t in report.types][:2] == ["WebPage", "Product"]  # most items first
    assert counts["WebPage"] == (3, 2, "")
    assert counts["Product"] == (2, 2, "Product")
    assert counts["Article"] == (1, 1, "Article")
    assert report.pages_with("conflicting") == 1


def test_schema_report_command(crawled_db: Path, site: str) -> None:
    result = runner.invoke(app, ["schema", "report", str(crawled_db)])
    assert result.exit_code == 0, result.output
    lines = [line.split("\t") for line in result.stdout.splitlines() if "\t" in line]
    assert [
        "missing_required",
        f"{site}/audit/schema-no-price",
        "Product",
        "offers.price or offers.priceSpecification.price or offers.lowPrice",
        "Product needs offers.price or offers.priceSpecification.price or offers.lowPrice",
    ] in lines
    assert {line[0] for line in lines} == {
        "invalid_json",
        "missing_required",
        "unknown_type",
        "conflicting",
        "unknown_property",
        "missing_recommended",
    }
    only = runner.invoke(app, ["schema", "report", str(crawled_db), "--kind", "unknown_type"])
    assert only.exit_code == 0, only.output
    assert [line.split("\t")[0] for line in only.stdout.splitlines() if "\t" in line] == [
        "unknown_type"
    ]
    bad = runner.invoke(app, ["schema", "report", str(crawled_db), "--kind", "typo"])
    assert bad.exit_code == 2
    assert "--kind must be one of" in bad.output


def test_audit_prints_the_structured_data_summary(crawled_db: Path) -> None:
    result = runner.invoke(app, ["audit", str(crawled_db)])
    assert result.exit_code == 0, result.output
    squashed = re.sub(r"\s+", "", result.output)  # Rich wraps
    assert "Structureddata:5of" in squashed
    assert "sitecrawlerschemareport" in squashed
    with open_store(crawled_db) as store:
        counts = store.issue_counts()
    for rule in ("schema.invalid_json", "schema.missing_required", "schema.conflicting"):
        assert counts[rule] == len(TRIGGERS[rule])


def test_structured_data_is_stored_and_exported(crawled_db: Path, site: str) -> None:
    with open_store(crawled_db) as store:
        tables = {t.name: t for t in dump_tables(store, ("pages", "structured_data"))}
    pages = tables["pages"]
    assert PAGE_COLUMNS[-1] == "structured_types"
    by_url = {row[0]: dict(zip(pages.columns, row, strict=True)) for row in pages.rows}
    assert by_url[f"{site}/audit/schema-conflict"]["structured_types"] == "WebPage"
    assert by_url[f"{site}/audit/schema-unknown"]["structured_types"] == "WebPage Prodcut"
    assert by_url[f"{site}/about"]["structured_types"] == ""
    rows = tables["structured_data"].rows
    assert {str(row[0]).removeprefix(site) for row in rows} == set(SCHEMA_PAGES)
    error = next(row for row in rows if row[4] is not None)
    assert error[0] == f"{site}/audit/schema-invalid-json"
    product = next(row for row in rows if row[0] == f"{site}/audit/schema-product")
    assert json.loads(str(product[5]))["offers"][0]["price"] == ["39.00"]


def test_structured_tab_cells_and_detail(audited_db: Path, site: str) -> None:
    with TestClient(create_app(audited_db)) as client:
        rows = {r["url"]: r for r in client.get("/api/rows").json()["rows"]}
        conflict = rows[f"{site}/audit/schema-conflict"]
        assert conflict["structured_items"] == 2
        assert conflict["structured_formats"] == "json-ld, microdata"
        assert conflict["schema_problems"] == 1
        assert "schema.conflicting" in conflict["rules"]
        assert rows[f"{site}/audit/schema-product"]["schema_problems"] == 0
        assert rows[f"{site}/about"]["structured_items"] == 0
        assert rows[f"{site}/missing"]["structured_items"] is None

        summary = client.get("/api/summary").json()["tabs"]["structured"]
        assert summary["has_structured"] == 5
        assert summary["missing_required"] == len(TRIGGERS["schema.missing_required"])
        assert summary["unknown_type"] == 1

        detail = client.get(
            "/detail/structured", params={"url": f"{site}/audit/schema-no-price"}
        ).text
        assert 'data-finding="schema.missing_required"' in detail
        assert 'data-item="json-ld"' in detail
        assert "Stoneware teapot" in detail
        assert "&#34;priceCurrency&#34;: [" in detail  # pretty_json, escaped once
        clean = client.get(
            "/detail/structured", params={"url": f"{site}/audit/schema-product"}
        ).text
        assert "No problems found" in clean
        none = client.get("/detail/structured", params={"url": f"{site}/about"}).text
        assert 'data-structured="none"' in none
        unparsed = client.get("/detail/structured", params={"url": f"{site}/missing"}).text
        assert 'data-structured="unparsed"' in unparsed
