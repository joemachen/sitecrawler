"""Whole-crawl analysis: the sitemap diff and the link, duplicate and structured data reports."""

from sitecrawler.analysis.duplicates import DuplicateReport, duplicate_report, member_status
from sitecrawler.analysis.links import LinkReport, ProblemLink, anchor_texts, link_report
from sitecrawler.analysis.sitemaps import SitemapReport, sitemap_report
from sitecrawler.analysis.structured import StructuredReport, TypeCount, structured_report

__all__ = [
    "DuplicateReport",
    "LinkReport",
    "ProblemLink",
    "SitemapReport",
    "StructuredReport",
    "TypeCount",
    "anchor_texts",
    "duplicate_report",
    "link_report",
    "member_status",
    "sitemap_report",
    "structured_report",
]
