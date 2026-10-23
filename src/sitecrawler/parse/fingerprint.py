"""Content fingerprints: a hash of the main text and a SimHash for near-duplicates (ADR-0012).

The HTML bodies are not stored, so both fingerprints are computed while the
page is in hand and kept on the page record. *Main text* is the visible text
of ``<main>`` (or the body) with the boilerplate removed: ``header``,
``nav``, ``footer`` and ``aside`` elements, their ARIA-role stand-ins, and
scripts and styles. Two pages with the same main text have the same
:attr:`~sitecrawler.models.Fingerprint.content_hash`; two pages whose main
text mostly overlaps have SimHash values a few bits apart.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections import Counter
from collections.abc import Iterable

from lxml import etree

from sitecrawler.models import Fingerprint

BITS = 64
"""Width of a SimHash fingerprint."""

SHINGLE = 3
"""Words per SimHash feature. Three-word runs tell reordered text from repeated text."""

BOILERPLATE = ("header", "nav", "footer", "aside", "script", "style", "noscript", "template")
"""Elements removed before the main text is read."""

_ROLES = ("banner", "navigation", "contentinfo", "complementary")
"""ARIA roles that mark the same boilerplate on templates built from ``<div>``."""

_WORD = re.compile(r"\w+")


def _attr(element: etree._Element, name: str) -> str:
    value = element.get(name)
    return value if value is not None else ""


def _role(element: etree._Element) -> str:
    return _attr(element, "role").strip().lower()


def _main_root(doc: etree._Element) -> etree._Element:
    """The element whose text is the page's content: ``<main>``, else ``role=main``, else body."""
    for element in doc.iter("main"):
        return element
    for element in doc.iter():
        if isinstance(element.tag, str) and _role(element) == "main":
            return element
    for element in doc.iter("body"):
        return element
    return doc


def main_text(doc: etree._Element) -> str:
    """Visible text of the page's content, boilerplate removed, whitespace squashed.

    ``doc`` is left untouched; the boilerplate is stripped from a copy.
    """
    root = copy.deepcopy(_main_root(doc))
    etree.strip_elements(root, *BOILERPLATE, with_tail=False)
    for element in list(root.iter()):
        if isinstance(element.tag, str) and _role(element) in _ROLES:
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)  # drops the tail text too, like strip_elements above
    return " ".join(" ".join(t for t in root.itertext() if isinstance(t, str)).split())


def words(text: str) -> list[str]:
    """The words of ``text`` in casefold form; punctuation is not a word."""
    return _WORD.findall(text.casefold())


def shingles(tokens: list[str], size: int = SHINGLE) -> Iterable[str]:
    """Every run of ``size`` consecutive tokens, or the whole text when it is shorter."""
    if len(tokens) <= size:
        if tokens:
            yield " ".join(tokens)
        return
    for start in range(len(tokens) - size + 1):
        yield " ".join(tokens[start : start + size])


def _feature_hash(feature: str) -> int:
    return int.from_bytes(hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(), "big")


def simhash(features: Iterable[str]) -> int:
    """Charikar's SimHash of ``features``: 64 bits, each the sign of a weighted vote.

    Features that occur more than once vote with their count. An empty
    feature set gives 0.
    """
    votes = [0] * BITS
    for feature, weight in Counter(features).items():
        bits = _feature_hash(feature)
        for i in range(BITS):
            votes[i] += weight if bits >> i & 1 else -weight
    value = 0
    for i, vote in enumerate(votes):
        if vote > 0:
            value |= 1 << i
    return value


def hamming(a: int, b: int) -> int:
    """How many of the 64 bits differ between two SimHash values."""
    return (a ^ b).bit_count()


def fingerprint_text(text: str) -> Fingerprint:
    """The fingerprint of already-extracted main text."""
    tokens = words(text)
    if not tokens:
        return Fingerprint()
    digest = hashlib.sha256(" ".join(tokens).encode("utf-8")).hexdigest()
    return Fingerprint(digest, simhash(shingles(tokens)), len(tokens))


def fingerprint(doc: etree._Element) -> Fingerprint:
    """The fingerprint of a parsed document's main text."""
    return fingerprint_text(main_text(doc))
