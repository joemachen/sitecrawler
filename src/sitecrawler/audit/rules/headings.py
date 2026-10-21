"""Heading rules: H1 presence, count, length, duplication, and H2 presence."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.rule import HtmlPageRule, Rule
from sitecrawler.audit.rules.titles import _others
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Headings"
MAX_H1_LENGTH = 70


class H1Missing(HtmlPageRule):
    """No H1."""

    id = "h1.missing"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Page has no H1"
    why = (
        "The H1 tells readers and search engines what the page is about at a "
        "glance. Pages without one tend to have a weaker topical signal and are "
        "harder to scan."
    )
    fix = "Add one H1 that states the page's subject, usually close to the title."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with no H1."""
        if not page.h1s:
            yield self.issue(page)


class H1Multiple(HtmlPageRule):
    """Several H1s."""

    id = "h1.multiple"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page has more than one H1"
    why = (
        "HTML5 allows several H1s, but most templates that produce them are "
        "misusing the tag for styling, which dilutes the main heading and confuses "
        "screen readers."
    )
    fix = "Keep one H1 for the page subject and demote the others to H2."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with two or more H1s."""
        if len(page.h1s) > 1:
            yield self.issue(page, f"{len(page.h1s)} H1s: " + " | ".join(page.h1s[:3]))


class H1Duplicate(Rule):
    """Same H1 across pages."""

    id = "h1.duplicate"
    severity = Severity.LOW
    category = CATEGORY
    summary = "H1 is shared with other pages"
    why = (
        "Pages with the same main heading look like the same page; it is usually a "
        "template putting the site or section name where the page subject belongs."
    )
    fix = "Make the H1 specific to the page."

    def check(self, crawl: CrawlView) -> Iterable[Issue]:
        """Flag every member of a group sharing an H1."""
        for group in crawl.group_html_pages(lambda p: p.h1.casefold()).values():
            if len(group) > 1:
                for page in group:
                    yield self.issue(page, _others(page, group))


class H1TooLong(HtmlPageRule):
    """Very long H1."""

    id = "h1.too_long"
    severity = Severity.LOW
    category = CATEGORY
    summary = f"H1 is longer than {MAX_H1_LENGTH} characters"
    why = "A heading that runs to a paragraph is hard to scan and usually says too much."
    fix = "Shorten the H1 to one line and move the rest into the opening paragraph."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag H1s over the limit."""
        if len(page.h1) > MAX_H1_LENGTH:
            yield self.issue(page, f"{len(page.h1)} characters")


class H2Missing(HtmlPageRule):
    """No H2 at all."""

    id = "h2.missing"
    severity = Severity.INFO
    category = CATEGORY
    summary = "Page has no H2 headings"
    why = (
        "Sub-headings break content into scannable sections and give search "
        "engines the page's sub-topics. Short pages do not need them; long ones do."
    )
    fix = "Add H2s for each section of a page that has more than a few paragraphs."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with no H2."""
        if not page.h2s:
            yield self.issue(page)
