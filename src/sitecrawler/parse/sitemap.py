"""XML sitemap and sitemap-index parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from xml.etree import ElementTree

_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass(slots=True)
class SitemapDoc:
    """The useful content of one sitemap file."""

    kind: Literal["index", "urlset"]
    locs: list[str] = field(default_factory=list)
    """Child sitemap URLs for an index, page URLs for a urlset."""


def parse_sitemap(xml: bytes) -> SitemapDoc | None:
    """Parse a sitemap or sitemap index. Returns ``None`` if the XML is unusable."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return None

    if root.tag.lower().endswith("sitemapindex"):
        doc = SitemapDoc(kind="index")
        doc.locs = [el.text.strip() for el in root.iter(f"{_NS}loc") if el.text]
        return doc

    doc = SitemapDoc(kind="urlset")
    for url_el in root.iter(f"{_NS}url"):
        loc = url_el.find(f"{_NS}loc")
        if loc is not None and loc.text:
            doc.locs.append(loc.text.strip())
    return doc
