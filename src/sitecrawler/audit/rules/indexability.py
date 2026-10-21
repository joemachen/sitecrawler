"""The indexability verdict, surfaced as an informational issue."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.engine import indexability
from sitecrawler.audit.rule import PageRule
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity


class NonIndexable(PageRule):
    """Every page that cannot be indexed, with the reason."""

    id = "page.non_indexable"
    severity = Severity.INFO
    category = "Indexability"
    summary = "Page cannot be indexed"
    why = (
        "One list of everything search engines will not index, whatever the cause: "
        "robots.txt, errors, redirects, noindex or a canonical pointing elsewhere. "
        "The specific rules say which of these are problems; this one is the roll-up "
        "to check against what you expect the site to show in search."
    )
    fix = "Scan the reasons; anything you did not intend has its own rule and fix above."

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages whose verdict is not indexable."""
        verdict = indexability(page, crawl)
        if not verdict.indexable:
            yield self.issue(page, verdict.reason)
