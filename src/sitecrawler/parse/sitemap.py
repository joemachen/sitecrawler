"""XML sitemap and sitemap-index parsing, gzip included. No I/O."""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from io import BytesIO
from typing import Literal
from urllib.parse import urljoin
from xml.etree import ElementTree

from sitecrawler.models import SitemapEntry

_GZIP_MAGIC = b"\x1f\x8b"
GZIP_MAX_BYTES = 64 * 1024 * 1024
"""Largest decompressed sitemap accepted; the protocol caps a file at 50 MB."""
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
    loc = urljoin(source, values["loc"]) if source else values["loc"]
    return SitemapEntry(source, loc, values["lastmod"], values["changefreq"], values["priority"])


def _gunzip(xml: bytes) -> bytes | None:
    """Decompress ``xml``, or ``None`` when it is corrupt or inflates past the limit."""
    try:
        with gzip.GzipFile(fileobj=BytesIO(xml)) as stream:
            data = stream.read(GZIP_MAX_BYTES + 1)
    except (OSError, EOFError):
        return None
    return data if len(data) <= GZIP_MAX_BYTES else None


def parse_sitemap(xml: bytes, source: str = "") -> SitemapDoc | None:
    """Parse a sitemap or sitemap index, gzip-compressed or plain.

    Elements are matched by local name, so a file that omits or misspells the
    sitemaps.org namespace still parses. A relative ``<loc>`` is resolved
    against ``source``; a URL listed twice in one file is one entry. Returns
    ``None`` if the bytes are not usable XML with a ``urlset`` or
    ``sitemapindex`` root, or a gzip file that inflates past
    :data:`GZIP_MAX_BYTES`.

    Args:
        xml: The file's bytes as fetched.
        source: The sitemap's own URL, recorded on every entry.
    """
    if xml.startswith(_GZIP_MAGIC):
        inflated = _gunzip(xml)
        if inflated is None:
            return None
        xml = inflated
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
    seen: set[str] = set()
    for container in root:
        if _local(container.tag) != child_name:
            continue
        entry = _entry(container, source)
        if entry is not None and entry.loc not in seen:
            seen.add(entry.loc)
            doc.entries.append(entry)
    return doc
