"""Turn fetched bytes into typed records. This package never does I/O."""

from sitecrawler.parse.extract import (
    ExtractorSet,
    compile_extractors,
    load_extract_toml,
    parse_extractor,
    parse_search,
    parse_searches,
)
from sitecrawler.parse.fingerprint import fingerprint, fingerprint_text, hamming, main_text
from sitecrawler.parse.headers import link_header_rels
from sitecrawler.parse.html import parse_html
from sitecrawler.parse.render_diff import diff_rendered
from sitecrawler.parse.sitemap import SitemapDoc, parse_sitemap

__all__ = [
    "ExtractorSet",
    "SitemapDoc",
    "compile_extractors",
    "diff_rendered",
    "fingerprint",
    "fingerprint_text",
    "hamming",
    "link_header_rels",
    "load_extract_toml",
    "main_text",
    "parse_extractor",
    "parse_html",
    "parse_search",
    "parse_searches",
    "parse_sitemap",
]
