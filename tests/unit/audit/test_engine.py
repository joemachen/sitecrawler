from collections.abc import Iterable

import pytest

from sitecrawler.audit import CrawlView, HtmlPageRule, PageRule, Rule, indexability, run_audit
from sitecrawler.audit.engine import robots_directives
from sitecrawler.models import Issue, Outcome, PageRecord, Severity
from tests.unit.audit.helpers import SITE, blocked, page, view


@pytest.mark.parametrize(
    ("meta", "header", "expected"),
    [
        ("", "", set()),
        ("noindex, follow", "", {"noindex", "follow"}),
        ("", "NOINDEX; nofollow", {"noindex", "nofollow"}),
        ("index", "googlebot: noindex", {"index", "noindex"}),
        ("", "otherbot: noindex", set()),
        ("", "unavailable_after: 2030-01-01", set()),
    ],
)
def test_robots_directives(meta: str, header: str, expected: set[str]) -> None:
    p = page("/", meta_robots=meta, headers={"x-robots-tag": header} if header else {})
    assert robots_directives(p) == frozenset(expected)


@pytest.mark.parametrize(
    ("record", "indexable", "reason"),
    [
        (page("/ok"), True, ""),
        (blocked("/b"), False, "blocked by robots.txt"),
        (page("/loop", None, outcome=Outcome.REDIRECT_LOOP), False, "redirect loop"),
        (page("/err", None, outcome=Outcome.ERROR, error="boom"), False, "fetch error: boom"),
        (page("/missing", 404), False, "status 404"),
        (
            page("/r404", 404, final_url=f"{SITE}/gone"),
            False,
            f"redirects to {SITE}/gone",
        ),
        (page("/odd", 302), False, "status 302 without a target"),
        (page("/r", final_url=f"{SITE}/elsewhere"), False, f"redirects to {SITE}/elsewhere"),
        (page("/pdf", content_type="application/pdf"), False, "not HTML (application/pdf)"),
        (page("/x", content_type=""), False, "not HTML (unknown type)"),
        (page("/noindex", meta_robots="noindex"), False, "noindex"),
        (page("/none", headers={"x-robots-tag": "none"}), False, "noindex"),
        (page("/canon", canonical=f"{SITE}/other"), False, f"canonicalised to {SITE}/other"),
        (page("/hc", canonical_header=f"{SITE}/h"), False, f"canonicalised to {SITE}/h"),
        (page("/self", canonical=f"{SITE}/self/"), True, ""),
        (page("/nocanon", canonical=""), True, ""),
    ],
)
def test_indexability(record: PageRecord, indexable: bool, reason: str) -> None:
    verdict = indexability(record, view([record]))
    assert verdict.indexable is indexable
    assert verdict.reason == reason


class _Always(PageRule):
    id = "test.always"
    severity = Severity.LOW
    category = "Test"
    summary = "always"
    why = "w"
    fix = "f"

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        yield self.issue(page, "hit")


class _Never(Rule):
    id = "test.never"
    severity = Severity.CRITICAL
    category = "Test"
    summary = "never"
    why = "w"
    fix = "f"

    def check(self, crawl: CrawlView) -> Iterable[Issue]:
        return []


def test_run_audit_sorts_and_counts() -> None:
    pages = [page("/b"), page("/a"), page("/missing", 404)]
    result = run_audit(view(pages), rules=[_Never(), _Always()])
    assert [i.url.removeprefix(SITE) for i in result.issues] == ["/a", "/b", "/missing"]
    assert result.issues[0].message == "hit"
    counts = result.counts()
    assert [(c.rule.id, c.count) for c in counts] == [("test.always", 3)]
    assert result.verdicts[f"{SITE}/missing"].reason == "status 404"
    assert result.verdicts[f"{SITE}/a"].indexable


def test_run_audit_uses_shipped_rules_by_default() -> None:
    result = run_audit(view([page("/missing", 404)]))
    assert any(i.rule_id == "response.4xx" for i in result.issues)
    assert {r.id for r in result.rules} >= {"response.4xx", "response.5xx"}


class _HtmlOnly(HtmlPageRule):
    id = "test.html_only"
    severity = Severity.INFO
    category = "Test"
    summary = "html only"
    why = "w"
    fix = "f"

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        yield self.issue(page)


def test_html_page_rule_skips_non_html_pages() -> None:
    pages = [page("/ok"), page("/missing", 404), page("/pdf", content_type="application/pdf")]
    found = list(_HtmlOnly().check(view(pages)))
    assert [i.url.removeprefix(SITE) for i in found] == ["/ok"]
