"""Write an XML sitemap (or a sitemap index with numbered parts) from crawled pages."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SITEMAP_MAX_URLS = 50_000
"""The protocol's limit per file; more URLs than this become an index plus parts."""


@dataclass(slots=True, frozen=True)
class SitemapUrl:
    """One ``<url>`` to write."""

    loc: str
    lastmod: str = ""
    """W3C datetime (``2026-10-21T10:00:00+00:00``) or empty for no ``<lastmod>``."""


def lastmod_from_header(last_modified: str) -> str:
    """Turn an HTTP ``Last-Modified`` value into a W3C datetime, or ``""`` if it is not one."""
    if not last_modified.strip():
        return ""
    try:
        parsed = parsedate_to_datetime(last_modified)
    except (TypeError, ValueError, IndexError):
        return ""
    return parsed.isoformat(timespec="seconds")


def _urlset(urls: Sequence[SitemapUrl]) -> ElementTree.Element:
    root = ElementTree.Element("urlset", xmlns=SITEMAP_NS)
    for url in urls:
        node = ElementTree.SubElement(root, "url")
        ElementTree.SubElement(node, "loc").text = url.loc
        if url.lastmod:
            ElementTree.SubElement(node, "lastmod").text = url.lastmod
    return root


def _index(locs: Sequence[str]) -> ElementTree.Element:
    root = ElementTree.Element("sitemapindex", xmlns=SITEMAP_NS)
    for loc in locs:
        node = ElementTree.SubElement(root, "sitemap")
        ElementTree.SubElement(node, "loc").text = loc
    return root


def _write(root: ElementTree.Element, path: Path) -> None:
    ElementTree.indent(root)
    ElementTree.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def write_sitemap(
    urls: Sequence[SitemapUrl],
    output: Path,
    *,
    base_url: str = "",
    max_urls: int = SITEMAP_MAX_URLS,
) -> list[Path]:
    """Write ``urls`` to ``output`` as one sitemap, or as an index plus numbered parts.

    Up to ``max_urls`` entries go in ``output`` itself. Beyond that, ``output``
    becomes a sitemap index pointing at ``<stem>-1.xml``, ``<stem>-2.xml``, ...
    next to it, each with at most ``max_urls`` entries; ``base_url`` is where
    those files will be served from, so the index can name them absolutely.

    Args:
        urls: The pages to list, in the order to write them.
        output: The sitemap (or index) file to write; its parent must exist.
        base_url: Site root the parts will be uploaded under, such as
            ``https://example.com/``; required when the index form is used.
        max_urls: Entries per file; the protocol's 50,000 by default.

    Returns:
        The files written, the index (or the single sitemap) first.

    Raises:
        ValueError: more than ``max_urls`` URLs and no ``base_url``.
    """
    if len(urls) <= max_urls:
        _write(_urlset(urls), output)
        return [output]
    if not base_url:
        msg = f"{len(urls)} URLs need a sitemap index; pass base_url so it can name the parts"
        raise ValueError(msg)
    parts: list[Path] = []
    for number, start in enumerate(range(0, len(urls), max_urls), start=1):
        part = output.with_name(f"{output.stem}-{number}.xml")
        _write(_urlset(urls[start : start + max_urls]), part)
        parts.append(part)
    _write(_index([urljoin(base_url, part.name) for part in parts]), output)
    return [output, *parts]
