import gzip

import pytest

from sitecrawler.models import SitemapEntry
from sitecrawler.parse import parse_sitemap

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def test_urlset_keeps_every_field() -> None:
    xml = f"""<?xml version="1.0"?>
    <urlset {NS}>
      <url><loc> https://x/a </loc></url>
      <url>
        <loc>https://x/b</loc>
        <lastmod>2026-01-01</lastmod>
        <changefreq>daily</changefreq>
        <priority>0.5</priority>
      </url>
      <url></url>
      <url><lastmod>2026-01-01</lastmod></url>
    </urlset>"""
    doc = parse_sitemap(xml.encode(), "https://x/sitemap.xml")
    assert doc is not None
    assert doc.kind == "urlset"
    assert doc.locs == ["https://x/a", "https://x/b"]
    assert doc.entries == [
        SitemapEntry("https://x/sitemap.xml", "https://x/a"),
        SitemapEntry("https://x/sitemap.xml", "https://x/b", "2026-01-01", "daily", "0.5"),
    ]


def test_index() -> None:
    xml = f"""<sitemapindex {NS}>
      <sitemap><loc>https://x/s1.xml</loc><lastmod>2026-02-02</lastmod></sitemap>
      <sitemap><loc>https://x/s2.xml</loc></sitemap>
    </sitemapindex>"""
    doc = parse_sitemap(xml.encode())
    assert doc is not None
    assert doc.kind == "index"
    assert doc.locs == ["https://x/s1.xml", "https://x/s2.xml"]
    assert doc.entries[0].lastmod == "2026-02-02"


def test_gzip_is_transparent(monkeypatch: pytest.MonkeyPatch) -> None:
    xml = f"<urlset {NS}><url><loc>https://x/z</loc></url></urlset>".encode()
    doc = parse_sitemap(gzip.compress(xml))
    assert doc is not None
    assert doc.locs == ["https://x/z"]
    assert parse_sitemap(b"\x1f\x8bnot really gzip") is None
    monkeypatch.setattr("sitecrawler.parse.sitemap.GZIP_MAX_BYTES", len(xml) - 1)
    assert parse_sitemap(gzip.compress(xml)) is None  # a gzip bomb is not a sitemap


def test_relative_locs_resolve_and_repeats_collapse() -> None:
    xml = f"""<urlset {NS}>
      <url><loc>/a</loc></url>
      <url><loc>b?x=1</loc></url>
      <url><loc>/a</loc><lastmod>2026-01-01</lastmod></url>
    </urlset>"""
    doc = parse_sitemap(xml.encode(), "https://x/dir/sitemap.xml")
    assert doc is not None
    assert doc.locs == ["https://x/a", "https://x/dir/b?x=1"]
    assert doc.entries[0].lastmod == ""  # the first listing wins
    bare = parse_sitemap(xml.encode())
    assert bare is not None
    assert bare.locs == ["/a", "b?x=1"]  # nothing to resolve against


def test_namespace_is_optional_and_other_namespaces_are_tolerated() -> None:
    bare = b"<urlset><url><loc>https://x/bare</loc></url></urlset>"
    doc = parse_sitemap(bare)
    assert doc is not None
    assert doc.locs == ["https://x/bare"]
    http = b'<urlset xmlns="http://www.google.com/schemas/sitemap/0.84"><url><loc>https://x/g</loc></url></urlset>'
    doc = parse_sitemap(http)
    assert doc is not None
    assert doc.locs == ["https://x/g"]


def test_garbage_returns_none() -> None:
    assert parse_sitemap(b"<html>not a sitemap") is None
    assert parse_sitemap(b"<rss><channel/></rss>") is None
    assert parse_sitemap(b"") is None
