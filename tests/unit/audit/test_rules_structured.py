"""Structured data rules: one issue per page per rule, every finding in the message."""

from __future__ import annotations

from sitecrawler.audit.rules import structured
from sitecrawler.models import PageRecord
from sitecrawler.parse import extract_structured
from sitecrawler.parse.html import parse_document
from tests.unit.audit.helpers import SITE, flagged, page


def _page(path: str, *blocks: str, **fields: object) -> PageRecord:
    html = "".join(f'<script type="application/ld+json">{b}</script>' for b in blocks)
    data = extract_structured(parse_document(html), f"{SITE}{path}")
    return page(path, structured=data, **fields)  # type: ignore[arg-type]


PAGES = [
    _page("/broken", '{"@type": "Event",}', '{"name": "x" "y"}'),
    _page("/product", '{"@type": "Product", "name": "W", "offers": {"priceCurrency": "USD"}}'),
    _page("/typo", '{"@type": "Prodcut"}', '{"@type": "Prodcut"}'),
    _page("/prop", '{"@type": "WebPage", "authr": "A"}'),
    _page(
        "/twice",
        '{"@type": "WebPage", "@id": "#p", "name": "One"}',
        '{"@type": "WebPage", "@id": "#p", "name": "Two"}',
    ),
    _page("/fine", '{"@type": "WebSite", "name": "S"}'),
    _page("/redirect", '{"@type": "Prodcut"}', final_url=f"{SITE}/fine"),
]


def test_invalid_json_lists_every_broken_block() -> None:
    issues = flagged(structured.InvalidJson(), PAGES)
    assert set(issues) == {"/broken"}
    assert issues["/broken"].message.count("(line 1, column") == 2
    assert "; " in issues["/broken"].message


def test_missing_required_and_recommended() -> None:
    required = flagged(structured.MissingRequired(), PAGES)
    assert {p: i.message for p, i in required.items()} == {
        "/product": "Product needs offers.price or offers.priceSpecification.price "
        "or offers.lowPrice"
    }
    recommended = flagged(structured.MissingRecommended(), PAGES)
    assert recommended["/product"].message == (
        "Product lacks aggregateRating, review, offers.availability"
    )


def test_unknown_type_is_reported_once_per_page_and_redirects_are_skipped() -> None:
    issues = flagged(structured.UnknownType(), PAGES)
    assert {p: i.message for p, i in issues.items()} == {
        "/typo": "Prodcut is not a schema.org type"
    }


def test_unknown_property_and_conflicting() -> None:
    assert set(flagged(structured.UnknownProperty(), PAGES)) == {"/prop"}
    conflicts = flagged(structured.Conflicting(), PAGES)
    assert set(conflicts) == {"/twice"}
    assert conflicts["/twice"].message.endswith("disagree on name: 'One' vs 'Two'")
