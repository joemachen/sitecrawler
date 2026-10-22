"""Robots directives of a page, read the same way by the engine, the rules and the graph."""

from __future__ import annotations

from sitecrawler.models import PageRecord

NOINDEX_TOKENS = frozenset({"noindex", "none"})
"""Directives that keep a page out of the index."""

NOFOLLOW_TOKENS = frozenset({"nofollow", "none"})
"""Directives that stop every link on the page from passing equity."""


def robots_directives(page: PageRecord) -> frozenset[str]:
    """Lower-cased directive tokens from ``<meta name="robots">`` and ``X-Robots-Tag``."""
    raw = f"{page.meta_robots},{page.headers.get('x-robots-tag', '')}"
    tokens: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        token = part.strip().lower()
        if ":" in token:  # "googlebot: noindex" or "unavailable_after: ..."
            agent, _, directive = token.partition(":")
            token = directive.strip() if agent in {"googlebot", "*"} else ""
        if token:
            tokens.add(token)
    return frozenset(tokens)


def page_nofollow(page: PageRecord) -> bool:
    """True when the page's directives say none of its links pass equity."""
    return bool(NOFOLLOW_TOKENS & robots_directives(page))
