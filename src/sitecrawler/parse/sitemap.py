"""XML sitemap and sitemap-index parsing, gzip included. No I/O."""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from typing import Literal
from xml.etree import ElementTree

from sitecrawler.models import SitemapEntry

_GZIP_MAGIC = b"\x1f\x8b"
_FIELDS = ("loc", "lastmod", "changefreq", "priority")


@dataclass(slots=True)
class SitemapDoc:
    """The useful content of one sitemap file."""

    kind: Literal["index", "urlset"]
    entries: list[SitemapEntry] = field(default_factory=list)
    """Child sitemaps for an index, pages for a urlset; ``sitemap_url`` is the file parsed."""

    @property
    def locs(self) -> list[str]:
        """The ``<loc>`` of every entry, in document order."""
        return [entry.loc for entry in self.entries]


def _local(tag: str) -> str:
    """``loc`` for ``{http://www.sitemaps.org/schemas/sitemap/0.9}loc`` (and for a bare ``loc``)."""
    return tag.rpartition("}")[2].lower()


def _entry(container: ElementTree.Element, source: str) -> SitemapEntry | None:
    values = dict.fromkeys(_FIELDS, "")
    for child in container:
        name = _local(child.tag)
        if name in values and child.text and not values[name]:
            values[name] = child.text.strip()
    if not values["loc"]:
        return None
    return SitemapEntry(
        source, values["loc"], values["lastmod"], values["changefreq"], values["priority"]
    )


def parse_sitemap(xml: bytes, source: str = "") -> SitemapDoc | None:
    """Parse a sitemap or sitemap index, gzip-compressed or plain.

    Elements are matched by local name, so a file that omits or misspells the
    sitemaps.org namespace still parses. Returns ``None`` if the bytes are not
    usable XML with a ``urlset`` or ``sitemapindex`` root.

    Args:
        xml: The file's bytes as fetched.
        source: The sitemap's own URL, recorded on every entry.
    """
    if xml.startswith(_GZIP_MAGIC):
        try:
            xml = gzip.decompress(xml)
        except (OSError, EOFError):
            return None
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return None

    root_name = _local(root.tag)
    if root_name == "sitemapindex":
        doc = SitemapDoc(kind="index")
        child_name = "sitemap"
    elif root_name == "urlset":
        doc = SitemapDoc(kind="urlset")
        child_name = "url"
    else:
        return None
    for container in root:
        if _local(container.tag) != child_name:
            continue
        entry = _entry(container, source)
        if entry is not None:
            doc.entries.append(entry)
    return doc
