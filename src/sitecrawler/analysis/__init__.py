"""Whole-crawl analysis: the sitemap diff, the link report and the duplicate report."""

from sitecrawler.analysis.duplicates import DuplicateReport, duplicate_report, member_status
from sitecrawler.analysis.links import LinkReport, ProblemLink, anchor_texts, link_report
from sitecrawler.analysis.sitemaps import SitemapReport, sitemap_report

__all__ = [
    "DuplicateReport",
    "LinkReport",
    "ProblemLink",
    "SitemapReport",
    "anchor_texts",
    "duplicate_report",
    "link_report",
    "member_status",
    "sitemap_report",
]
