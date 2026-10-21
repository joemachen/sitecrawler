"""Turn fetched bytes into typed records. This package never does I/O."""

from sitecrawler.parse.html import parse_html
from sitecrawler.parse.sitemap import SitemapDoc, parse_sitemap

__all__ = ["SitemapDoc", "parse_html", "parse_sitemap"]
