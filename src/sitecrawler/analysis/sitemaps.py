"""Sitemap-versus-crawl report: the facts about sitemap files that are not page issues.

Per-page findings (orphans, non-indexable entries, missing pages, duplicates)
are audit rules in :mod:`sitecrawler.audit.rules.sitemaps`; this module
covers what belongs to the files: which were read, which could not be,
entries on other hosts and entries the crawl never fetched (ADR-0010).
"""

from __future__ import annotations

from dataclasses import dataclass

from sitecrawler.audit.view import CrawlView
from sitecrawler.models import SitemapEntry, SitemapFile


@dataclass(slots=True, frozen=True)
class SitemapReport:
    """What the crawl found when it read the site's sitemaps."""

    files: tuple[SitemapFile, ...]
    """Every sitemap or index the crawl tried, in the order it tried them."""
    entries: int
    """``<url>`` entries across every usable sitemap, duplicates included."""
    pages_listed: int
    """Distinct pages those entries name, after normalisation."""
    other_host: tuple[SitemapEntry, ...]
    """Entries on hosts the crawl did not cover; never fetched."""
    not_crawled: tuple[SitemapEntry, ...]
    """On-site entries with no page row: beyond ``max_pages``, or not page-like URLs."""
    duplicates: dict[str, tuple[SitemapEntry, ...]]
    """Normalised URL to its entries, for every URL listed more than once."""

    @property
    def readable(self) -> tuple[SitemapFile, ...]:
        """Files that parsed as a sitemap or index."""
        return tuple(f for f in self.files if f.ok)

    @property
    def unreadable(self) -> tuple[SitemapFile, ...]:
        """Files that could not be fetched or were not sitemap XML."""
        return tuple(f for f in self.files if not f.ok)

    @property
    def found(self) -> bool:
        """True when at least one sitemap file parsed."""
        return bool(self.readable)

    def summary(self) -> str:
        """One line for the audit output."""
        if not self.files:
            return "Sitemaps: none read (crawl ran with --no-sitemap, or an older file)."
        if not self.found:
            return (
                f"Sitemaps: none found ({len(self.unreadable)} tried: "
                f"{', '.join(f.url for f in self.unreadable)})."
            )
        parts = [
            f"Sitemaps: {len(self.readable)} file(s) read, {self.entries} entries naming "
            f"{self.pages_listed} pages"
        ]
        if self.unreadable:
            parts.append(f"{len(self.unreadable)} file(s) unreadable")
        if self.other_host:
            parts.append(f"{len(self.other_host)} on other hosts")
        if self.not_crawled:
            parts.append(f"{len(self.not_crawled)} not crawled")
        if self.duplicates:
            parts.append(f"{len(self.duplicates)} listed more than once")
        return "; ".join(parts) + "."


def sitemap_report(crawl: CrawlView) -> SitemapReport:
    """Compare the sitemap files and entries in ``crawl`` with the pages it fetched."""
    other_host: list[SitemapEntry] = []
    not_crawled: list[SitemapEntry] = []
    for entry in crawl.sitemap_entries:
        if not crawl.is_internal(entry.loc):
            other_host.append(entry)
        elif crawl.page_for(entry.loc) is None:
            not_crawled.append(entry)
    duplicates = {
        key: tuple(entries)
        for key, entries in sorted(crawl.sitemap_listings.items())
        if len(entries) > 1
    }
    return SitemapReport(
        files=tuple(crawl.sitemap_files),
        entries=len(crawl.sitemap_entries),
        pages_listed=len(crawl.sitemap_listings),
        other_host=tuple(other_host),
        not_crawled=tuple(not_crawled),
        duplicates=duplicates,
    )
