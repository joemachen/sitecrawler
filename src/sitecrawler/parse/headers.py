"""Parsing of HTTP header values the crawler keeps."""

from __future__ import annotations

import re
from urllib.parse import urljoin

_LINK_PART = re.compile(r"<([^>]*)>\s*((?:;[^,]*)*)")
_REL = re.compile(r"rel\s*=\s*\"?([^\";]*)\"?", re.IGNORECASE)


def link_header_rels(value: str, base_url: str) -> dict[str, str]:
    """Map each ``rel`` in a ``Link`` header to its (absolute) target.

    ``<https://x/a>; rel="canonical", </b>; rel=next`` gives
    ``{"canonical": "https://x/a", "next": "https://x/b"}``. The first target
    wins when a rel repeats. Malformed input yields an empty mapping.
    """
    rels: dict[str, str] = {}
    for target, params in _LINK_PART.findall(value):
        rel = _REL.search(params)
        if not rel:
            continue
        for name in rel.group(1).lower().split():
            rels.setdefault(name, urljoin(base_url, target.strip()))
    return rels
