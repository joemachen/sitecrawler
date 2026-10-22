"""Run the rules over a crawl and summarise what they found."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from sitecrawler.audit.directives import NOINDEX_TOKENS, robots_directives
from sitecrawler.audit.registry import load_rules
from sitecrawler.audit.rule import Rule
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Indexability, Issue, LinkMetrics, Outcome, PageRecord

__all__ = [
    "NOINDEX_TOKENS",
    "AuditResult",
    "RuleCount",
    "indexability",
    "robots_directives",
    "run_audit",
]


def indexability(page: PageRecord, crawl: CrawlView) -> Indexability:
    """Decide whether ``page`` can be indexed, giving the first reason it cannot."""
    if page.outcome is Outcome.BLOCKED:
        return Indexability(False, "blocked by robots.txt")
    if page.outcome is Outcome.REDIRECT_LOOP:
        return Indexability(False, "redirect loop")
    if page.outcome is Outcome.ERROR:
        return Indexability(False, f"fetch error: {page.error}"[:80])
    if page.final_url and not crawl.same_page(page.final_url, page.url):
        return Indexability(False, f"redirects to {page.final_url}")
    if page.status_code is None or page.status_code >= 400:
        return Indexability(False, f"status {page.status_code}")
    if page.status_code >= 300:
        return Indexability(False, f"status {page.status_code} without a target")
    if "html" not in page.content_type:
        return Indexability(False, f"not HTML ({page.content_type or 'unknown type'})")
    if NOINDEX_TOKENS & robots_directives(page):
        return Indexability(False, "noindex")
    canonical = page.canonical_header or page.canonical
    if canonical and not crawl.same_page(canonical, page.url):
        return Indexability(False, f"canonicalised to {canonical}")
    return Indexability(True)


@dataclass(slots=True, frozen=True)
class RuleCount:
    """How many URLs one rule flagged."""

    rule: Rule
    count: int


@dataclass(slots=True)
class AuditResult:
    """Everything one audit run produced."""

    issues: list[Issue]
    verdicts: dict[str, Indexability]
    rules: Sequence[Rule] = field(default_factory=list)
    links: dict[str, LinkMetrics] = field(default_factory=dict)
    """Inlink counts, click depth and Link Score per URL (ADR-0011)."""

    def counts(self) -> list[RuleCount]:
        """Rules that fired, most severe first, then by count."""
        counter = Counter(i.rule_id for i in self.issues)
        rows = [RuleCount(r, counter[r.id]) for r in self.rules if counter[r.id]]
        return sorted(rows, key=lambda rc: (rc.rule.severity.rank, -rc.count, rc.rule.id))


def run_audit(crawl: CrawlView, rules: Sequence[Rule] | None = None) -> AuditResult:
    """Run ``rules`` (default: every shipped rule) over ``crawl``."""
    rules = load_rules() if rules is None else rules
    issues: list[Issue] = []
    for rule in rules:
        issues.extend(rule.check(crawl))
    issues.sort(key=lambda i: (i.severity.rank, i.rule_id, i.url))
    verdicts = {p.url: indexability(p, crawl) for p in crawl.pages}
    return AuditResult(issues, verdicts, rules, dict(crawl.link_graph.metrics))
