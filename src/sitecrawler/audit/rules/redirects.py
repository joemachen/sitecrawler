"""Redirect rules: chains, loops, bad targets, and links that go through redirects."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.rule import HtmlPageRule, PageRule
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, Outcome, PageRecord, RedirectHop, Severity

CATEGORY = "Redirects"
TEMPORARY = frozenset({302, 307})


def _chain(page: PageRecord) -> str:
    return " -> ".join([page.url, *(hop.to_url for hop in page.redirect_hops)])


def _real_hops(page: PageRecord, crawl: CrawlView) -> list[RedirectHop]:
    """Hops that move to a different page.

    A hop between two forms of the same URL (``/blog`` to ``/blog/``, ``www.``
    or not) is usually the server answering the crawler's normalised request,
    not something a visitor following the site's own links would see.
    """
    return [hop for hop in page.redirect_hops if not crawl.same_page(hop.from_url, hop.to_url)]


class Chain(PageRule):
    """More than one hop."""

    id = "redirect.chain"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Redirect chain of two or more hops"
    why = (
        "Every hop costs a round trip for users and crawlers, and each one leaks a "
        "little link equity. Google follows up to ten hops, but long chains slow "
        "crawling and are usually a sign of migrations layered on migrations."
    )
    fix = (
        "Point the first URL straight at the final destination, and update internal "
        "links to use the final URL."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag fetched pages with two or more hops between different pages."""
        if page.outcome is Outcome.FETCHED and len(_real_hops(page, crawl)) > 1:
            yield self.issue(page, f"{len(page.redirect_hops)} hops: {_chain(page)}")


class Loop(PageRule):
    """A chain that never resolves."""

    id = "redirect.loop"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "Redirect loop or chain that never resolves"
    why = (
        "The URL redirects back to itself (or past the hop limit), so neither users "
        "nor search engines ever reach a page. Browsers show an error and the URL "
        "drops out of the index."
    )
    fix = (
        "Find the rule that sends the final hop back to the start (often an HTTP to "
        "HTTPS rule fighting a trailing-slash rule) and make the chain end at a 200."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag ``Outcome.REDIRECT_LOOP``."""
        if page.outcome is Outcome.REDIRECT_LOOP:
            yield self.issue(page, page.error)


class ToError(PageRule):
    """Redirect whose destination is an error page."""

    id = "redirect.to_error"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "Redirect ends on a 4xx or 5xx page"
    why = (
        "A redirect promises a replacement page; landing on an error instead is worse "
        "than a plain 404 because it also wastes the hop. Search engines treat the "
        "chain as a dead end."
    )
    fix = (
        "Redirect to a live, relevant page, or remove the redirect and let the URL "
        "return 404 or 410 honestly."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag redirected pages whose final status is 4xx/5xx."""
        if page.redirect_hops and page.status_code is not None and page.status_code >= 400:
            yield self.issue(page, f"{page.status_code} at {page.final_url}")


class OffSite(PageRule):
    """Redirect that leaves the crawled site."""

    id = "redirect.off_site"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Internal URL redirects to another site"
    why = (
        "Internal links are sending visitors and link equity to a different domain. "
        "That is fine for a deliberate move, but a surprise when it comes from an old "
        "campaign URL, a hijacked plugin or a misconfigured rule."
    )
    fix = (
        "If the move is intended, update internal links to point at the new domain "
        "directly. Otherwise fix the redirect rule."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag fetched pages whose final URL is on another host."""
        if (
            page.outcome is Outcome.FETCHED
            and page.redirect_hops
            and page.final_url
            and not crawl.is_internal(page.final_url)
        ):
            yield self.issue(page, f"to {page.final_url}")


class Temporary(PageRule):
    """302/307 where a permanent redirect is expected."""

    id = "redirect.temporary"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Temporary redirect (302/307) used for a permanent move"
    why = (
        "A temporary redirect tells search engines to keep the old URL indexed and "
        "come back later. For a page that has moved for good, that delays the "
        "transfer of rankings to the new URL."
    )
    fix = (
        "Use 301 (or 308 to preserve the method) for permanent moves. Keep 302/307 "
        "only for genuinely temporary situations such as A/B tests or maintenance."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag chains ending on a live internal page that contain a 302 or 307 hop.

        Chains that end on an error, loop or another site have their own rules.
        """
        temporary = [hop for hop in _real_hops(page, crawl) if hop.status_code in TEMPORARY]
        if (
            page.outcome is Outcome.FETCHED
            and temporary
            and page.status_code is not None
            and 200 <= page.status_code < 300
            and crawl.is_internal(page.final_url)
        ):
            codes = ", ".join(str(hop.status_code) for hop in temporary)
            yield self.issue(page, f"{codes} in {_chain(page)}")


class LinksToRedirects(HtmlPageRule):
    """Internal links that point at redirecting URLs."""

    id = "link.to_redirect"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page links to URLs that redirect"
    why = (
        "Every click on such a link takes an extra round trip, and crawlers spend "
        "budget following the hop. Linking to the final URL is free to fix and "
        "removes the dependency on the redirect staying in place."
    )
    fix = "Change the href to the URL the redirect lands on."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with at least one internal link whose target redirects elsewhere."""
        redirecting: list[str] = []
        for link in page.links:
            target = crawl.page_for(link.href)
            if (
                target is not None
                and target.redirect_hops
                and target.final_url
                and not crawl.same_page(link.href, target.final_url)
                and link.href not in redirecting
            ):
                redirecting.append(link.href)
        if redirecting:
            more = f" and {len(redirecting) - 1} more" if len(redirecting) > 1 else ""
            yield self.issue(
                page, f"{len(redirecting)} link(s) redirect, e.g. {redirecting[0]}{more}"
            )
