"""The structured data index: vocabulary, rich-result needs and findings per page."""

from __future__ import annotations

from sitecrawler.audit.richresults import RICH_RESULTS, Need
from sitecrawler.audit.structured import (
    KINDS,
    Finding,
    StructuredIndex,
    Vocabulary,
    check_page,
    rich_result_for,
)
from sitecrawler.models import PageRecord, StructuredData
from sitecrawler.parse import extract_structured
from sitecrawler.parse.html import parse_document
from tests.unit.audit.helpers import SITE, page, view

VOCAB = Vocabulary.bundled()


def ld(*blocks: str) -> str:
    return "".join(f'<script type="application/ld+json">{b}</script>' for b in blocks)


def structured(path: str, html: str) -> PageRecord:
    return page(path, structured=extract_structured(parse_document(html), f"{SITE}{path}"))


def findings(html: str) -> list[Finding]:
    return check_page(structured("/p", html), VOCAB)


def kinds(html: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for f in findings(html):
        found.setdefault(f.kind, []).append(f.message)
    return found


COMPLETE_PRODUCT = """{"@context": "https://schema.org", "@type": "Product", "name": "Widget",
  "offers": {"@type": "Offer", "price": "9.99", "priceCurrency": "USD",
             "availability": "https://schema.org/InStock"},
  "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.5", "reviewCount": "8"},
  "review": {"@type": "Review", "author": {"@type": "Person", "name": "Ann"},
             "reviewRating": {"@type": "Rating", "ratingValue": "5"}}}"""


# ------------------------------------------------------------------ vocabulary


def test_bundled_vocabulary_has_types_parents_and_domains() -> None:
    assert VOCAB is Vocabulary.bundled()
    assert VOCAB.is_type("Product")
    assert not VOCAB.is_type("Prodcut")
    assert VOCAB.ancestors("NewsArticle")[:3] == ("NewsArticle", "Article", "CreativeWork")
    # LocalBusiness reaches Thing through Organization and Place; it is listed once.
    assert VOCAB.ancestors("LocalBusiness").count("Thing") == 1
    assert VOCAB.ancestors("LocalBusiness") is VOCAB.ancestors("LocalBusiness")
    assert VOCAB.allows("Offer", "price")
    assert VOCAB.allows("Product", "name")  # inherited from Thing
    assert not VOCAB.allows("Product", "price")
    assert not VOCAB.allows("Product", "authr")


def test_rich_result_for_uses_the_nearest_listed_ancestor() -> None:
    assert rich_result_for(VOCAB, "Restaurant") is RICH_RESULTS["LocalBusiness"]
    assert rich_result_for(VOCAB, "BlogPosting") is RICH_RESULTS["Article"]
    assert rich_result_for(VOCAB, "WebSite") is None
    assert "FAQPage" not in RICH_RESULTS
    assert Need(("offers.price", "offers.lowPrice")).label == "offers.price or offers.lowPrice"


# ------------------------------------------------------------------ rich results


def test_a_complete_product_has_no_findings() -> None:
    assert findings(ld(COMPLETE_PRODUCT)) == []


def test_product_without_offers_price_misses_a_required_property() -> None:
    no_price = COMPLETE_PRODUCT.replace('"price": "9.99", ', "")
    assert kinds(ld(no_price)) == {
        "missing_required": [
            "Product needs offers.price or offers.priceSpecification.price or offers.lowPrice"
        ]
    }
    # Every offer needs a price, and a blank one does not count.
    two = COMPLETE_PRODUCT.replace(
        '"offers": {', '"offers": [{"@type": "Offer", "price": " "}, {'
    ).replace('"aggregateRating"', '"aggregateRating"', 1)
    two = two.replace('InStock"},', 'InStock"}],')
    assert "missing_required" in kinds(ld(two))


def test_product_needs_one_of_offers_review_or_rating_and_a_name() -> None:
    found = kinds(ld('{"@type": "Product"}'))
    assert found["missing_required"] == [
        "Product needs name",
        "Product needs offers or review or aggregateRating",
    ]
    assert found["missing_recommended"] == ["Product lacks aggregateRating, review"]


def test_nested_needs_only_apply_when_the_parent_is_there() -> None:
    found = kinds(
        ld(
            '{"@type": "Product", "name": "W", "aggregateRating": {"ratingValue": "4"},'
            ' "review": {"author": "Ann"}}'
        )  # a text author counts
    )
    assert found["missing_required"] == [
        "Product needs aggregateRating.ratingCount or aggregateRating.reviewCount",
        "Product needs review.reviewRating.ratingValue",
    ]


def test_a_type_listed_twice_through_subtypes_is_checked_once() -> None:
    found = findings(ld('{"@type": ["Product", "IndividualProduct"], "name": "W"}'))
    assert [f.type for f in found if f.kind == "missing_required"] == ["Product"]


def test_action_annotations_name_the_property_they_annotate() -> None:
    search = (
        '{"@type": "WebSite", "url": "/", "potentialAction": {"@type": "SearchAction",'
        ' "target": "/search?q={q}", "query-input": "required name=q"}}'
    )
    assert findings(ld(search)) == []
    wrong = search.replace("query-input", "price-output")
    assert [f.message for f in findings(ld(wrong))] == [
        "price-output is not a property of SearchAction (at potentialAction)"
    ]


def test_types_without_a_rich_result_and_other_vocabularies_are_not_checked() -> None:
    assert findings(ld('{"@type": "WebSite", "name": "S", "url": "/"}')) == []
    assert findings(ld('{"@context": "http://e.test/v", "@type": "Product", "bogus": "x"}')) == []


# ------------------------------------------------------------------ vocabulary findings


def test_unknown_types_and_properties_are_found_at_any_depth() -> None:
    found = kinds(
        ld(
            '{"@type": "WebPage", "authr": "A", "price": "1", "x:custom": "kept",'
            ' "mainEntity": {"@type": "Prodcut", "nme": "skipped: unknown type"},'
            ' "about": {"nme": "skipped: untyped"},'
            ' "author": {"@type": "Person", "nam": "N"}}'
        )
    )
    assert found["unknown_type"] == ["Prodcut is not a schema.org type (at mainEntity)"]
    assert found["unknown_property"] == [
        "authr is not a schema.org property (on WebPage)",
        "price is not a property of WebPage",
        "nam is not a schema.org property (on Person) (at author)",
    ]


# ------------------------------------------------------------------ conflicts


def test_items_naming_one_entity_must_agree() -> None:
    html = ld(
        '{"@type": "Product", "@id": "/w", "name": "Widget", "sku": "1", "brand": {"name": "A"}}'
    ) + (
        '<div itemscope itemtype="https://schema.org/Product" itemid="https://site.test/w">'
        '<span itemprop="name">Widget Pro</span><span itemprop="sku">1</span>'
        '<span itemprop="brand">A</span></div>'
    )
    conflicts = [f for f in findings(html) if f.kind == "conflicting"]
    assert [(f.type, f.path) for f in conflicts] == [("Product", "name")]
    assert conflicts[0].message == (
        "2 Product items for https://site.test/w disagree on name: 'Widget' vs 'Widget Pro'"
    )


def test_items_are_grouped_by_url_when_there_is_no_id() -> None:
    same = ld(
        '{"@type": "Event", "url": "/gig", "name": "Gig"}',
        '{"@type": "Event", "url": "https://site.test/gig", "name": "Gig"}',
        '{"@type": "Event", "url": " ", "name": "Unnamed"}',
        '{"@type": "Event", "name": "No entity"}',
    )
    assert [f for f in findings(same) if f.kind == "conflicting"] == []
    differ = same.replace('"name": "Gig"}', '"name": "Gig 2"}', 1)
    assert [f.path for f in findings(differ) if f.kind == "conflicting"] == ["name"]


# ------------------------------------------------------------------ the index


def test_index_covers_parsed_html_pages_and_orders_findings() -> None:
    broken = page(
        "/broken",
        structured=extract_structured(
            parse_document(ld('{"a": 1,}', '{"@type": "Prodcut"}')), f"{SITE}/broken"
        ),
    )
    plain = page("/plain", structured=StructuredData())
    unparsed = page("/unparsed")
    index = StructuredIndex(view([broken, plain, unparsed]))
    assert [p.url for p in index.pages] == [f"{SITE}/broken", f"{SITE}/plain"]
    assert [f.kind for f in index.findings_for(f"{SITE}/broken")] == [
        "invalid_json",
        "unknown_type",
    ]
    assert index.findings_for(f"{SITE}/broken", "unknown_type")[0].type == "Prodcut"
    assert index.findings_for(f"{SITE}/plain") == []
    assert index.findings_for(f"{SITE}/unparsed") == []
    assert check_page(unparsed, VOCAB) == []
    assert view([plain]).structured.vocabulary is VOCAB
    assert KINDS[0] == "invalid_json"
