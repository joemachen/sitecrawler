"""Structured data parsing: JSON-LD, microdata and RDFa Lite into one normalised shape."""

from __future__ import annotations

from sitecrawler.models import StructuredData, StructuredItem
from sitecrawler.parse import extract_structured, parse_html
from sitecrawler.parse.html import parse_document
from sitecrawler.parse.structured import schema_name

BASE = "https://x.test/p/"


def parse(html: str) -> StructuredData:
    return extract_structured(parse_document(html), BASE)


def only(html: str) -> StructuredItem:
    found = parse(html)
    assert len(found.items) == 1, found
    return found.items[0]


def ld(body: str) -> str:
    return f'<html><head><script type="application/ld+json">{body}</script></head></html>'


# ------------------------------------------------------------------ names


def test_schema_name_strips_every_schema_org_spelling() -> None:
    for raw in (
        "Product",
        "schema:Product",
        "http://schema.org/Product",
        "https://schema.org/Product",
        "https://www.schema.org/Product",
        "http://schema.org/Product/",
    ):
        assert schema_name(raw) == "Product", raw
    assert schema_name("http://data-vocabulary.org/Breadcrumb") is None
    assert schema_name("og:title") is None


# ------------------------------------------------------------------ JSON-LD


def test_jsonld_normalises_values_to_lists_of_text_or_nodes() -> None:
    item = only(
        ld(
            """{"@context": "https://schema.org", "@type": "Product", "@id": "#p",
            "name": "Widget", "sku": 42, "isFamilyFriendly": true, "gtin": null,
            "image": ["a.jpg", "b.jpg"],
            "offers": {"@type": "Offer", "price": 9.5, "priceCurrency": "USD"},
            "description": {"@value": "Plain", "@language": "en"}}"""
        )
    )
    assert item.format == "json-ld"
    assert item.types == ("Product",)
    assert item.data == {
        "@type": ["Product"],
        "@id": ["#p"],
        "name": ["Widget"],
        "sku": ["42"],
        "isFamilyFriendly": ["true"],
        "image": ["a.jpg", "b.jpg"],
        "offers": [{"@type": ["Offer"], "price": ["9.5"], "priceCurrency": ["USD"]}],
        "description": ["Plain"],
    }


def test_jsonld_graph_and_top_level_arrays_give_one_item_each() -> None:
    graph = parse(
        ld(
            """{"@context": "https://schema.org", "@graph": [
              {"@type": "Organization", "name": "Acme"},
              {"@type": "WebSite", "name": "Acme site"}]}"""
        )
    )
    assert [i.types for i in graph.items] == [("Organization",), ("WebSite",)]
    array = parse(
        ld(
            """[{"@context": "https://schema.org", "@type": "Article"},
                {"@context": "https://schema.org", "@type": "BreadcrumbList"}]"""
        )
    )
    assert [i.types for i in array.items] == [("Article",), ("BreadcrumbList",)]
    assert array.types == ("Article", "BreadcrumbList")
    assert array.formats == ("json-ld",)


def test_jsonld_prefixed_names_and_type_lists() -> None:
    item = only(
        ld(
            """{"@context": {"schema": "https://schema.org/"},
                "@type": ["schema:Product", "https://schema.org/Thing"],
                "schema:name": "W"}"""
        )
    )
    assert item.types == ("Product", "Thing")
    assert item.data["name"] == ["W"]


def test_jsonld_other_vocabularies_keep_their_iris() -> None:
    item = only(ld('{"@context": "http://data-vocabulary.org", "@type": "Breadcrumb"}'))
    assert item.types == ("http://data-vocabulary.org/Breadcrumb",)
    vocab = only(ld('{"@context": {"@vocab": "https://example.test/v#"}, "@type": "Thing"}'))
    assert vocab.types == ("https://example.test/v#Thing",)
    listed = only(
        ld('{"@context": ["https://schema.org", {"x": "https://e.test/"}], "@type": "Event"}')
    )
    assert listed.types == ("Event",)
    bare = only(ld('{"@type": "Recipe"}'))
    assert bare.types == ("Recipe",)  # no context: read as schema.org, as Google does


def test_jsonld_invalid_json_is_an_error_with_its_page_line() -> None:
    html = (
        "<html><head>\n"
        '<script type="application/ld+json">\n'
        '{"@type": "Product",\n'
        ' "name": "W"\n'
        ' "sku": "1"}\n'
        "</script></head></html>"
    )
    found = parse(html)
    assert found.items == ()
    (error,) = found.errors
    assert error.line == 5
    assert error.message.startswith("Expecting ',' delimiter")
    assert "line 5" in error.message
    assert not found.empty


