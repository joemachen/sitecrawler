"""Response-code rules: pages that did not come back as a usable 2xx."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.rule import PageRule
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, Outcome, PageRecord, Severity

CATEGORY = "Response codes"


def _linked_from(page: PageRecord, crawl: CrawlView) -> str:
    sources = crawl.inlinks_to(page.url)
    if not sources:
        return "linked from nowhere (sitemap or start URL)"
    first = sources[0].src
    more = f" and {len(sources) - 1} more" if len(sources) > 1 else ""
    return f"linked from {first}{more}"


class ClientError(PageRule):
    """4xx responses."""

    id = "response.4xx"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "Page returns a 4xx client error"
    why = (
        "A 4xx page is a dead end for users and gets dropped from the index. When "
        "internal links point at it, the crawl budget and link equity spent on it "
        "are wasted."
    )
    fix = (
        "Restore the page, redirect it (301) to the best replacement, or remove every "
        "internal link that points at it. Keep 410 for pages that are gone on purpose."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag 400-499."""
        if page.status_code is not None and 400 <= page.status_code < 500:
            yield self.issue(page, f"{page.status_code}, {_linked_from(page, crawl)}")


class ServerError(PageRule):
    """5xx responses."""

    id = "response.5xx"
    severity = Severity.CRITICAL
    category = CATEGORY
    summary = "Page returns a 5xx server error"
    why = (
        "Server errors mean the page could not be served at all. Repeated 5xx "
        "responses make search engines slow their crawling of the whole site and "
        "eventually drop the affected URLs."
    )
    fix = (
        "Check the server logs for the URL, fix the underlying error, and re-crawl. "
        "If the error is intermittent, look at capacity and rate limits."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag 500-599."""
        if page.status_code is not None and page.status_code >= 500:
            yield self.issue(page, f"{page.status_code}, {_linked_from(page, crawl)}")


class FetchError(PageRule):
    """No usable response at all."""

    id = "response.error"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "Page could not be fetched (timeout or connection error)"
    why = (
        "A timeout or connection failure means the crawler, and probably search "
        "engines, got nothing back. Pages that fail this way are not indexed and "
        "may be slow for users too."
    )
    fix = (
        "Open the URL in a browser. If it loads, check for slow responses, aggressive "
        "rate limiting or bot blocking; if it does not, fix the server or DNS."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag ``Outcome.ERROR``."""
        if page.outcome is Outcome.ERROR:
            yield self.issue(page, page.error)


class BlockedByRobots(PageRule):
    """robots.txt disallowed a URL that the site links to."""

    id = "response.blocked_by_robots"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Linked page is blocked by robots.txt"
    why = (
        "Search engines will not fetch a disallowed URL, so whatever it contains "
        "cannot rank. When it is also linked internally or listed in the sitemap, "
        "the site is sending mixed signals and leaking link equity into a page "
        "that cannot use it."
    )
    fix = (
        "If the page should rank, remove the Disallow rule. If it should not, stop "
        "linking to it internally and take it out of the sitemap; use noindex "
        "rather than robots.txt when it must stay reachable but unindexed."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag ``Outcome.BLOCKED``."""
        if page.outcome is Outcome.BLOCKED:
            yield self.issue(page, _linked_from(page, crawl))
