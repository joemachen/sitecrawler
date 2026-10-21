"""HTML parsing into a :class:`~sitecrawler.models.ParsedPage`."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from sitecrawler.models import LinkRef, ParsedPage

_DESCRIPTION = re.compile("^description$", re.IGNORECASE)
_ROBOTS = re.compile("^robots$", re.IGNORECASE)
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


def _meta_content(soup: BeautifulSoup, name: re.Pattern[str]) -> str:
    tag = soup.find("meta", attrs={"name": name})
    return _squash(_attr(tag, "content")) if isinstance(tag, Tag) else ""


def _headings(soup: BeautifulSoup, level: str) -> list[str]:
    return [_squash(h.get_text(" ")) for h in soup.find_all(level) if isinstance(h, Tag)]


def parse_html(html: str, base_url: str) -> ParsedPage:
    """Extract title, metas, headings, canonical, links and word count.

    Args:
        html: The document text.
        base_url: URL the document was served from; relative links resolve against it.
    """
    soup = BeautifulSoup(html, "lxml")
    page = ParsedPage()

    if soup.title is not None and soup.title.string:
        page.title = _squash(soup.title.string)

    page.meta_description = _meta_content(soup, _DESCRIPTION)
    page.meta_robots = _meta_content(soup, _ROBOTS)

    root = soup.find("html")
    if isinstance(root, Tag):
        page.lang = _attr(root, "lang").strip()

    page.h1s = _headings(soup, "h1")
    page.h2s = _headings(soup, "h2")
    page.h1 = page.h1s[0] if page.h1s else ""

    canonical = soup.find("link", rel=lambda v: bool(v) and "canonical" in v)
    if isinstance(canonical, Tag) and _attr(canonical, "href"):
        page.canonical = urljoin(base_url, _attr(canonical, "href"))

    for anchor in soup.find_all("a", href=True):
        href = _attr(anchor, "href").strip()
        if not href or href.startswith(_NON_LINK_SCHEMES):
            continue
        absolute = urljoin(base_url, href)
        page.links.append(absolute)
        page.anchors.append(
            LinkRef(absolute, text=_squash(anchor.get_text(" ")), rel=_attr(anchor, "rel"))
        )

    for noise in soup(["script", "style", "noscript"]):
        noise.decompose()
    page.word_count = len(soup.get_text(" ").split())
    return page
