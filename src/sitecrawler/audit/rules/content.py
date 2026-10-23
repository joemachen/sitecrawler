"""Content rules: pages that repeat each other, and pages with too little to say.

All three read the crawl's duplicate index (``crawl.duplicates``, ADR-0012),
built from the content fingerprints the crawl computed. Only indexable pages
are flagged: a copy that canonicalises to the original, or is noindex, is
already doing the right thing, and the indexability verdict says so.
"""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.duplicates import MIN_WORDS, NEAR_DUPLICATE_DISTANCE, DuplicateIndex
from sitecrawler.audit.engine import indexability
from sitecrawler.audit.rule import HtmlPageRule, Rule
from sitecrawler.audit.rules._common import describe_group
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity
from sitecrawler.parse.fingerprint import BITS

CATEGORY = "Content"


def _indexable(pages: Iterable[PageRecord], crawl: CrawlView) -> list[PageRecord]:
    return [p for p in pages if indexability(p, crawl).indexable]


def is_low_content(page: PageRecord, crawl: CrawlView, floor: int = MIN_WORDS) -> bool:
    """True for an indexable page whose fingerprint has fewer than ``floor`` main-text words.

    Shared by ``content.low_word_count`` and the duplicate report, so the
    two count the same pages.
    """
    fingerprint = page.fingerprint
    if fingerprint is None or fingerprint.words >= floor:
        return False
    return indexability(page, crawl).indexable


class Duplicate(Rule):
    """The same main text on more than one indexable page."""

    id = "content.duplicate"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "Page content is identical to other indexable pages"
    why = (
        "Two indexable pages with the same main text (boilerplate such as menus and "
        "footers aside) compete with each other: search engines pick one to show, "
        "split the links between them, and may demote both. A copy that "
        "canonicalises to the original, redirects, or is noindex is not reported, "
        "because it has already told search engines which page to keep."
    )
    fix = (
        "Keep one URL and canonicalise or 301-redirect the others to it. If the "
        "pages must both exist, give them different content."
    )

    def check(self, crawl: CrawlView) -> Iterable[Issue]:
        """Flag every indexable member of an exact group with another indexable member."""
        for cluster in crawl.duplicates.exact:
            group = _indexable(cluster.members, crawl)
            if len(group) > 1:
                for page in group:
                    yield self.issue(page, describe_group(page, group))


class NearDuplicate(Rule):
    """Nearly the same main text on more than one indexable page."""

    id = "content.near_duplicate"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Page content is nearly identical to other indexable pages"
    why = (
        "Pages that share most of their text, such as a product page per colour, a "
        "city page per city or an article published twice with a different "
        f"introduction, are treated much like exact duplicates. Pages of {MIN_WORDS} "
        "words or more are compared by SimHash; within "
        f"{NEAR_DUPLICATE_DISTANCE} of {BITS} bits (roughly nine tenths of the text in "
        "common) they are near-duplicates. The message names the closest page. "
        "Shorter pages are reported by content.low_word_count instead."
    )
    fix = (
        "Merge the pages or canonicalise the variants to one of them; if each must "
        "rank on its own, write content that is specific to it."
    )

    def check(self, crawl: CrawlView) -> Iterable[Issue]:
        """Flag indexable cluster members that have an indexable near (not exact) partner."""
        index = crawl.duplicates
        for cluster in index.near:
            group = _indexable(cluster.members, crawl)
            for page in group:
                partners = [q for q in group if not DuplicateIndex.same_text(page, q)]
                if not partners:
                    continue
                nearest = min(partners, key=lambda q: (index.distance(page, q), q.url))
                more = f" and {len(partners) - 1} more" if len(partners) > 1 else ""
                yield self.issue(
                    page,
                    f"nearly the same as {nearest.url} "
                    f"({index.distance(page, nearest)} of {BITS} bits differ){more}",
                )


class LowWordCount(HtmlPageRule):
    """Too little main text."""

    id = "content.low_word_count"
    severity = Severity.LOW
    category = CATEGORY
    summary = f"Page has fewer than {MIN_WORDS} words of main content"
    why = (
        "The count is of the page's main text: the body with menus, headers, "
        "footers, sidebars and scripts removed. A page with little of its own to say "
        "is hard to rank, and many of them together read to search engines as thin "
        "content across the site. Non-indexable pages are not reported."
    )
    fix = (
        "Write the content the page is meant to rank for, or merge it into a page "
        "that has it. If the page is a stub, deliberately, noindex it."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag indexable pages under the floor, with the count."""
        if page.fingerprint is not None and is_low_content(page, crawl):
            yield self.issue(page, f"{page.fingerprint.words} words")
