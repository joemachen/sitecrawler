"""Canonical tag rules."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.rule import HtmlPageRule
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Canonicals"


def effective_canonical(page: PageRecord) -> str:
    """The canonical search engines will use: the ``Link`` header wins over the HTML tag."""
    return page.canonical_header or page.canonical


class Missing(HtmlPageRule):
    """No canonical at all."""

    id = "canonical.missing"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page declares no canonical URL"
    why = (
        "Without a canonical, search engines pick which of a page's URL variants "
        "(trailing slash, query strings, http/https, www) to index, and may split "
        "signals across several. A self-referencing canonical settles it."
    )
    fix = 'Add <link rel="canonical" href="..."> pointing at the page\'s preferred URL.'

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with neither an HTML nor a header canonical."""
        if not effective_canonical(page):
            yield self.issue(page)


class ToNon200(HtmlPageRule):
    """Canonical pointing at a page that does not return 200."""

    id = "canonical.to_non_200"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "Canonical points at a URL that is not a 200 page"
    why = (
        "A canonical is a request to index a different URL instead of this one. If "
        "that URL is missing, errors or redirects, the request is ignored at best, "
        "and at worst this page drops out while nothing replaces it."
    )
    fix = "Point the canonical at a URL that returns 200 directly (no redirect)."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag canonicals whose crawled target is not a plain 200."""
        canonical = effective_canonical(page)
        if not canonical or crawl.same_page(canonical, page.url):
            return
        target = crawl.page_for(canonical)
        if target is None:
            return  # not crawled, cannot judge
        redirected = target.final_url and not crawl.same_page(target.final_url, target.url)
        if target.status_code != 200 or redirected:
            yield self.issue(page, f"{canonical} returns {target.status}")


class OffSite(HtmlPageRule):
    """Canonical on another host."""

    id = "canonical.off_site"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Canonical points at another site"
    why = (
        "A cross-domain canonical hands this page's ranking to the other site. That "
        "is right for syndicated content and wrong for almost everything else, "
        "including staging sites that kept the production canonical."
    )
    fix = (
        "Unless the content is deliberately syndicated, point the canonical at this site's own URL."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag canonicals whose host is not one of the crawl's hosts."""
        canonical = effective_canonical(page)
        if canonical and not crawl.is_internal(canonical):
            yield self.issue(page, f"to {canonical}")


class Chain(HtmlPageRule):
    """Canonical whose target canonicalises somewhere else again."""

    id = "canonical.chain"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Canonical target has a different canonical of its own"
    why = (
        "Search engines do not follow canonical chains reliably; the signal may stop "
        "at the first hop or be ignored altogether."
    )
    fix = "Point every page in the group straight at the final canonical URL."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag canonicals whose target page canonicalises to a third URL."""
        canonical = effective_canonical(page)
        if not canonical or crawl.same_page(canonical, page.url):
            return
        target = crawl.page_for(canonical)
        if target is None:
            return
        next_hop = effective_canonical(target)
        if next_hop and not crawl.same_page(next_hop, target.url):
            yield self.issue(page, f"{canonical} canonicalises to {next_hop}")


class CanonicalisedButLinked(HtmlPageRule):
    """A page that defers to another URL yet is linked internally."""

    id = "canonical.canonicalised_but_linked"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Internal links point at a page that canonicalises elsewhere"
    why = (
        "Links are sending users and crawlers to a URL the site itself says is "
        "not the one to index. Linking to the canonical URL instead keeps the "
        "signals in one place."
    )
    fix = "Update internal links to the canonical URL."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with a non-self canonical and at least one inlink."""
        canonical = effective_canonical(page)
        if canonical and not crawl.same_page(canonical, page.url):
            sources = crawl.inlinks_to(page.url)
            if sources:
                yield self.issue(page, f"canonical {canonical}; linked from {sources[0].src}")


class NotSelfReferencing(HtmlPageRule):
    """Canonical that points elsewhere (informational)."""

    id = "canonical.not_self_referencing"
    severity = Severity.INFO
    category = CATEGORY
    summary = "Canonical points at a different URL"
    why = (
        "Not a problem by itself: this is how duplicates are meant to be handled. "
        "Listed so you can confirm every one of these is intentional."
    )
    fix = "Check the list; if a page should rank on its own, make its canonical self-referencing."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag canonicals that are not the page's own URL."""
        canonical = effective_canonical(page)
        if canonical and not crawl.same_page(canonical, page.url):
            yield self.issue(page, f"to {canonical}")


class OgUrlMismatch(HtmlPageRule):
    """``og:url`` disagrees with the canonical."""

    id = "canonical.og_url_mismatch"
    severity = Severity.LOW
    category = CATEGORY
    summary = "og:url differs from the canonical"
    why = (
        "Social networks treat og:url as the page's identity, search engines use the "
        "canonical. When they disagree, shares and links accumulate on two URLs."
    )
    fix = "Set og:url to the same URL as the canonical."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages whose og:url and canonical are different pages."""
        canonical = effective_canonical(page)
        if page.og_url and canonical and not crawl.same_page(page.og_url, canonical):
            yield self.issue(page, f"og:url {page.og_url} vs canonical {canonical}")


class Conflict(HtmlPageRule):
    """HTML and header canonicals disagree."""

    id = "canonical.conflict"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "HTML canonical and Link header canonical disagree"
    why = (
        "Two canonicals for one page is a contradiction search engines resolve by "
        "ignoring both. It usually means a CDN or framework adds a header the "
        "template does not know about."
    )
    fix = "Remove one of them, or make both say the same URL."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with both canonicals set to different pages."""
        if (
            page.canonical
            and page.canonical_header
            and not crawl.same_page(page.canonical, page.canonical_header)
        ):
            yield self.issue(page, f"html {page.canonical} vs header {page.canonical_header}")
