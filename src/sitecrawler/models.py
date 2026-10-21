"""Typed records that cross module boundaries.

Nothing in this module does I/O. Every other package imports from here, so this
module must not import from any of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Outcome(StrEnum):
    """What happened when we tried to fetch a URL."""

    FETCHED = "fetched"
    """A response came back (any status code)."""

    BLOCKED = "blocked"
    """robots.txt disallowed the URL; no request was made."""

    ERROR = "error"
    """Network or protocol failure; no usable response."""


@dataclass(slots=True, frozen=True)
class CrawlConfig:
    """Everything that controls a crawl, in one immutable object."""

    start_url: str
    max_pages: int = 5000
    delay_seconds: float = 0.5
    workers: int = 4
    timeout_seconds: float = 20.0
    use_sitemap: bool = True
    keep_query: bool = False
    respect_robots: bool = True
    user_agent: str = "sitecrawler/0.1 (+https://github.com/joemachen/sitecrawler)"


@dataclass(slots=True, frozen=True)
class QueueItem:
    """A URL waiting to be fetched, with how we got there."""

    url: str
    depth: int
    found_on: str


@dataclass(slots=True, frozen=True)
class FetchResult:
    """Raw outcome of one HTTP request. No parsing has happened yet."""

    url: str
    outcome: Outcome
    status_code: int | None = None
    final_url: str = ""
    content_type: str = ""
    text: str = ""
    elapsed_ms: int = 0
    error: str = ""

    @property
    def is_html(self) -> bool:
        """True when the response is an HTML document we can parse."""
        return self.outcome is Outcome.FETCHED and "html" in self.content_type


@dataclass(slots=True)
class ParsedPage:
    """What the parser extracted from one HTML document."""

    title: str = ""
    meta_description: str = ""
    h1: str = ""
    canonical: str = ""
    word_count: int = 0
    links: list[str] = field(default_factory=list)
    """Absolute hrefs of every anchor, before any filtering."""


@dataclass(slots=True)
class PageRecord:
    """One row of crawl output: fetch result plus parsed fields plus provenance."""

    url: str
    outcome: Outcome
    depth: int
    found_on: str
    status_code: int | None = None
    title: str = ""
    meta_description: str = ""
    h1: str = ""
    canonical: str = ""
    content_type: str = ""
    internal_links: int = 0
    word_count: int = 0
    fetch_ms: int = 0
    error: str = ""

    @property
    def status(self) -> str:
        """Status code as text, or the outcome name when there was no response."""
        return str(self.status_code) if self.status_code is not None else self.outcome.value
