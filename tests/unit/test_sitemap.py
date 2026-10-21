from sitecrawler.parse import parse_sitemap

NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def test_urlset() -> None:
    xml = f"""<?xml version="1.0"?>
    <urlset {NS}>
      <url><loc> https://x/a </loc></url>
      <url><loc>https://x/b</loc><lastmod>2026-01-01</lastmod></url>
      <url></url>
    </urlset>"""
    doc = parse_sitemap(xml.encode())
    assert doc is not None
    assert doc.kind == "urlset"
    assert doc.locs == ["https://x/a", "https://x/b"]


def test_index() -> None:
    xml = f"""<sitemapindex {NS}>
      <sitemap><loc>https://x/s1.xml</loc></sitemap>
      <sitemap><loc>https://x/s2.xml</loc></sitemap>
    </sitemapindex>"""
    doc = parse_sitemap(xml.encode())
    assert doc is not None
    assert doc.kind == "index"
    assert doc.locs == ["https://x/s1.xml", "https://x/s2.xml"]


def test_garbage_returns_none() -> None:
    assert parse_sitemap(b"<html>not a sitemap") is None
    assert parse_sitemap(b"") is None
