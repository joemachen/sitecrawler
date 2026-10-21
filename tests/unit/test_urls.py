import pytest

from sitecrawler.crawl.urls import looks_like_page, normalize, same_site, strip_www


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Example.com/", "https://example.com/"),
        ("https://www.example.com/a/", "https://example.com/a"),
        ("https://example.com//a//b", "https://example.com/a/b"),
        ("https://example.com/a#frag", "https://example.com/a"),
        ("https://example.com/a?utm_source=x&b=1", "https://example.com/a"),
        ("http://example.com/a", "http://example.com/a"),
        ("  https://example.com/a  ", "https://example.com/a"),
        ("https://example.com", "https://example.com/"),
    ],
)
def test_normalize_default(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "raw", ["mailto:a@b.c", "ftp://x/y", "/relative", "", "javascript:void(0)"]
)
def test_normalize_rejects_non_http(raw: str) -> None:
    assert normalize(raw) is None


def test_normalize_keep_query_sorts_and_strips_tracking() -> None:
    url = "https://example.com/p?z=1&a=2&utm_campaign=spring&fbclid=abc"
    assert normalize(url, keep_query=True) == "https://example.com/p?a=2&z=1"


def test_normalize_forces_scheme() -> None:
    assert normalize("https://example.com/a", scheme="http") == "http://example.com/a"
    assert normalize("http://example.com/a", scheme="https") == "https://example.com/a"


def test_normalize_keeps_port() -> None:
    assert normalize("http://localhost:8080/x/") == "http://localhost:8080/x"


def test_strip_www_and_same_site() -> None:
    assert strip_www("WWW.Example.com") == "example.com"
    assert same_site("www.example.com", "example.com")
    assert not same_site("blog.example.com", "example.com")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x/a", True),
        ("https://x/a.html", True),
        ("https://x/a.pdf", False),
        ("https://x/img/logo.PNG", False),
        ("https://x/v1.2/page", True),  # dot in a directory, not an extension
        ("https://x/file.unknownext", True),
    ],
)
def test_looks_like_page(url: str, expected: bool) -> None:
    assert looks_like_page(url) is expected


def test_parse_url_list_skips_blanks_comments_and_duplicates() -> None:
    from sitecrawler.crawl.urls import parse_url_list

    lines = [
        "# my list",
        "",
        "https://a.test/one  ",
        "   ",
        "https://a.test/two",
        "https://a.test/one",
        "\thttps://b.test/\r",
    ]
    assert parse_url_list(lines) == ["https://a.test/one", "https://a.test/two", "https://b.test/"]