def test_jsonld_ignores_blank_blocks_scalars_and_other_script_types() -> None:
    found = parse(
        '<script type="application/ld+json">  </script>'
        '<script type="application/ld+json">"just a string"</script>'
        '<script type="application/json">{"@type": "Product"}</script>'
        '<script type="APPLICATION/LD+JSON ">{"@type": "Event"}</script>'
    )
    assert [i.types for i in found.items] == [("Event",)]
    assert found.errors == ()


def test_jsonld_line_is_the_script_line() -> None:
    html = '<html>\n<head>\n\n<script type="application/ld+json">{"@type": "Event"}</script>'
    assert only(html).line == 4


# ------------------------------------------------------------------ microdata

MICRODATA = """
<html><body>
<div itemscope itemtype="https://schema.org/Product" itemid="urn:sku:1">
  <h1 itemprop="name">  Widget
    deluxe </h1>
  <img itemprop="image" src="w.jpg">
  <a itemprop="url" href="/products/widget">link</a>
  <meta itemprop="sku" content="W-1">
  <time itemprop="releaseDate" datetime="2026-01-02">Jan 2</time>
  <time itemprop="productionDate">2025</time>
  <data itemprop="gtin" value="123">one two three</data>
  <span itemprop="brand manufacturer">Acme</span>
  <div itemprop="offers" itemscope itemtype="http://schema.org/Offer">
    <span itemprop="price">9.99</span>
    <link itemprop="availability" href="https://schema.org/InStock">
  </div>
  <div itemscope itemtype="https://schema.org/Review"><span itemprop="name">Inner</span></div>
</div>
</body></html>
"""


def test_microdata_values_follow_the_element_rules() -> None:
    found = parse(MICRODATA)
    product, review = found.items
    assert product.format == "microdata"
    assert product.data == {
        "@type": ["Product"],
        "@id": ["urn:sku:1"],
        "name": ["Widget deluxe"],
        "image": ["https://x.test/p/w.jpg"],
        "url": ["https://x.test/products/widget"],
        "sku": ["W-1"],
        "releaseDate": ["2026-01-02"],
        "productionDate": ["2025"],
        "gtin": ["123"],
        "brand": ["Acme"],
        "manufacturer": ["Acme"],
        "offers": [
            {
                "@type": ["Offer"],
                "price": ["9.99"],
                "availability": ["https://schema.org/InStock"],
            }
        ],
    }
    # An itemscope without itemprop inside another item is an item of its own.
    assert review.data == {"@type": ["Review"], "name": ["Inner"]}
    assert product.line == 3


def test_microdata_item_without_type_and_full_iri_properties() -> None:
    item = only(
        '<p itemscope><span itemprop="https://schema.org/name">N</span>'
        '<span itemprop="http://e.test/x">X</span></p>'
    )
    assert item.data == {"name": ["N"], "http://e.test/x": ["X"]}
    assert item.types == ()


def test_microdata_other_vocabulary_types_keep_their_iris() -> None:
    item = only('<p itemscope itemtype="http://data-vocabulary.org/Breadcrumb"></p>')
    assert item.types == ("http://data-vocabulary.org/Breadcrumb",)


# ------------------------------------------------------------------ RDFa Lite

RDFA = """
<html><body>
<div vocab="https://schema.org/" typeof="Article" resource="#a">
  <h1 property="headline">Title</h1>
  <a property="url" href="/a">self</a>
  <meta property="datePublished" content="2026-10-01">
  <div property="author" typeof="Person"><span property="name">Ann</span></div>
  <span property="og:ignored">x</span>
</div>
<p typeof="schema:Event" prefix="schema: https://schema.org/">
  <span property="schema:name">Gig</span></p>
<div vocab="http://e.test/v/" typeof="Thing"></div>
<span property="name">no item around me</span>
</body></html>
"""


def test_rdfa_lite_items_nested_items_and_values() -> None:
    found = parse(RDFA)
    article, event, other = found.items
    assert article.format == "rdfa"
    assert article.data == {
        "@type": ["Article"],
        "@id": ["#a"],
        "headline": ["Title"],
        "url": ["https://x.test/a"],
        "datePublished": ["2026-10-01"],
        "author": [{"@type": ["Person"], "name": ["Ann"]}],
        "og:ignored": ["x"],
    }
    assert event.data == {"@type": ["Event"], "name": ["Gig"]}
    assert other.types == ("http://e.test/v/Thing",)


def test_meta_property_tags_without_an_item_are_not_structured_data() -> None:
    found = parse('<head><meta property="og:url" content="https://x.test/"></head>')
    assert found.empty
    assert found.types == ()


# ------------------------------------------------------------------ parse_html


def test_parse_html_sets_structured_before_scripts_are_stripped() -> None:
    page = parse_html(ld('{"@type": "Event", "name": "Gig"}') + "<p>two words</p>", BASE)
    assert page.structured is not None
    assert page.structured.types == ("Event",)
    assert page.word_count == 2
    plain = parse_html("<p>nothing</p>", BASE)
    assert plain.structured == StructuredData()
