import pytest

from sitecrawler.parse import link_header_rels

BASE = "https://x.test/dir/page"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('<https://x.test/c>; rel="canonical"', {"canonical": "https://x.test/c"}),
        ("</c>; rel=canonical", {"canonical": "https://x.test/c"}),
        (
            '<https://x.test/c>; rel="canonical", </n>; rel="next"; title="n"',
            {"canonical": "https://x.test/c", "next": "https://x.test/n"},
        ),
        (
            '</a>; rel="alternate stylesheet"',
            {"alternate": "https://x.test/a", "stylesheet": "https://x.test/a"},
        ),
        ('</first>; rel="next", </second>; rel="next"', {"next": "https://x.test/first"}),
        ("</x>; type=text/css", {}),
        ("garbage", {}),
        ("", {}),
    ],
)
def test_link_header_rels(value: str, expected: dict[str, str]) -> None:
    assert link_header_rels(value, BASE) == expected
