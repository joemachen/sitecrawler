"""Pure URL helpers: normalisation and same-site checks."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SKIP_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp", ".avif",
        ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z",
        ".css", ".js", ".json", ".xml", ".txt", ".map",
        ".mp4", ".mp3", ".webm", ".mov", ".avi", ".wav",
        ".woff", ".woff2", ".ttf", ".eot", ".otf",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".csv",
    }
)  # fmt: skip
"""Path extensions that are never HTML pages."""

TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "ref", "_ga",
    }
)  # fmt: skip
"""Query parameters that never change page content and are always dropped."""

_MULTI_SLASH = re.compile(r"/{2,}")


def strip_www(host: str) -> str:
    """Lower-case a hostname and drop a leading ``www.``."""
    host = host.lower()
    return host.removeprefix("www.")


def same_site(host_a: str, host_b: str) -> bool:
    """True when two hostnames refer to the same site (``www.`` is ignored)."""
    return strip_www(host_a) == strip_www(host_b)


def normalize(url: str, *, keep_query: bool = False, scheme: str | None = None) -> str | None:
    """Canonicalise a URL so the same page is never crawled twice.

    Normalisation: lower-case host without ``www.``, duplicate slashes
    collapsed, trailing slash removed (except for the root), fragment dropped.
    Query strings are dropped unless ``keep_query`` is set, in which case
    tracking parameters are removed and the rest are sorted.

    Args:
        url: Any absolute URL.
        keep_query: Preserve (cleaned, sorted) query parameters.
        scheme: Force this scheme (``"http"`` or ``"https"``) so that http and
            https forms of a page collapse to one. Defaults to the URL's own.

    Returns:
        The normalised URL, or ``None`` if the input is not an http(s) URL.
    """
    try:
        parts = urlparse(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None

    host = strip_www(parts.netloc)
    path = _MULTI_SLASH.sub("/", parts.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    query = ""
    if keep_query and parts.query:
        params = [
            (k, v)
            for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        query = urlencode(sorted(params))

    return urlunparse((scheme or parts.scheme, host, path, "", query, ""))


def parse_url_list(lines: Iterable[str]) -> list[str]:
    """Read a URL list: one per line, blank lines and ``#`` comments ignored, duplicates dropped.

    URLs are returned as written (not normalised) and in order of first appearance.
    """
    seen: set[str] = set()
    urls: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line not in seen:
            seen.add(line)
            urls.append(line)
    return urls


def looks_like_page(url: str) -> bool:
    """Cheap pre-filter: skip URLs whose path extension can't be an HTML page."""
    path = urlparse(url).path.lower()
    dot = path.rfind(".")
    if dot != -1 and "/" not in path[dot:]:
        return path[dot:] not in SKIP_EXTENSIONS
    return True
