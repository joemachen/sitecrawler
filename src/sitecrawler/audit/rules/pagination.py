"""Pagination rules: rel=prev/next targets, canonicals on paginated pages, sequence breaks."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.rule import HtmlPageRule
from sitecrawler.audit.rules._common import describe_target
from sitecrawler.audit.rules.canonicals import effective_canonical
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Pagination"


class ToNon200(HtmlPageRule):
    """rel=prev/next pointing at a dead page."""

    id = "pagination.to_non_200"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "rel=prev or rel=next points at a URL that is not a 200 page"
    why = (
        "A pagination link to a missing or redirecting page breaks the series: "
        "crawlers stop there and the pages beyond it lose their path in."
    )
    fix = "Point rel=prev/next at the live URL of the neighbouring page."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag crawled prev/next targets that are not a plain 200."""
        bad: list[str] = []
        for rel, href in (("prev", page.rel_prev), ("next", page.rel_next)):
            if not href:
                continue
            target = crawl.page_for(href)
            if target is None:
                continue
            problem = describe_target(crawl, target)
            if problem:
                bad.append(f"{rel} {href} {problem}")
        if bad:
            yield self.issue(page, ", ".join(bad))


class CanonicalToFirstPage(HtmlPageRule):
    """Page 2+ canonicalised to page 1."""

    id = "pagination.canonical_to_first"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Paginated page canonicalises to another page in the series"
    why = (
        "Pointing page 2, 3, ... at page 1 tells search engines those pages are "
        "duplicates, so the items listed only on them are never discovered. Each "
        "page in a series should be its own canonical."
    )
    fix = "Give every paginated page a self-referencing canonical."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with rel=prev (so not the first) whose canonical is another page."""
        canonical = effective_canonical(page)
        if page.rel_prev and canonical and not crawl.same_page(canonical, page.url):
            yield self.issue(page, f"canonical {canonical}")


class BrokenSequence(HtmlPageRule):
    """Next page does not point back."""

    id = "pagination.broken_sequence"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "rel=next target does not link back with rel=prev"
    why = (
        "prev/next should form a chain that reads the same in both directions. A "
        "next page whose prev points somewhere else (or nowhere) means the series "
        "has a gap or two series are tangled."
    )
    fix = "Make the next page's rel=prev point back at this page."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages whose crawled next page has a prev that is not this page."""
        if not page.rel_next:
            return
        target = crawl.page_for(page.rel_next)
        if target is None or not crawl.is_html_page(target):
            return
        if not target.rel_prev or not crawl.same_page(target.rel_prev, page.url):
            back = target.rel_prev or "nothing"
            yield self.issue(page, f"next {page.rel_next} has prev {back}")
