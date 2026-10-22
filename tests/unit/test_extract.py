"""The extractor grammar, the TOML loader and running extractors over HTML."""

from __future__ import annotations

import pytest

from sitecrawler.models import ExtractorSpec, SearchSpec
from sitecrawler.parse import (
    compile_extractors,
    load_extract_toml,
    parse_extractor,
    parse_search,
    parse_searches,
)
from sitecrawler.parse.extract import make_extractor

HTML = """
<!doctype html>
<html lang="en">
<head>
  <title>Widget</title>
  <script>
    gtag('config', 'G-7F3K9Q2M1X');
  </script>
</head>
<body>
  <h1>Widget</h1>
  <p>Only <span class="price">$19.99</span> while <!-- comment --> stocks last.</p>
  <span class="price"></span>
  <span class="price">  $5.50  </span>
  <dd data-sku="WID-001">WID-001</dd>
  <img src="/a.png" alt="A"><img src="/b.png">
  <article><p>Hello &amp; <b>bold</b></p>tail</article>
</body>
</html>
"""


# ----------------------------------------------------------------- grammar
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("price=css:.price", ExtractorSpec("price", "css", ".price")),
        ("price = css: .price ", ExtractorSpec("price", "css", ".price")),
        ("img=css[attr=src,all]:img", ExtractorSpec("img", "css", "img", "attr", "src", True)),
        ("body=xpath[html]://article", ExtractorSpec("body", "xpath", "//article", "html")),
        (
            "sku=xpath://*[@data-sku]/@data-sku",
            ExtractorSpec("sku", "xpath", "//*[@data-sku]/@data-sku"),
        ),
        ("ga=regex:G-[A-Z0-9]{6,}", ExtractorSpec("ga", "regex", "G-[A-Z0-9]{6,}")),
        ("ga-id=regex[all]:x=(\\d+)", ExtractorSpec("ga-id", "regex", "x=(\\d+)", all=True)),
        ("t=css[all,first,text]:title", ExtractorSpec("t", "css", "title")),
    ],
)  # fmt: skip
def test_parse_extractor(text: str, expected: ExtractorSpec) -> None:
    assert parse_extractor(text) == expected


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("css:.price", "expected NAME=KIND:EXPRESSION"),
        ("1price=css:.price", "expected NAME=KIND:EXPRESSION"),
        ("price=.price", "css, xpath or regex after the ="),
        ("price=jq:.price", "unknown kind 'jq'"),
        ("price=css[bold]:.price", "unknown modifier 'bold'"),
        ("price=css[attr=]:.price", "needs the attribute name"),
        ("price=css:", "expression is empty"),
        ("price=css:p[", "invalid CSS selector"),
        ("price=xpath://a[", "invalid XPath expression"),
        ("price=regex:(", "invalid regex"),
        ("price=regex[html]:x", "does not apply"),
        ("price=regex[attr=src]:x", "does not apply"),
    ],
)
def test_parse_extractor_errors(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_extractor(text)


def test_make_extractor_checks_loose_parts() -> None:
    assert make_extractor("a", "css", "p", attr="href") == ExtractorSpec(
        "a", "css", "p", "attr", "href"
    )
    with pytest.raises(ValueError, match="unknown mode"):
        make_extractor("a", "css", "p", mode="outer")
    with pytest.raises(ValueError, match="unknown kind"):
        make_extractor("a", "sql", "p")
    with pytest.raises(ValueError, match="names are letters"):
        make_extractor("a b", "css", "p")


def test_parse_search() -> None:
    assert parse_search("G-[A-Z0-9]+") == SearchSpec("search", "G-[A-Z0-9]+")
    assert parse_search("ga=G-[A-Z0-9]+") == SearchSpec("ga", "G-[A-Z0-9]+")
    assert parse_search("x", default_name="other") == SearchSpec("other", "x")
    assert parse_searches(["a", "named=b", "c"]) == (
        SearchSpec("search", "a"),
        SearchSpec("named", "b"),
        SearchSpec("search2", "c"),
    )
    with pytest.raises(ValueError, match="invalid regular expression"):
        parse_search("ga=(")
    with pytest.raises(ValueError, match="pattern is empty"):
        parse_search("ga=")


def test_compile_rejects_a_name_used_twice() -> None:
    with pytest.raises(ValueError, match="used by more than one"):
        compile_extractors([parse_extractor("ga=css:p")], [parse_search("ga=x")])
    assert not compile_extractors()


# -------------------------------------------------------------------- TOML
TOML = """
[extract.price]
css = ".price"

[extract.img]
css = "img"
attr = "src"
all = true

[extract.body]
xpath = "//article"
mode = "html"

[extract]
sku = "xpath://*[@data-sku]/@data-sku"

[search]
gtag = "gtag\\\\('config'"

[search.ga]
pattern = "G-[A-Z0-9]{6,}"
"""


def test_load_extract_toml() -> None:
    extractors, searches = load_extract_toml(TOML)
    assert extractors == (
        ExtractorSpec("price", "css", ".price"),
        ExtractorSpec("img", "css", "img", "attr", "src", True),
        ExtractorSpec("body", "xpath", "//article", "html"),
        ExtractorSpec("sku", "xpath", "//*[@data-sku]/@data-sku"),
    )
    assert searches == (SearchSpec("gtag", "gtag\\('config'"), SearchSpec("ga", "G-[A-Z0-9]{6,}"))
    assert load_extract_toml("") == ((), ())


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[extract\n", "invalid TOML"),
        ("[other]\nx = 1", "unknown top-level keys"),
        ("extract = 1", r"\[extract\] must be a table"),
        ("[extract]\nprice = 1", r"\[extract.price\] must be a table or"),
        ("[extract.price]\nselector = '.p'", "unknown keys"),
        ("[extract.price]\nmode = 'text'", "exactly one of css, xpath or regex"),
        ("[extract.price]\ncss = '.p'\nxpath = '//p'", "exactly one of css, xpath or regex"),
        ("[extract.price]\ncss = 1", "must be strings"),
        ("[extract.price]\ncss = '.p'\nall = 'yes'", "must be strings"),
        ("[search]\nga = 1", r"\[search.ga\] must be a pattern string"),
        ("[search.ga]\nregex = 'x'", r"\[search.ga\] must be a pattern string"),
    ],
)
def test_load_extract_toml_errors(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_extract_toml(text)


# ----------------------------------------------------------------- running
def _run(*specs: str, searches: tuple[str, ...] = ()) -> dict[str, tuple[tuple[str, ...], int]]:
    extractors = compile_extractors(
        [parse_extractor(s) for s in specs], [parse_search(s) for s in searches]
    )
    return {e.name: (e.values, e.count) for e in extractors.run(HTML)}


def test_css_text_first_and_all() -> None:
    assert _run("price=css:.price") == {"price": (("$19.99",), 2)}
    assert _run("price=css[all]:.price") == {"price": (("$19.99", "$5.50"), 2)}


def test_css_attribute_and_inner_html() -> None:
    assert _run("img=css[attr=src,all]:img")["img"] == (("/a.png", "/b.png"), 2)
    assert _run("alt=css[attr=alt,all]:img")["alt"] == (("A",), 1)
    assert _run("body=css[html]:article")["body"] == (("<p>Hello &amp; <b>bold</b></p>tail",), 1)
    assert _run("p=css[html]:article p")["p"] == (("Hello &amp; <b>bold</b>",), 1)


def test_xpath_strings_elements_and_scalars() -> None:
    assert _run("sku=xpath://*[@data-sku]/@data-sku")["sku"] == (("WID-001",), 1)
    assert _run("h1=xpath://h1")["h1"] == (("Widget",), 1)
    assert _run("n=xpath:count(//img)")["n"] == (("2",), 1)
    assert _run("avg=xpath:count(//img) div 4")["avg"] == (("0.5",), 1)
    assert _run("has=xpath:boolean(//h1)")["has"] == (("true",), 1)
    assert _run("text=xpath[all]://body/p/text()")["text"] == (("Only", "while", "stocks last."), 3)


def test_regex_group_or_whole_match() -> None:
    assert _run("ga=regex:gtag\\('config',\\s*'(G-[A-Z0-9]+)'")["ga"] == (("G-7F3K9Q2M1X",), 1)
    assert _run("id=regex:G-[A-Z0-9]{6,}")["id"] == (("G-7F3K9Q2M1X",), 1)
    assert _run("none=regex:UA-\\d+")["none"] == ((), 0)


def test_search_is_case_insensitive_and_counts() -> None:
    results = _run(searches=("ga=g-[a-z0-9]{6,}", "missing=UA-\\d+", 'price=class="price"'))
    assert results["ga"] == (("G-7F3K9Q2M1X",), 1)
    assert results["missing"] == ((), 0)
    assert results["price"] == (('class="price"',), 3)


def test_results_follow_config_order_and_columns() -> None:
    extractors = compile_extractors(
        [parse_extractor("b=css:h1"), parse_extractor("a=css:h1")], [parse_search("s=x")]
    )
    assert [e.name for e in extractors.run(HTML)] == ["b", "a", "s"]
    assert [e.kind for e in extractors.run(HTML)] == ["css", "css", "search"]
    assert extractors.columns == ("extract_b", "extract_a", "search_s")
    assert [e.column for e in extractors.run(HTML)] == ["extract_b", "extract_a", "search_s"]


def test_empty_document_yields_no_matches() -> None:
    extractors = compile_extractors([parse_extractor("p=css:p")], [parse_search("x")])
    assert [(e.values, e.count) for e in extractors.run("")] == [((), 0), ((), 0)]
