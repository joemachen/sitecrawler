"""Meta description rules."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.rule import HtmlPageRule, Rule
from sitecrawler.audit.rules._common import describe_group
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Meta descriptions"
MAX_LENGTH = 155
MIN_LENGTH = 70


class Missing(HtmlPageRule):
    """No meta description."""

    id = "meta_description.missing"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Page has no meta description"
    why = (
        "The description is the snippet under the title in search results. Without "
        "one Google picks a sentence from the page, which is often a menu or a "
        "cookie notice, and the result gets fewer clicks."
    )
    fix = "Write one or two sentences (70 to 155 characters) that say why to click."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag an empty description."""
        if not page.meta_description:
            yield self.issue(page)


class Duplicate(Rule):
    """Same description on several pages."""

    id = "meta_description.duplicate"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Meta description is shared with other pages"
    why = (
        "A description reused across pages is ignored by Google in favour of page "
        "text, and it tells searchers nothing about which result to pick."
    )
    fix = "Describe each page specifically, or leave the description out on thin pages."

    def check(self, crawl: CrawlView) -> Iterable[Issue]:
        """Flag every member of a group sharing a description."""
        for group in crawl.group_html_pages(lambda p: p.meta_description.casefold()).values():
            if len(group) > 1:
                for page in group:
                    yield self.issue(page, describe_group(page, group))


class TooLong(HtmlPageRule):
    """Description likely to be truncated."""

    id = "meta_description.too_long"
    severity = Severity.LOW
    category = CATEGORY
    summary = f"Meta description is longer than {MAX_LENGTH} characters"
    why = "Snippets are cut at about 155 characters on desktop and less on mobile."
    fix = "Front-load the message and trim to about 155 characters."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag descriptions over the limit."""
        if len(page.meta_description) > MAX_LENGTH:
            yield self.issue(page, f"{len(page.meta_description)} characters")


class TooShort(HtmlPageRule):
    """Description too short to be useful."""

    id = "meta_description.too_short"
    severity = Severity.LOW
    category = CATEGORY
    summary = f"Meta description is shorter than {MIN_LENGTH} characters"
    why = "A few words do not earn a click, and Google will usually replace them."
    fix = "Use the room: one or two full sentences that promise what the page delivers."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag non-empty descriptions under the limit."""
        if 0 < len(page.meta_description) < MIN_LENGTH:
            yield self.issue(page, f"{len(page.meta_description)} characters")


class Multiple(HtmlPageRule):
    """More than one description meta tag."""

    id = "meta_description.multiple"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page has more than one meta description"
    why = (
        "Two descriptions usually mean two plugins or templates writing the head; "
        "which one search engines use is undefined."
    )
    fix = 'Keep one <meta name="description">.'

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with two or more description metas."""
        if page.meta_description_count > 1:
            yield self.issue(page, f"{page.meta_description_count} description tags")
