"""Content rules: duplicate, near-duplicate and low word count."""

from __future__ import annotations

from sitecrawler.audit.duplicates import MIN_WORDS
from sitecrawler.audit.rules import content
from sitecrawler.models import Fingerprint, PageRecord
from sitecrawler.parse import fingerprint_text
from tests.unit.audit.helpers import SITE, flagged, long_text, page

LONG = long_text(MIN_WORDS + 20)
LONG_NEAR = LONG.replace("word100 word101", "changed words")
LONG_NEAR_2 = LONG.replace("word10 word11", "other changed words")
LONG_OTHER = long_text(MIN_WORDS, prefix="o")
SHORT = "a short page with the same few words on it"


def _page(path: str, text: str, **fields: object) -> PageRecord:
    return page(path, fingerprint=fingerprint_text(text), **fields)  # type: ignore[arg-type]


def test_duplicate_flags_indexable_copies_only() -> None:
    pages = [
        _page("/a", LONG),
        _page("/b", LONG),
        _page("/copy", LONG, canonical=f"{SITE}/a"),
        _page("/hidden", LONG, meta_robots="noindex"),
        _page("/s1", SHORT),
        _page("/s2", SHORT),
        _page("/alone", LONG_OTHER),
        _page("/alone-copy", LONG_OTHER, canonical=f"{SITE}/alone"),
    ]
    hits = flagged(content.Duplicate(), pages)
    assert {path: issue.message for path, issue in hits.items()} == {
        "/a": f"same as {SITE}/b",
        "/b": f"same as {SITE}/a",
        "/s1": f"same as {SITE}/s2",
        "/s2": f"same as {SITE}/s1",
    }
    assert flagged(content.Duplicate(), [_page("/a", LONG), _page("/b", LONG_NEAR)]) == {}


def test_near_duplicate_names_the_closest_other_text() -> None:
    pages = [
        _page("/a", LONG),
        _page("/a2", LONG),  # exact twin of /a: a duplicate, not a near-duplicate of it
        _page("/b", LONG_NEAR),
        _page("/c", LONG_NEAR_2),
        _page("/copy", LONG_NEAR, canonical=f"{SITE}/b"),
        _page("/s1", SHORT),
        _page("/s2", SHORT + " extra"),
    ]
    hits = flagged(content.NearDuplicate(), pages)
    assert set(hits) == {"/a", "/a2", "/b", "/c"}
    a_message = hits["/a"].message
    assert a_message.startswith(f"nearly the same as {SITE}/")
    assert a_message.endswith("of 64 bits differ) and 1 more")
    assert hits["/a2"].message == a_message
    assert hits["/b"].message.endswith("of 64 bits differ) and 2 more")  # /a, /a2, /c
    # a cluster of exact twins alone, or with only non-indexable partners, is not near
    twins = [
        _page("/a", LONG),
        _page("/a2", LONG),
        _page("/copy", LONG_NEAR, canonical=f"{SITE}/a"),
    ]
    assert flagged(content.NearDuplicate(), twins) == {}


def test_low_word_count_is_for_indexable_html_pages_under_the_floor() -> None:
    pages = [
        _page("/thin", SHORT),
        _page("/empty", ""),
        _page("/long", LONG),
        _page("/noindex", SHORT, meta_robots="noindex"),
        page("/unparsed", fingerprint=None),
        _page("/exact", " ".join(f"w{i}" for i in range(MIN_WORDS))),
    ]
    hits = flagged(content.LowWordCount(), pages)
    assert {path: issue.message for path, issue in hits.items()} == {
        "/thin": "10 words",
        "/empty": "0 words",
    }
    assert page("/x", fingerprint=Fingerprint()).fingerprint is not None
