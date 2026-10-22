from sitecrawler.analysis import sitemap_report
from sitecrawler.models import SitemapEntry, SitemapFile
from tests.unit.audit.helpers import SITE, page, view

SM = f"{SITE}/sitemap.xml"
SM2 = f"{SITE}/sitemap-2.xml"


def test_report_counts_files_hosts_uncrawled_and_duplicates() -> None:
    files = [
        SitemapFile(SM, "robots.txt", "urlset", 200, "", 3),
        SitemapFile(f"{SITE}/index.xml", "robots.txt", "index", 200, "", 2),
        SitemapFile(SM2, f"{SITE}/index.xml", "urlset", 200, "", 2),
        SitemapFile(f"{SITE}/gone.xml", f"{SITE}/index.xml", status_code=404, error="status 404"),
    ]
    entries = [
        SitemapEntry(SM, f"{SITE}/a"),
        SitemapEntry(SM, f"{SITE}/b"),
        SitemapEntry(SM, f"{SITE}/never-fetched"),
        SitemapEntry(SM2, f"{SITE}/a/"),
        SitemapEntry(SM2, "https://other.test/x"),
    ]
    v = view([page("/a"), page("/b")], sitemap_entries=entries, sitemap_files=files)
    report = sitemap_report(v)
    assert report.entries == 5
    assert report.pages_listed == 4
    assert [f.url for f in report.readable] == [SM, f"{SITE}/index.xml", SM2]
    assert [f.url for f in report.unreadable] == [f"{SITE}/gone.xml"]
    assert [e.loc for e in report.other_host] == ["https://other.test/x"]
    assert [e.loc for e in report.not_crawled] == [f"{SITE}/never-fetched"]
    assert list(report.duplicates) == [f"{SITE}/a"]
    assert report.found
    assert report.summary() == (
        "Sitemaps: 3 file(s) read, 5 entries naming 4 pages; 1 file(s) unreadable; "
        "1 on other hosts; 1 not crawled; 1 listed more than once."
    )


def test_summary_when_nothing_was_read_or_found() -> None:
    assert sitemap_report(view([page("/")])).summary().startswith("Sitemaps: none read")
    tried = view(
        [page("/")],
        sitemap_files=[SitemapFile(SM, "default", status_code=404, error="status 404")],
    )
    report = sitemap_report(tried)
    assert not report.found
    assert report.summary() == f"Sitemaps: none found (1 tried: {SM})."
