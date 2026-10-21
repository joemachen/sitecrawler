"""Title, meta description and heading rules."""

from sitecrawler.audit.rules import headings, meta, titles
from tests.unit.audit.helpers import SITE, flagged, page

LONG = "x" * 61
OK_TITLE = "A title of a sensible length for a page"
OK_DESC = "A description of a sensible length for a page, with enough words to pass."


def test_title_rules() -> None:
    pages = [
        page("/missing", title=""),
        page("/long", title=LONG),
        page("/short", title="Tiny"),
        page("/multi", title=OK_TITLE, title_count=2),
        page("/same", title="Same Words", h1="same words"),
        page("/dup-a", title="Shared"),
        page("/dup-b", title="shared"),
        page("/ok", title=OK_TITLE + " that is unique", h1="Different"),
        page("/redirected", title="", final_url=f"{SITE}/elsewhere"),
    ]
    assert set(flagged(titles.Missing(), pages)) == {"/missing"}
    assert set(flagged(titles.TooLong(), pages)) == {"/long"}
    assert flagged(titles.TooLong(), pages)["/long"].message == "61 characters"
    assert set(flagged(titles.TooShort(), pages)) == {"/short", "/same", "/dup-a", "/dup-b"}
    assert set(flagged(titles.Multiple(), pages)) == {"/multi"}
    assert set(flagged(titles.SameAsH1(), pages)) == {"/same"}
    dup = flagged(titles.Duplicate(), pages)
    assert set(dup) == {"/dup-a", "/dup-b"}
    assert dup["/dup-a"].message == f"same as {SITE}/dup-b"


def test_duplicate_message_counts_the_rest() -> None:
    pages = [page(f"/p{i}", title="Shared") for i in range(3)]
    dup = flagged(titles.Duplicate(), pages)
    assert dup["/p0"].message == f"same as {SITE}/p1 and 1 more"


def test_meta_rules() -> None:
    pages = [
        page("/missing", meta_description=""),
        page("/long", meta_description="d" * 156),
        page("/short", meta_description="Brief."),
        page("/multi", meta_description=OK_DESC + " Twice.", meta_description_count=2),
        page("/dup-a", meta_description=OK_DESC),
        page("/dup-b", meta_description=OK_DESC.upper()),
        page("/ok", meta_description=OK_DESC + " Unique."),
    ]
    assert set(flagged(meta.Missing(), pages)) == {"/missing"}
    assert set(flagged(meta.TooLong(), pages)) == {"/long"}
    assert set(flagged(meta.TooShort(), pages)) == {"/short"}
    assert set(flagged(meta.Multiple(), pages)) == {"/multi"}
    assert set(flagged(meta.Duplicate(), pages)) == {"/dup-a", "/dup-b"}


def test_heading_rules() -> None:
    pages = [
        page("/none", h1="", h1s=()),
        page("/two", h1="A", h1s=("A", "B")),
        page("/long", h1="h" * 71, h1s=("h" * 71,)),
        page("/dup-a", h1="Shared heading", h1s=("Shared heading",)),
        page("/dup-b", h1="shared heading", h1s=("shared heading",)),
        page("/noh2", h2s=()),
        page("/ok"),
    ]
    assert set(flagged(headings.H1Missing(), pages)) == {"/none"}
    two = flagged(headings.H1Multiple(), pages)
    assert set(two) == {"/two"}
    assert two["/two"].message == "2 H1s: A | B"
    assert set(flagged(headings.H1TooLong(), pages)) == {"/long"}
    assert set(flagged(headings.H1Duplicate(), pages)) == {"/dup-a", "/dup-b"}
    assert set(flagged(headings.H2Missing(), pages)) == {"/noh2"}
