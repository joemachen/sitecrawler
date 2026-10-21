"""Title tag rules."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.rule import HtmlPageRule, Rule
from sitecrawler.audit.rules._common import describe_group
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Titles"
MAX_LENGTH = 60
"""Roughly what fits in a desktop result before Google truncates (about 580 px)."""
MIN_LENGTH = 30


class Missing(HtmlPageRule):
    """No ``<title>`` text."""

    id = "title.missing"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "Page has no title"
    why = (
        "The title is the headline of the search result and the strongest on-page "
        "relevance signal. Without one Google invents a title from the content or "
        "the anchor text, usually badly."
    )
    fix = "Add a unique, descriptive <title> of roughly 30 to 60 characters."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag an empty title."""
        if not page.title:
            yield self.issue(page)


class Duplicate(Rule):
    """The same title on more than one page."""

    id = "title.duplicate"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Title is shared with other pages"
    why = (
        "Identical titles tell search engines the pages are about the same thing, so "
        "they compete with each other and the result shown may be the wrong one. "
        "They also make the pages indistinguishable in a results list."
    )
    fix = (
        "Give each page a title that names what makes it different. If the pages "
        "really are the same, canonicalise or merge them instead."
    )

    def check(self, crawl: CrawlView) -> Iterable[Issue]:
        """Flag every member of a group sharing a title."""
        for group in crawl.group_html_pages(lambda p: p.title.casefold()).values():
            if len(group) > 1:
                for page in group:
                    yield self.issue(page, describe_group(page, group))


class TooLong(HtmlPageRule):
    """Title likely to be truncated."""

    id = "title.too_long"
    severity = Severity.LOW
    category = CATEGORY
    summary = f"Title is longer than {MAX_LENGTH} characters"
    why = (
        "Google cuts titles off at about 580 pixels, roughly 60 characters, so the "
        "end of a long title is never seen and the whole thing may be rewritten."
    )
    fix = "Put the distinctive words first and trim the title to about 60 characters."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag titles over the limit."""
        if len(page.title) > MAX_LENGTH:
            yield self.issue(page, f"{len(page.title)} characters")


class TooShort(HtmlPageRule):
    """Title too short to describe the page."""

    id = "title.too_short"
    severity = Severity.LOW
    category = CATEGORY
    summary = f"Title is shorter than {MIN_LENGTH} characters"
    why = (
        "Very short titles waste the space searchers use to judge a result, and "
        "rarely contain the phrases people search for."
    )
    fix = "Say what the page is and who it is for; the brand name can go at the end."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag non-empty titles under the limit."""
        if 0 < len(page.title) < MIN_LENGTH:
            yield self.issue(page, f"{len(page.title)} characters")


class Multiple(HtmlPageRule):
    """More than one ``<title>`` element."""

    id = "title.multiple"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Page has more than one <title> element"
    why = (
        "Which title search engines use is undefined; usually the first, sometimes "
        "the last. A second title normally means two templates or plugins are both "
        "writing the head."
    )
    fix = "Keep exactly one <title> in the <head>."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with two or more title elements."""
        if page.title_count > 1:
            yield self.issue(page, f"{page.title_count} <title> elements")


class SameAsH1(HtmlPageRule):
    """Title and first H1 identical."""

    id = "title.same_as_h1"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Title is identical to the H1"
    why = (
        "Not wrong, but a missed chance: the title is written for the results page "
        "and the H1 for the reader, so the two can carry different phrases."
    )
    fix = "Keep the H1 for readers and give the title the search phrase and context."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag a title that equals the H1 ignoring case."""
        if page.title and page.h1 and page.title.casefold() == page.h1.casefold():
            yield self.issue(page)
