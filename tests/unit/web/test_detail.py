"""Rule rows, per-rule issues and page detail from a hand-built snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sitecrawler.audit import load_rules
from sitecrawler.models import CrawlInfo
from sitecrawler.store.dump import PAGE_COLUMNS, TableDump
from sitecrawler.web import CrawlSnapshot
from tests.unit.audit.helpers import SITE, links, page, view
from tests.unit.web.test_data import ISSUE_COLUMNS, REDIRECT_COLUMNS, page_row


def snapshot() -> CrawlSnapshot:
    home = page("/", links=links("/a", "/missing"))
    a = page("/a", links=links("/missing"))
    missing = page("/missing", status=404, title="", h1s=(), links=())
    rules = {r.id: r for r in load_rules()}
    return CrawlSnapshot(
        path=Path("crawl.db"),
        info=CrawlInfo(
            "https://site.test/", "crawl", "0", "done", 3, datetime(2026, 1, 1, tzinfo=UTC)
        ),
        view=view([home, a, missing]),
        pages=TableDump(
            "pages",
            PAGE_COLUMNS,
            [
                page_row(f"{SITE}/", indexable=True),
                page_row(f"{SITE}/a", indexable=True),
                page_row(
                    f"{SITE}/missing",
                    status_code=404,
                    indexable=False,
                    indexability_reason="status 404",
                ),
            ],
        ),
        issues=TableDump(
            "issues",
            ISSUE_COLUMNS,
            [
                (f"{SITE}/missing", "page.non_indexable", "info", "status 404"),
                (f"{SITE}/missing", "response.4xx", "high", "404, linked from /"),
                (f"{SITE}/a", "title.too_short", "low", ""),
                (f"{SITE}/", "title.too_short", "low", ""),
            ],
        ),
        redirects=TableDump("redirects", REDIRECT_COLUMNS, []),
        rules=rules,
        issue_counts={
            "response.4xx": 1,
            "title.too_short": 2,
            "page.non_indexable": 1,
            "gone.rule": 3,
        },
    )


def test_rule_rows_are_sorted_by_severity_then_count_and_skip_unknown_rules() -> None:
    rows = snapshot().rule_rows()
    assert [(r.rule.id, r.count) for r in rows] == [
        ("response.4xx", 1),
        ("title.too_short", 2),
        ("page.non_indexable", 1),
    ]


def test_issues_for_one_rule() -> None:
    rows = snapshot().issues_for("title.too_short")
    assert [r["url"] for r in rows] == [f"{SITE}/a", f"{SITE}/"]
    assert snapshot().issues_for("nope") == []


def test_page_detail_joins_verdict_issues_and_inlinks() -> None:
    detail = snapshot().page_detail(f"{SITE}/missing")
    assert detail is not None
    assert (detail.indexable, detail.indexability_reason) == (False, "status 404")
    assert [i["rule_id"] for i in detail.issues] == ["response.4xx", "page.non_indexable"]
    assert detail.issues[0]["summary"] == snapshot().rules["response.4xx"].summary
    assert sorted(i.src for i in detail.inlinks) == [f"{SITE}/", f"{SITE}/a"]


def test_page_detail_for_unknown_url_is_none() -> None:
    assert snapshot().page_detail("https://elsewhere.test/") is None
