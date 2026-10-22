"""The sitemap writer: valid against the sitemaps.org schemas, split when too large."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from sitecrawler.export import (
    SitemapUrl,
    lastmod_from_header,
    site_origin,
    sitemap_urls_for,
    write_sitemap,
)
from tests.unit.audit.helpers import SITE, blocked, page, view

SCHEMAS = Path(__file__).parent.parent / "fixtures" / "schemas"


def validate(path: Path, schema: str) -> etree._ElementTree:
    """Parse ``path`` and assert it validates against ``schema`` (sitemap or siteindex)."""
    xsd = etree.XMLSchema(etree.parse(SCHEMAS / f"{schema}.xsd"))
    doc = etree.parse(path)
    xsd.assertValid(doc)
    return doc


def locs(doc: etree._ElementTree) -> list[str]:
    return [str(el.text) for el in doc.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]


def test_single_sitemap_validates_and_escapes(tmp_path: Path) -> None:
    out = tmp_path / "sitemap.xml"
    urls = [
        SitemapUrl("https://example.com/"),
        SitemapUrl("https://example.com/a?x=1&y=2", "2026-10-21T10:00:00+00:00"),
    ]
    assert write_sitemap(urls, out) == [out]
    doc = validate(out, "sitemap")
    assert locs(doc) == ["https://example.com/", "https://example.com/a?x=1&y=2"]
    assert out.read_text(encoding="utf-8").count("<lastmod>") == 1
    assert "&amp;" in out.read_text(encoding="utf-8")


def test_over_the_limit_becomes_an_index_with_parts(tmp_path: Path) -> None:
    out = tmp_path / "sitemap.xml"
    urls = [SitemapUrl(f"https://example.com/p{i}") for i in range(5)]
    written = write_sitemap(urls, out, base_url="https://example.com/", max_urls=2)
    assert written == [out, *(tmp_path / f"sitemap-{n}.xml" for n in (1, 2, 3))]
    index = validate(out, "siteindex")
    assert locs(index) == [f"https://example.com/sitemap-{n}.xml" for n in (1, 2, 3)]
    parts = [locs(validate(p, "sitemap")) for p in written[1:]]
    assert [len(p) for p in parts] == [2, 2, 1]
    assert [u for part in parts for u in part] == [u.loc for u in urls]


def test_index_needs_a_base_url(tmp_path: Path) -> None:
    urls = [SitemapUrl("https://example.com/a"), SitemapUrl("https://example.com/b")]
    with pytest.raises(ValueError, match="base_url"):
        write_sitemap(urls, tmp_path / "s.xml", max_urls=1)


def test_sitemap_urls_for_keeps_indexable_200_pages_only() -> None:
    pages = [
        page("/b", headers={"last-modified": "Wed, 21 Oct 2026 10:00:00 GMT"}),
        page("/a"),
        page("/gone", 404),
        page("/ni", meta_robots="noindex"),
        page("/moved", 301, final_url=f"{SITE}/a"),
        page("/empty", 204),
        blocked("/blocked"),
    ]
    urls = sitemap_urls_for(view(pages))
    assert urls == [SitemapUrl(f"{SITE}/a"), SitemapUrl(f"{SITE}/b")]
    with_dates = sitemap_urls_for(view(pages), lastmod=True)
    assert [u.lastmod for u in with_dates] == ["", "2026-10-21T10:00:00+00:00"]


def test_site_origin() -> None:
    assert site_origin("https://www.example.com/deep/page?x=1") == "https://www.example.com/"
    assert site_origin("") == ""


def test_lastmod_from_header() -> None:
    assert lastmod_from_header("Wed, 21 Oct 2026 10:00:00 GMT") == "2026-10-21T10:00:00+00:00"
    assert lastmod_from_header("") == ""
    assert lastmod_from_header("yesterday") == ""
