"""diff_rendered compares two parsed pages field by field and links as sets."""

from __future__ import annotations

from sitecrawler.models import ParsedPage, RenderDiff
from sitecrawler.parse import diff_rendered, parse_html

RAW = """<html><head><title>Raw</title><meta name="description" content="Desc"></head>
<body><h1>Head</h1><a href="/a">A</a><a href="/b">B</a><a href="/a">A again</a>
<p>one two three</p></body></html>"""
RENDERED = """<html><head><title>Rendered</title><meta name="description" content="Desc">
<link rel="canonical" href="/page"></head>
<body><h1>Head</h1><a href="/b">B</a><a href="/c">C</a><a href="/d">D</a>
<p>one two three four</p></body></html>"""
BASE = "https://x.test/page"


def test_diff_lists_changed_fields_and_link_sets() -> None:
    diff = diff_rendered(parse_html(RAW, BASE), parse_html(RENDERED, BASE))
    assert (diff.raw_title, diff.rendered_title) == ("Raw", "Rendered")
    assert (diff.raw_canonical, diff.rendered_canonical) == ("", "https://x.test/page")
    assert diff.raw_meta_description == diff.rendered_meta_description == "Desc"
    assert (diff.raw_h1, diff.rendered_h1) == ("Head", "Head")
    assert (diff.raw_link_count, diff.rendered_link_count) == (2, 3)  # /a twice counts once
    assert diff.links_added == ("https://x.test/c", "https://x.test/d")
    assert diff.links_removed == ("https://x.test/a",)
    assert diff.changes == ("title", "canonical", "links")
    assert diff.changed
    assert diff.describe() == "title, canonical, links +2/-1"


def test_word_count_is_reported_but_not_a_change() -> None:
    diff = diff_rendered(parse_html(RAW, BASE), parse_html(RAW.replace("three", "three 4"), BASE))
    assert diff.rendered_word_count == diff.raw_word_count + 1
    assert diff.changes == ()
    assert not diff.changed
    assert diff.describe() == ""


def test_identical_pages_have_no_changes() -> None:
    page = parse_html(RENDERED, BASE)
    diff = diff_rendered(page, page)
    assert not diff.changed
    assert diff.links_added == diff.links_removed == ()


def test_describe_counts_only_the_side_that_changed() -> None:
    assert RenderDiff(links_added=("x",)).describe() == "links +1"
    assert RenderDiff(links_removed=("x", "y")).describe() == "links -2"
    assert RenderDiff(raw_meta_robots="", rendered_meta_robots="noindex").describe() == (
        "meta robots"
    )
    diff = RenderDiff(raw_h1="a", rendered_h1="b", raw_meta_description="x")
    assert diff.changes == ("meta description", "h1")


def test_links_are_compared_as_sets_in_first_seen_order() -> None:
    raw = ParsedPage(links=["https://x/1", "https://x/2"])
    rendered = ParsedPage(links=["https://x/2", "https://x/1", "https://x/3", "https://x/3"])
    diff = diff_rendered(raw, rendered)
    assert diff.links_added == ("https://x/3",)
    assert diff.links_removed == ()
    assert diff.rendered_link_count == 3
