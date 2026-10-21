"""The ``Rule`` base classes every audit check is built on."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import ClassVar

from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity


class Rule(ABC):
    """One audit check. Subclasses set the class attributes and implement :meth:`check`.

    The attributes double as documentation: the user guide page for every rule
    is generated from them, so write ``summary``, ``why`` and ``fix`` for the
    person who has to act on the finding.
    """

    id: ClassVar[str]
    """Stable identifier such as ``title.missing``; the ``issues`` table key."""
    severity: ClassVar[Severity]
    category: ClassVar[str]
    """Heading in the Issues report: ``Titles``, ``Redirects``, ..."""
    summary: ClassVar[str]
    """One line, shown next to the count."""
    why: ClassVar[str]
    """A short paragraph: why search engines or users care."""
    fix: ClassVar[str]
    """What to do about it."""

    @abstractmethod
    def check(self, crawl: CrawlView) -> Iterable[Issue]:
        """Yield one issue per affected URL."""

    def issue(self, page: PageRecord, message: str = "") -> Issue:
        """Build an issue on ``page`` with this rule's id and severity."""
        return Issue(page.url, self.id, self.severity, message)


class PageRule(Rule):
    """A rule that looks at one page at a time (most of them)."""

    def check(self, crawl: CrawlView) -> Iterable[Issue]:
        """Run :meth:`check_page` over every fetched page."""
        for page in crawl.pages:
            yield from self.check_page(page, crawl)

    @abstractmethod
    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Yield the issues this page has (usually zero or one)."""


class HtmlPageRule(PageRule):
    """A page rule that only applies to pages whose HTML was parsed."""

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Skip pages that were not fetched as HTML with a 2xx/3xx status."""
        if crawl.is_html_page(page):
            yield from self.check_html(page, crawl)

    @abstractmethod
    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Yield the issues this HTML page has."""
