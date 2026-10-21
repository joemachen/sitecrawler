"""Robots directive rules: meta robots, X-Robots-Tag and robots.txt interactions."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.engine import NOINDEX_TOKENS, robots_directives
from sitecrawler.audit.rule import HtmlPageRule, PageRule
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, Outcome, PageRecord, Severity

CATEGORY = "Robots directives"
CONFLICTS = (("index", "noindex"), ("follow", "nofollow"), ("all", "none"))


def _directives(page: PageRecord) -> str:
    return ", ".join(sorted(robots_directives(page)))


class Noindex(HtmlPageRule):
    """Explicit noindex."""

    id = "robots.noindex"
    severity = Severity.INFO
    category = CATEGORY
    summary = "Page is set to noindex"
    why = (
        "The page asks not to be indexed, via meta robots or X-Robots-Tag. Correct "
        "for thank-you pages and internal search; a disaster when it is left on "
        "after a launch."
    )
    fix = "Confirm each listed page should stay out of search; remove the directive otherwise."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag the ``noindex`` token (``none`` has its own rule)."""
        if "noindex" in robots_directives(page):
            yield self.issue(page, _directives(page))


class Nofollow(HtmlPageRule):
    """Page-level nofollow."""

    id = "robots.nofollow"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page is set to nofollow"
    why = (
        "A page-level nofollow tells crawlers to ignore every link on the page, so "
        "nothing it links to gets any equity from it. Rarely what anyone intends."
    )
    fix = (
        "Remove nofollow from meta robots or X-Robots-Tag; use rel=nofollow on "
        "individual links instead."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag the ``nofollow`` token (``none`` has its own rule)."""
        if "nofollow" in robots_directives(page):
            yield self.issue(page, _directives(page))


class NoneDirective(HtmlPageRule):
    """The ``none`` shorthand."""

    id = "robots.none"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page uses the robots directive none (noindex and nofollow)"
    why = (
        "``none`` is shorthand for noindex plus nofollow. It is easy to misread as "
        "'no directives' and is best spelled out."
    )
    fix = "Replace it with the explicit directives you mean, or remove it."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag the ``none`` token."""
        if "none" in robots_directives(page):
            yield self.issue(page, _directives(page))


class Conflicting(HtmlPageRule):
    """Contradictory directives."""

    id = "robots.conflicting"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Robots directives contradict each other"
    why = (
        "index and noindex (or follow and nofollow) on the same page, across the "
        "meta tag and the X-Robots-Tag header, leave the outcome to each search "
        "engine's tie-break rule. Google takes the most restrictive."
    )
    fix = "Decide what the page should do and keep a single consistent directive."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages carrying both halves of any opposing pair."""
        tokens = robots_directives(page)
        if any(a in tokens and b in tokens for a, b in CONFLICTS):
            yield self.issue(page, _directives(page))


class NoindexInSitemap(HtmlPageRule):
    """A noindex page the sitemap still advertises."""

    id = "robots.noindex_in_sitemap"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Noindex page is listed in the sitemap"
    why = (
        "The sitemap says 'please index this' and the page says 'do not'. Search "
        "engines follow the page, and lose a little trust in the sitemap."
    )
    fix = "Remove noindex pages from the sitemap (or drop the noindex if they should rank)."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag noindex pages present in a sitemap."""
        if NOINDEX_TOKENS & robots_directives(page) and crawl.listed_in_sitemap(page.url):
            yield self.issue(page, _directives(page))


class NoindexLinked(HtmlPageRule):
    """A noindex page that internal links still point at."""

    id = "robots.noindex_linked"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Noindex page receives internal links"
    why = (
        "Links into a page that cannot rank are wasted link equity, and over time "
        "Google stops following links from long-term noindex pages too."
    )
    fix = "Link to an indexable page instead, or reconsider whether this page should be noindex."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag noindex pages with at least one inlink."""
        if NOINDEX_TOKENS & robots_directives(page):
            sources = crawl.inlinks_to(page.url)
            if sources:
                yield self.issue(page, f"linked from {sources[0].src}")


class BlockedButLinked(PageRule):
    """robots.txt disallows a page the site links to."""

    id = "robots.blocked_but_linked"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Internal links point at a URL blocked by robots.txt"
    why = (
        "Crawlers follow the link, hit the Disallow rule and stop: the page can still "
        "be indexed (URL only, no content) and the link equity goes nowhere useful."
    )
    fix = (
        "If the page should rank, allow it in robots.txt. If it should not, use "
        "noindex instead of Disallow, or stop linking to it."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag blocked pages with at least one inlink."""
        if page.outcome is Outcome.BLOCKED:
            sources = crawl.inlinks_to(page.url)
            if sources:
                more = f" and {len(sources) - 1} more" if len(sources) > 1 else ""
                yield self.issue(page, f"linked from {sources[0].src}{more}")
