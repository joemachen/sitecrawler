"""Duplicate content report: every exact group and near cluster, for printing.

The per-page findings are the three ``content.*`` rules; this module lists
the clusters themselves, with every member's indexability so the reader can
see which copies already canonicalise away (ADR-0012). ``sitecrawler
duplicates report`` prints it and ``audit`` prints its one-line summary.
"""

from __future__ import annotations

from dataclasses import dataclass

from sitecrawler.audit.duplicates import MIN_WORDS, NEAR_DUPLICATE_DISTANCE, Cluster, DuplicateIndex
from sitecrawler.audit.engine import indexability
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import PageRecord
from sitecrawler.parse.fingerprint import BITS


@dataclass(slots=True, frozen=True)
class DuplicateReport:
    """What the content fingerprints say about one crawl."""

    pages: int
    """Parsed HTML pages with any main text."""
    compared: int
    """Pages of ``min_words`` words or more, the pool near-duplicates are found in."""
    exact: tuple[Cluster, ...]
    """Groups of identical main text, any length, by representative URL."""
    near: tuple[Cluster, ...]
    """Clusters within ``max_distance`` bits that hold more than one distinct text."""
    low_content: int
    """Indexable HTML pages under ``min_words`` words."""
    max_distance: int
    min_words: int

    def summary(self) -> str:
        """One line for the audit output."""
        exact_pages = sum(len(c.members) for c in self.exact)
        near_pages = sum(len(c.members) for c in self.near)
        return (
            f"Duplicates: {self.pages} pages fingerprinted; {exact_pages} in "
            f"{len(self.exact)} group(s) of identical content; {near_pages} in "
            f"{len(self.near)} near-duplicate cluster(s) within {self.max_distance} of "
            f"{BITS} bits among the {self.compared} pages of {self.min_words}+ words; "
            f"{self.low_content} indexable page(s) under {self.min_words} words."
        )


def member_status(crawl: CrawlView, page: PageRecord) -> str:
    """``indexable``, or why the page is not."""
    verdict = indexability(page, crawl)
    return "indexable" if verdict.indexable else verdict.reason


def duplicate_report(crawl: CrawlView, max_distance: int | None = None) -> DuplicateReport:
    """Cluster the fingerprinted pages of ``crawl``.

    Args:
        crawl: The crawl to report on.
        max_distance: SimHash bits two near-duplicates may differ by; the
            audit's default when None. Any other value builds a fresh index.
    """
    index = (
        crawl.duplicates
        if max_distance is None or max_distance == NEAR_DUPLICATE_DISTANCE
        else DuplicateIndex(crawl, max_distance)
    )
    near = tuple(c for c in index.near if len({_hash(p) for p in c.members}) > 1)
    low_content = sum(
        1
        for p in crawl.html_pages
        if p.fingerprint is not None
        and p.fingerprint.words < MIN_WORDS
        and indexability(p, crawl).indexable
    )
    return DuplicateReport(
        pages=len(index.pages),
        compared=sum(1 for p in index.pages if p.fingerprint and p.fingerprint.words >= MIN_WORDS),
        exact=index.exact,
        near=near,
        low_content=low_content,
        max_distance=index.max_distance,
        min_words=index.min_words,
    )


def _hash(page: PageRecord) -> str:
    return page.fingerprint.content_hash if page.fingerprint else ""
