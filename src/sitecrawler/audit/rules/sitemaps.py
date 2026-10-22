"""Sitemap rules: does the XML sitemap match the site the crawl found?

Every rule compares the sitemap entries, normalised the crawl's way, with the
crawled pages and their indexability verdict (ADR-0010). Facts about the
sitemap files themselves (unreadable files, entries on other hosts) are not
issues; ``sitecrawler sitemap report`` prints them.
"""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.engine import indexability
from sitecrawler.audit.rule import HtmlPageRule, PageRule
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Sitemaps"


def _files(crawl: CrawlView, page: PageRecord) -> str:
    """``sitemap.xml, sitemap-2.xml``: the files that list ``page``, shortest form."""
    names: list[str] = []
    for entry in crawl.sitemap_listings_for(page.url):
        name = entry.sitemap_url.rsplit("/", 1)[-1] or entry.sitemap_url
        if name and name not in names:
            names.append(name)
    return ", ".join(names) or "a sitemap"


class Orphan(HtmlPageRule):
    """A sitemap page nothing links to."""

    id = "sitemap.orphan"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Sitemap page has no internal links pointing to it"
    why = (
        "The page is indexable and the sitemap lists it, but no other page on the "
        "site links to it, so the sitemap is the only way in. Search engines treat "
        "a page nothing links to as unimportant, and users cannot reach it at all. "
        "Non-indexable orphans are listed by sitemap.non_indexable instead, since "
        "linking to them would not help."
    )
    fix = (
        "Link to the page from a relevant page, a category page or the navigation; "
        "if nothing should link to it, it probably should not be in the sitemap either."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag indexable sitemap pages with no inlink from another page."""
        if page.found_on == "start" or not crawl.listed_in_sitemap(page.url):
            return
        if not indexability(page, crawl).indexable:
            return
        if any(not crawl.same_page(i.src, page.url) for i in crawl.inlinks_to(page.url)):
            return
        yield self.issue(page, f"listed in {_files(crawl, page)}, linked from nowhere")


class NonIndexable(PageRule):
    """A sitemap entry search engines cannot index."""

    id = "sitemap.non_indexable"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Non-indexable page is listed in the sitemap"
    why = (
        "A sitemap should list only canonical, indexable, 200 pages. An entry that "
        "redirects, errors, is blocked by robots.txt, is noindex or canonicalises "
        "elsewhere wastes crawl budget and makes search engines trust the sitemap "
        "less. The message says which of these it is."
    )
    fix = (
        "Remove the entry, or fix the page so it is indexable: for a redirect list "
        "the target, for a canonicalised page list the canonical."
    )

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag sitemap pages whose verdict is not indexable, with the reason."""
        if not crawl.listed_in_sitemap(page.url):
            return
        verdict = indexability(page, crawl)
        if not verdict.indexable:
            yield self.issue(page, verdict.reason)


class Missing(HtmlPageRule):
    """An indexable page the sitemap does not know about."""

    id = "sitemap.missing"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Indexable page is missing from the sitemap"
    why = (
        "The page returns 200, is indexable and is linked, but no sitemap lists it. "
        "Search engines will still find it through links; the sitemap just stops "
        "being the complete inventory it is meant to be, and lastmod hints are lost. "
        "Reported only when the crawl read at least one sitemap."
    )
    fix = (
        "Add the page to the sitemap, or regenerate it from this crawl with "
        "`sitecrawler sitemap generate`."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag indexable 200 pages absent from every sitemap, once a sitemap was read."""
        if not crawl.sitemap_entries or page.status_code != 200:
            return
        if crawl.listed_in_sitemap(page.url) or not indexability(page, crawl).indexable:
            return
        yield self.issue(page)


class Duplicate(PageRule):
    """A page listed more than once."""

    id = "sitemap.duplicate"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page is listed more than once across the sitemaps"
    why = (
        "The same page appears twice, in two sitemap files or twice in one, "
        "sometimes as two spellings of one URL. Harmless to rankings, but a sign "
        "that the sitemaps are generated by more than one process, and the "
        "duplicates inflate every count you read off them."
    )
    fix = "Generate each URL into exactly one sitemap file, in its canonical form."

    def check_page(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with more than one sitemap entry."""
        listings = crawl.sitemap_listings_for(page.url)
        if len(listings) > 1:
            yield self.issue(page, f"listed {len(listings)} times: {_files(crawl, page)}")
