"""HTML parsing into a :class:`~sitecrawler.models.ParsedPage`."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from sitecrawler.models import ParsedPage

_DESCRIPTION = re.compile("^description$", re.IGNORECASE)
_NON_LINK_SCHEMES = ("#", "mailto:", "tel:", "javascript:")


def _squash(text: str) -> str:
    return " ".join(text.split())


def _attr(tag: Tag, name: str) -> str:
    """Return a string attribute, flattening bs4's list-valued attributes."""
    value = tag.get(name)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return " ".join(value)


def parse_html(html: str, base_url: str) -> ParsedPage:
    """Extract title, description, first H1, canonical, links and word count.

    Args:
        html: The document text.
        base_url: URL the document was served from; relative links resolve against it.
    """
    soup = BeautifulSoup(html, "lxml")
    page = ParsedPage()

    if soup.title is not None and soup.title.string:
        page.title = _squash(soup.title.string)

    description = soup.find("meta", attrs={"name": _DESCRIPTION})
    if isinstance(description, Tag):
        page.meta_description = _squash(_attr(description, "content"))

    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        page.h1 = _squash(h1.get_text(" "))

    canonical = soup.find("link", rel=lambda v: bool(v) and "canonical" in v)
    if isinstance(canonical, Tag) and _attr(canonical, "href"):
        page.canonical = urljoin(base_url, _attr(canonical, "href"))

    for anchor in soup.find_all("a", href=True):
        href = _attr(anchor, "href").strip()
        if not href or href.startswith(_NON_LINK_SCHEMES):
            continue
        page.links.append(urljoin(base_url, href))

    for noise in soup(["script", "style", "noscript"]):
        noise.decompose()
    page.word_count = len(soup.get_text(" ").split())
    return page
