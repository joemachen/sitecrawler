from sitecrawler.parse import parse_html

BASE = "https://example.com/dir/page"


def test_extracts_core_fields() -> None:
    html = """
    <html><head>
      <title>  Hello   World </title>
      <meta name="DESCRIPTION" content=" A   description ">
      <link rel="canonical" href="/canon">
    </head><body>
      <h1>First <b>heading</b></h1><h1>Second</h1>
      <p>one two three</p>
      <script>ignored words here</script>
      <style>.x{}</style>
    </body></html>
    """
    page = parse_html(html, BASE)
    assert page.title == "Hello World"
    assert page.meta_description == "A description"
    assert page.h1 == "First heading"
    assert page.canonical == "https://example.com/canon"
    # "Hello World" + "First heading" + "Second" + "one two three" = 8 words
    assert page.word_count == 8


def test_missing_fields_are_empty() -> None:
    page = parse_html("<html><body><p>hi</p></body></html>", BASE)
    assert page.title == ""
    assert page.meta_description == ""
    assert page.h1 == ""
    assert page.canonical == ""
    assert page.links == []


def test_links_are_absolutised_and_filtered() -> None:
    html = """
    <a href="rel">r</a>
    <a href="/abs">a</a>
    <a href="https://other.test/x">o</a>
    <a href="#frag">f</a>
    <a href="mailto:a@b.c">m</a>
    <a href="tel:123">t</a>
    <a href="javascript:void(0)">j</a>
    <a href="   ">blank</a>
    <a>no href</a>
    """
    page = parse_html(html, BASE)
    assert page.links == [
        "https://example.com/dir/rel",
        "https://example.com/abs",
        "https://other.test/x",
    ]


def test_canonical_with_multiple_rel_values() -> None:
    html = '<link rel="alternate canonical" href="https://example.com/c">'
    assert parse_html(html, BASE).canonical == "https://example.com/c"


def test_headings_metas_and_lang() -> None:
    html = """
    <html lang="en-GB"><head>
      <meta name="ROBOTS" content="noindex, follow">
    </head><body>
      <h1>One</h1><h2>Two a</h2><h1>One again</h1><h2>Two b</h2>
    </body></html>
    """
    page = parse_html(html, BASE)
    assert page.lang == "en-GB"
    assert page.meta_robots == "noindex, follow"
    assert page.h1s == ["One", "One again"]
    assert page.h2s == ["Two a", "Two b"]
    assert page.h1 == "One"


def test_anchors_carry_text_and_rel() -> None:
    html = """
    <a href="/a" rel="nofollow noopener">  Click <b>here</b> </a>
    <a href="/b">plain</a>
    """
    page = parse_html(html, BASE)
    assert [a.href for a in page.anchors] == page.links
    assert page.anchors[0].text == "Click here"
    assert page.anchors[0].rel == "nofollow noopener"
    assert page.anchors[0].nofollow
    assert not page.anchors[1].nofollow


def test_anchor_position_is_the_nearest_sectioning_ancestor() -> None:
    html = """
    <header><nav><a href="/n">N</a></nav><a href="/h">H</a></header>
    <main><a href="/b">B</a><div role="complementary"><a href="/s">S</a></div></main>
    <footer><nav><a href="/f">F</a></nav><a href="/g">G</a></footer>
    <div role="navigation"><a href="/r">R</a></div>
    <div role="banner"><a href="/x">X</a></div><div role="contentinfo"><a href="/y">Y</a></div>
    """
    page = parse_html(html, BASE)
    assert [a.position for a in page.anchors] == [
        "nav", "header", "body", "aside", "nav", "footer", "nav", "header", "footer",
    ]  # fmt: skip


def test_br_and_nested_tags_separate_words() -> None:
    page = parse_html("<h1>Hello<br>World</h1><h2>a<b>b</b>c</h2>", BASE)
    assert page.h1 == "Hello World"
    assert page.h2s == ["a b c"]


def test_comments_and_noscript_are_not_text() -> None:
    html = "<p>one <!-- hidden words --> two</p><noscript>three</noscript> four"
    assert parse_html(html, BASE).word_count == 3


def test_empty_and_xml_prologue_documents() -> None:
    assert parse_html("", BASE) == parse_html("   \n", BASE)
    assert parse_html("", BASE).word_count == 0
    xhtml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" lang="fr"><head><title>X</title></head>'
        "<body><h1>Un</h1></body></html>"
    )
    page = parse_html(xhtml, BASE)
    assert page.title == "X"
    assert page.lang == "fr"
    assert page.h1 == "Un"


def test_og_url_and_meta_name_matching_are_tolerant() -> None:
    html = """
    <meta property="og:url" content=" /og ">
    <meta name=" Description " content="desc">
    <meta name="description" content="second">
    """
    page = parse_html(html, BASE)
    assert page.og_url == "https://example.com/og"
    assert page.meta_description == "desc"
    assert page.meta_description_count == 2
