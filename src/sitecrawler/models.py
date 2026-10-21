"""Typed records that cross module boundaries.

Nothing in this module does I/O. Every other package imports from here, so this
module must not import from any of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Outcome(StrEnum):
    """What happened when we tried to fetch a URL."""

    FETCHED = "fetched"
    """A response came back (any status code)."""

    BLOCKED = "blocked"
    """robots.txt disallowed the URL; no request was made."""

    ERROR = "error"
    """Network or protocol failure; no usable response."""

    REDIRECT_LOOP = "redirect_loop"
    """Redirects never resolved: a cycle, or more than ``max_redirects`` hops."""


@dataclass(slots=True, frozen=True)
class CrawlConfig:
    """Everything that controls a crawl, in one immutable object."""

    start_url: str = ""
    """Where a site crawl starts. Leave empty and set ``seed_urls`` for list mode."""
    max_pages: int = 5000
    delay_seconds: float = 0.5
    workers: int = 4
    timeout_seconds: float = 20.0
    use_sitemap: bool = True
    keep_query: bool = False
    respect_robots: bool = True
    user_agent: str = "sitecrawler/0.3 (+https://github.com/joemachen/sitecrawler)"
    max_redirects: int = 10
    """Give up on a redirect chain longer than this and report ``redirect_loop``."""
    http2: bool = True
    """Negotiate HTTP/2 when the server offers it (HTTPS only)."""
    seed_urls: tuple[str, ...] = ()
    """List mode: fetch exactly these URLs instead of spidering from ``start_url``."""
    follow_links: bool = True
    """Queue the links found on each page. Off by default in list mode (see CLI)."""


@dataclass(slots=True, frozen=True)
class RedirectHop:
    """One step of a redirect chain, as the server sent it."""

    hop_no: int
    """1-based position in the chain."""
    from_url: str
    to_url: str
    """Absolute target, resolved against ``from_url``."""
    status_code: int


@dataclass(slots=True, frozen=True)
class QueueItem:
    """A URL waiting to be fetched, with how we got there."""

    url: str
    depth: int
    found_on: str


@dataclass(slots=True, frozen=True)
class ResumeState:
    """What a store hands back so an interrupted crawl can carry on."""

    seen: frozenset[str] = frozenset()
    """Every URL already queued or fetched; the frontier must not re-add these."""
    pending: tuple[QueueItem, ...] = ()
    """URLs queued but not yet fetched, in queue order."""
    done: int = 0
    """Pages already fetched, so ``max_pages`` counts across runs."""


class Severity(StrEnum):
    """How much an issue matters; the Issues report is sorted by this."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        """0 for CRITICAL up to 4 for INFO, for sorting."""
        return list(Severity).index(self)


@dataclass(slots=True, frozen=True)
class Issue:
    """One audit finding on one URL."""

    url: str
    rule_id: str
    severity: Severity
    message: str = ""
    """Detail for this URL (the duplicate's partner, the hop count, ...)."""


@dataclass(slots=True, frozen=True)
class Indexability:
    """Whether a page can appear in search results, and if not, why."""

    indexable: bool
    reason: str = ""


@dataclass(slots=True, frozen=True)
class HreflangRef:
    """One ``<link rel="alternate" hreflang=...>`` entry."""

    lang: str
    href: str


@dataclass(slots=True, frozen=True)
class CrawlInfo:
    """Summary of a stored crawl, as read back from a store."""

    start_url: str
    mode: str
    version: str
    status: str
    """``running``, ``done`` (frontier exhausted) or ``stopped`` (hit ``max_pages``)."""
    pages_done: int
    started_at: datetime
    finished_at: datetime | None = None
    config_json: str = ""


@dataclass(slots=True, frozen=True)
class LinkRef:
    """One anchor on a page."""

    href: str
    """Absolute target URL, before any normalisation."""
    text: str = ""
    rel: str = ""

    @property
    def nofollow(self) -> bool:
        """True when ``rel`` contains ``nofollow``."""
        return "nofollow" in self.rel.lower().split()


@dataclass(slots=True, frozen=True)
class FetchResult:
    """Raw outcome of one HTTP request. No parsing has happened yet."""

    url: str
    outcome: Outcome
    status_code: int | None = None
    final_url: str = ""
    content_type: str = ""
    text: str = ""
    """Decoded body, only when the response is HTML."""
    content: bytes = b""
    """Raw body of the final response, whatever its type."""
    headers: dict[str, str] = field(default_factory=dict)
    """Response headers of the final response, keys lower-cased."""
    size_bytes: int = 0
    elapsed_ms: int = 0
    """Wall time for the whole chain, redirects included."""
    error: str = ""
    hops: tuple[RedirectHop, ...] = ()
    """Every redirect followed before the final response, in order."""

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
    """First H1, for the CSV; ``h1s`` has them all."""
    canonical: str = ""
    word_count: int = 0
    links: list[str] = field(default_factory=list)
    """Absolute hrefs of every anchor, before any filtering."""
    anchors: list[LinkRef] = field(default_factory=list)
    """The same anchors with their text and ``rel``."""
    h1s: list[str] = field(default_factory=list)
    h2s: list[str] = field(default_factory=list)
    meta_robots: str = ""
    """Content of ``<meta name="robots">``, if present."""
    lang: str = ""
    """``<html lang>`` attribute, if present."""
    title_count: int = 0
    meta_description_count: int = 0
    og_url: str = ""
    hreflang: list[HreflangRef] = field(default_factory=list)
    rel_prev: str = ""
    rel_next: str = ""


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
    final_url: str = ""
    """Where the request ended up after redirects; empty when there was no response."""
    size_bytes: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    redirect_hops: tuple[RedirectHop, ...] = ()
    links: tuple[LinkRef, ...] = ()
    """Every anchor on the page, unfiltered."""
    h1s: tuple[str, ...] = ()
    h2s: tuple[str, ...] = ()
    meta_robots: str = ""
    lang: str = ""
    title_count: int = 0
    meta_description_count: int = 0
    og_url: str = ""
    canonical_header: str = ""
    """Canonical declared in the HTTP ``Link`` header, if any."""
    hreflang: tuple[HreflangRef, ...] = ()
    rel_prev: str = ""
    rel_next: str = ""

    @property
    def status(self) -> str:
        """Status code as text, or the outcome name when there was no response."""
        return self.status_text(self.status_code, self.outcome.value)

    @staticmethod
    def status_text(status_code: int | None, outcome: str) -> str:
        """The rule behind :attr:`status`, shared with the store's export views."""
        return str(status_code) if status_code is not None else outcome
