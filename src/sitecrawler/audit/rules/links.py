"""Internal linking rules: broken and nofollow links, weak or deep pages, poor anchors.

Every rule reads the link graph the audit builds once per crawl
(``crawl.link_graph``, ADR-0011). ``link.to_redirect`` lives with the
redirect rules; the whole-crawl report of broken and redirecting links with
their anchors is ``sitecrawler links report``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from sitecrawler.audit.engine import indexability
from sitecrawler.audit.graph import is_broken
from sitecrawler.audit.rule import HtmlPageRule
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Links"

FEW_INLINKS = 1
"""``link.few_inlinks`` fires on pages with this many follow inlinks or fewer."""

MAX_DEPTH = 3
"""``link.high_depth`` fires on pages more than this many clicks from the start page."""

MAX_OUTLINKS = 300
"""``link.too_many_outlinks`` fires on pages with more anchors than this."""

GENERIC_ANCHORS = frozenset(
    {
        "click here", "here", "click", "this", "this page", "this link", "this article",
        "link", "page", "read more", "more", "more info", "more information", "info",
        "learn more", "see more", "view", "view more", "view all", "details", "continue",
        "continue reading", "go", "start", "website", "homepage", "home page",
    }
)  # fmt: skip
"""Anchor texts that say nothing about the target, compared case-insensitively
without punctuation."""

_PUNCTUATION = re.compile(r"[^\w\s]+", re.UNICODE)


def is_generic(text: str) -> bool:
    """True when ``text`` is one of :data:`GENERIC_ANCHORS`, ignoring case and punctuation."""
    cleaned = " ".join(_PUNCTUATION.sub(" ", text).lower().split())
    return cleaned in GENERIC_ANCHORS


def _more(count: int) -> str:
    return f" and {count - 1} more" if count > 1 else ""


class ToError(HtmlPageRule):
    """Links to pages that do not resolve."""

    id = "link.to_error"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Page links to URLs that return an error"
    why = (
        "A link to a 4xx or 5xx page, a URL that could not be fetched or a redirect "
        "that never resolves sends users to a dead end and spends crawl budget and "
        "link equity on nothing. The error itself is reported on the target by the "
        "response and redirect rules; this rule names the pages that need their "
        "links changed."
    )
    fix = (
        "Point the link at a live page or remove it. `sitecrawler links report` "
        "lists every such link with its anchor text."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with an internal link to a broken target, naming the first."""
        broken: dict[str, str] = {}
        for link in page.links:
            target = crawl.page_for(link.href)
            if target is None or target is page or not is_broken(target):
                continue
            broken.setdefault(target.url, f"{link.href} ({target.status})")
        if broken:
            first = next(iter(broken.values()))
            yield self.issue(
                page, f"{len(broken)} link(s) to errors, e.g. {first}{_more(len(broken))}"
            )


class FewInlinks(HtmlPageRule):
    """Indexable pages the site barely links to."""

    id = "link.few_inlinks"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Indexable page has one follow inlink or none"
    why = (
        "Internal links are how search engines judge which pages matter and how "
        "users move around. A page reachable from a single other page (or from "
        "none, when only a sitemap or a nofollow link points at it) gets little "
        "equity and is one broken link away from being an orphan. Links from the "
        "page to itself and nofollow links do not count."
    )
    fix = (
        "Link to the page from a relevant hub, a category or the navigation; "
        "if it does not deserve that, ask whether it should be indexable at all."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag indexable pages (other than the start page) with at most one follow inlink."""
        if page.found_on == "start" or not indexability(page, crawl).indexable:
            return
        sources = crawl.link_graph.follow_sources(page.url)
        if len(sources) > FEW_INLINKS:
            return
        detail = f"1 follow inlink, from {sources[0]}" if sources else "no follow inlinks"
        yield self.issue(page, detail)


class HighDepth(HtmlPageRule):
    """Pages many clicks from the start page."""

    id = "link.high_depth"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Indexable page is more than 3 clicks from the start page"
    why = (
        "The fewer clicks from the home page, the more often a page is crawled and "
        "the more equity reaches it. Pages four or more clicks deep are typically "
        "old posts and paginated tails that only a sitemap or a deep link keeps "
        "alive. This is the shortest path over internal links, not the order the "
        "crawler happened to find pages in."
    )
    fix = (
        "Link to the page from somewhere closer to the home page: a hub, related "
        "links on popular pages, or a flatter category structure."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag indexable pages whose click depth is above :data:`MAX_DEPTH`."""
        depth = crawl.link_graph.metrics[page.url].link_depth
        if depth is None or depth <= MAX_DEPTH:
            return
        if indexability(page, crawl).indexable:
            yield self.issue(page, f"{depth} clicks from the start page")


class GenericAnchor(HtmlPageRule):
    """Links whose text says nothing about the target."""

    id = "link.generic_anchor"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Internal links use generic anchor text such as “click here”"
    why = (
        "Anchor text tells search engines and screen-reader users what the linked "
        "page is about. “Click here”, “read more” and “this page” "
        "describe the act of clicking, not the destination, so the link passes "
        "no topical signal and reads badly out of context."
    )
    fix = (
        "Rewrite the anchor to name the destination: “see the pricing page” "
        "rather than “click here to see pricing”. Only internal links are counted."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with internal links whose anchor text is in :data:`GENERIC_ANCHORS`."""
        generic: dict[tuple[str, str], str] = {}
        for link in page.links:
            if crawl.is_internal(link.href) and is_generic(link.text):
                generic.setdefault((link.text, link.href), f"“{link.text}” to {link.href}")
        if generic:
            first = next(iter(generic.values()))
            yield self.issue(
                page, f"{len(generic)} generic anchor(s), e.g. {first}{_more(len(generic))}"
            )


class NofollowInternal(HtmlPageRule):
    """Internal links marked nofollow."""

    id = "link.nofollow_internal"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page has internal links with rel=nofollow"
    why = (
        "nofollow tells search engines not to pass equity through the link and is "
        "meant for links you do not vouch for. On your own site it throws equity "
        "away without keeping the target out of the index; the target still gets "
        "crawled through other links or the sitemap. It is almost always a leftover "
        "from a plugin or an old attempt at sculpting PageRank."
    )
    fix = (
        "Remove rel=nofollow from internal links. To keep a page out of search, use "
        "noindex on the page itself."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with at least one internal ``rel=nofollow`` link."""
        nofollow: list[str] = []
        for link in page.links:
            if link.nofollow and crawl.is_internal(link.href) and link.href not in nofollow:
                nofollow.append(link.href)
        if nofollow:
            yield self.issue(
                page,
                f"{len(nofollow)} nofollow link(s), e.g. to {nofollow[0]}{_more(len(nofollow))}",
            )


class TooManyOutlinks(HtmlPageRule):
    """Pages with an excessive number of links."""

    id = "link.too_many_outlinks"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page has more than 300 links"
    why = (
        "Every link on a page shares the equity the page can pass, so a page with "
        "hundreds of links gives each one very little, and a page that is mostly "
        "links is hard to use. Mega-menus, tag clouds and unpaginated listings are "
        "the usual causes. Internal and external anchors both count."
    )
    fix = (
        "Trim the navigation to what the page's visitors need, paginate long "
        "listings, and move exhaustive link lists to a dedicated index page."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with more than :data:`MAX_OUTLINKS` anchors."""
        if len(page.links) > MAX_OUTLINKS:
            yield self.issue(page, f"{len(page.links)} links on the page")
