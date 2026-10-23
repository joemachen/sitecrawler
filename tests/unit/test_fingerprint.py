"""Content fingerprints: main text, content hash and SimHash."""

from __future__ import annotations

from sitecrawler.models import Fingerprint
from sitecrawler.parse import fingerprint_text, hamming, main_text, parse_html
from sitecrawler.parse.fingerprint import BITS, shingles, simhash, words
from sitecrawler.parse.html import parse_document
from tests.unit.audit.helpers import long_text

BASE = "https://x.test/p"

PAGE = """
<html><head><title>Title words</title><style>.x{}</style></head>
<body>
  <header><h1>Site name</h1><nav><a href="/">Home</a> <a href="/b">Blog</a></nav></header>
  <div role="navigation">Breadcrumb trail here</div>
  <p>Real content, first sentence. <!-- a comment -->Second sentence.</p>
  <aside>Related posts</aside>
  <script>var x = "not words";</script>
  <div role="complementary">Sidebar</div> tail text
  <footer>Copyright</footer>
</body></html>
"""


def test_main_text_strips_boilerplate_by_tag_and_role() -> None:
    assert main_text(parse_document(PAGE)) == "Real content, first sentence. Second sentence."


def test_main_text_prefers_main_then_role_main_then_body() -> None:
    with_main = "<body><p>outside</p><main><p>inside</p><nav>menu</nav></main></body>"
    assert main_text(parse_document(with_main)) == "inside"
    with_role = '<body><p>outside</p><div role="MAIN"><p>inside</p></div></body>'
    assert main_text(parse_document(with_role)) == "inside"
    assert main_text(parse_document("<p>just body</p>")) == "just body"
    assert main_text(parse_document("")) == ""


def test_main_text_does_not_change_the_document() -> None:
    doc = parse_document(PAGE)
    before = len(list(doc.iter()))
    main_text(doc)
    assert len(list(doc.iter())) == before


def test_words_and_shingles() -> None:
    assert words("Hello, World! It's 2026.") == ["hello", "world", "it", "s", "2026"]
    assert list(shingles(["a", "b", "c", "d"])) == ["a b c", "b c d"]
    assert list(shingles(["a", "b"])) == ["a b"]
    assert list(shingles([])) == []


def test_fingerprint_text_hashes_normalised_words() -> None:
    a = fingerprint_text("Hello,   WORLD! One two three.")
    b = fingerprint_text("hello world one two three")
    assert a == b
    assert a.words == 5
    assert len(a.content_hash) == 64
    assert a.simhash_hex == f"{a.simhash:016x}"
    assert not a.empty
    assert fingerprint_text("...") == Fingerprint()
    assert fingerprint_text("").empty


def test_simhash_distances() -> None:
    base = long_text(300)
    same = fingerprint_text(base)
    assert hamming(same.simhash, fingerprint_text(base).simhash) == 0
    changed = base.replace("word150 word151 word152", "alpha beta gamma")
    near = fingerprint_text(changed)
    assert near.content_hash != same.content_hash
    assert hamming(same.simhash, near.simhash) <= 6
    unrelated = fingerprint_text(long_text(300, prefix="other"))
    assert hamming(same.simhash, unrelated.simhash) > 20
    assert simhash([]) == 0
    assert 0 <= hamming(same.simhash, 0) <= BITS
    reordered = fingerprint_text(" ".join(reversed(base.split())))
    assert hamming(same.simhash, reordered.simhash) > 15  # three-word runs see word order


def test_parse_html_sets_the_fingerprint() -> None:
    page = parse_html(PAGE, BASE)
    assert page.fingerprint == fingerprint_text("Real content, first sentence. Second sentence.")
    assert page.fingerprint.words == 6
    assert page.word_count > page.fingerprint.words  # the whole page counts the menus too
    empty = parse_html("<html><body><nav>only a menu</nav></body></html>", BASE)
    assert empty.fingerprint == Fingerprint()
