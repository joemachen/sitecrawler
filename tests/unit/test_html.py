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
