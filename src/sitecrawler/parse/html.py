"""HTML parsing into a :class:`~sitecrawler.models.ParsedPage`, on lxml."""

from __future__ import annotations

from urllib.parse import urljoin

from lxml import etree
from lxml import html as lxml_html

from sitecrawler.models import HreflangRef, LinkRef, ParsedPage

_NON_LINK_SCHEMES = ("#", "mailto:", "tel:", "javascript:")
_NOISE = ("script", "style", "noscript")
_SECTIONS = {"header": "header", "nav": "nav", "footer": "footer", "aside": "aside"}
"""Sectioning elements that name a link's position."""
_ROLES = {
    "banner": "header",
    "navigation": "nav",
    "contentinfo": "footer",
    "complementary": "aside",
}
"""ARIA roles that stand in for the elements above on templates built from ``<div>``."""
_PARSER = lxml_html.HTMLParser(encoding="utf-8")
_EMPTY = b"<html></html>"


def _squash(text: str) -> str:
    return " ".join(text.split())


def parse_document(html: str) -> etree._Element:
    """Parse ``html`` into an lxml tree and return its ``<html>`` root.

    Fragments are wrapped in ``<html><body>``; an empty or whitespace-only
    document gives an empty ``<html>``. The text is encoded to UTF-8 bytes
    first because lxml refuses ``str`` input that carries an XML encoding
    declaration, which XHTML pages do.
    """
    try:
        return lxml_html.document_fromstring(html.encode("utf-8"), parser=_PARSER)
    except etree.ParserError:  # "Document is empty"
        return lxml_html.document_fromstring(_EMPTY, parser=_PARSER)


def text_of(element: etree._Element) -> str:
    """Visible text of ``element``: text nodes joined with a space, whitespace squashed.

    Comments are skipped; ``<br>`` and nested tags separate words, so
    ``<h1>Hello<br>World</h1>`` reads ``Hello World``.
    """
    return _squash(" ".join(t if isinstance(t, str) else t.decode() for t in element.itertext()))


def _attr(element: etree._Element, name: str) -> str:
    value = element.get(name)
    return value if value is not None else ""


def link_position(anchor: etree._Element) -> str:
    """Where ``anchor`` sits: ``header``, ``nav``, ``footer``, ``aside`` or ``body``.

    The nearest ``<header>``, ``<nav>``, ``<footer>`` or ``<aside>`` ancestor
    (or an element carrying the matching ARIA role: ``banner``,
    ``navigation``, ``contentinfo``, ``complementary``) names the position;
    an anchor under none of them is ``body``. Nearest wins, so the main
    menu inside ``<header><nav>`` reads ``nav``.
    """
    for ancestor in anchor.iterancestors():
        tag = ancestor.tag if isinstance(ancestor.tag, str) else ""
        if tag in _SECTIONS:
            return _SECTIONS[tag]
        role = _attr(ancestor, "role").strip().lower()
        if role in _ROLES:
            return _ROLES[role]
    return "body"


def _metas(doc: etree._Element, name: str) -> list[etree._Element]:
    """Every ``<meta name=...>`` whose name matches ``name``, ignoring case."""
    return [m for m in doc.iter("meta") if _attr(m, "name").strip().lower() == name]


def parse_html(html: str, base_url: str) -> ParsedPage:
    """Extract title, metas, headings, canonical, links and word count.

    Args:
        html: The document text.
        base_url: URL the document was served from; relative links resolve against it.
    """
    doc = parse_document(html)
    page = ParsedPage()

    titles = list(doc.iter("title"))
    page.title_count = len(titles)
    if titles:
        page.title = text_of(titles[0])

    descriptions = _metas(doc, "description")
    page.meta_description_count = len(descriptions)
    if descriptions:
        page.meta_description = _squash(_attr(descriptions[0], "content"))
    robots = _metas(doc, "robots")
    if robots:
        page.meta_robots = _squash(_attr(robots[0], "content"))

    page.lang = _attr(doc, "lang").strip()

    page.h1s = [text_of(h) for h in doc.iter("h1")]
    page.h2s = [text_of(h) for h in doc.iter("h2")]
    page.h1 = page.h1s[0] if page.h1s else ""

    for meta in doc.iter("meta"):
        content = _attr(meta, "content").strip()
        if _attr(meta, "property") == "og:url" and content:
            page.og_url = urljoin(base_url, content)
            break

    for link in doc.iter("link"):
        href = _attr(link, "href").strip()
        if not href:
            continue
        rels = _attr(link, "rel").lower().split()
        absolute = urljoin(base_url, href)
        if "canonical" in rels and not page.canonical:
            page.canonical = absolute
        if "alternate" in rels and _attr(link, "hreflang"):
            page.hreflang.append(HreflangRef(_attr(link, "hreflang").strip(), absolute))
        if "prev" in rels and not page.rel_prev:
            page.rel_prev = absolute
        if "next" in rels and not page.rel_next:
            page.rel_next = absolute

    for anchor in doc.iter("a"):
        href = _attr(anchor, "href").strip()
        if not href or href.startswith(_NON_LINK_SCHEMES):
            continue
        absolute = urljoin(base_url, href)
        page.links.append(absolute)
        page.anchors.append(
            LinkRef(
                absolute,
                text=text_of(anchor),
                rel=_attr(anchor, "rel"),
                position=link_position(anchor),
            )
        )

    etree.strip_elements(doc, *_NOISE, with_tail=False)
    page.word_count = len(text_of(doc).split())
    return page
