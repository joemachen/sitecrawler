from sitecrawler.audit.rules import sitemaps
from sitecrawler.models import SitemapEntry
from tests.unit.audit.helpers import SITE, blocked, flagged, links, page

SM = f"{SITE}/sitemap.xml"
SM2 = f"{SITE}/sitemap-2.xml"


def _entries(*locs: str, file: str = SM) -> list[SitemapEntry]:
    return [SitemapEntry(file, f"{SITE}{loc}") for loc in locs]


def test_orphan_is_an_indexable_sitemap_page_nothing_links_to() -> None:
    home = page("/", links=links("/linked", "/self-only"))
    pages = [
        home,
        page("/linked"),
        page("/orphan", found_on=f"sitemap:{SM}"),
        page("/self-only", links=links("/self-only")),
        page("/noindex-orphan", meta_robots="noindex"),
        page("/unlisted"),
        page("/orphan-self-link", found_on="list", links=links("/orphan-self-link")),
    ]
    entries = _entries(
        "/", "/linked", "/orphan", "/noindex-orphan", "/orphan-self-link", "/self-only"
    )
    hits = flagged(sitemaps.Orphan(), pages, sitemap_entries=entries)
    assert set(hits) == {"/orphan", "/orphan-self-link"}  # self-links do not count
    assert hits["/orphan"].message == "listed in sitemap.xml, linked from nowhere"
    # the start page is reachable by definition, however it is found
    start = [page("/", found_on="start")]
    assert flagged(sitemaps.Orphan(), start, sitemap_entries=_entries("/")) == {}


def test_non_indexable_gives_the_reason() -> None:
    pages = [
        page("/ok"),
        page("/gone", 404),
        blocked("/b"),
        page("/ni", meta_robots="noindex"),
        page("/canon", canonical=f"{SITE}/ok"),
        page("/moved", 301, final_url=f"{SITE}/ok"),
        page("/unlisted", 404),
    ]
    entries = _entries("/ok", "/gone", "/b", "/ni", "/canon", "/moved")
    hits = flagged(sitemaps.NonIndexable(), pages, sitemap_entries=entries)
    assert {path: issue.message for path, issue in hits.items()} == {
        "/gone": "status 404",
        "/b": "blocked by robots.txt",
        "/ni": "noindex",
        "/canon": f"canonicalised to {SITE}/ok",
        "/moved": f"redirects to {SITE}/ok",
    }


def test_missing_is_every_indexable_200_page_not_listed_once_a_sitemap_was_read() -> None:
    pages = [
        page("/listed"),
        page("/unlisted"),
        page("/unlisted-ni", meta_robots="noindex"),
        page("/unlisted-204", 204),
    ]
    assert set(flagged(sitemaps.Missing(), pages, sitemap_entries=_entries("/listed"))) == {
        "/unlisted"
    }
    assert flagged(sitemaps.Missing(), pages) == {}  # no sitemap: nothing to be missing from


def test_duplicate_counts_entries_across_and_within_files() -> None:
    pages = [page("/twice"), page("/variants"), page("/once"), page("/same-file")]
    entries = [
        *_entries("/twice", "/once", "/same-file", "/same-file"),
        *_entries("/twice", file=SM2),
        SitemapEntry(SM2, f"{SITE}/variants/"),
        SitemapEntry(SM2, "https://www.site.test/variants"),
    ]
    hits = flagged(sitemaps.Duplicate(), pages, sitemap_entries=entries)
    assert {path: issue.message for path, issue in hits.items()} == {
        "/twice": "listed 2 times: sitemap.xml, sitemap-2.xml",
        "/variants": "listed 2 times: sitemap-2.xml",
        "/same-file": "listed 2 times: sitemap.xml",
    }


def test_bare_sitemap_urls_still_work_for_membership() -> None:
    pages = [page("/a", found_on="sitemap:?"), page("/b")]
    hits = flagged(sitemaps.Missing(), pages, sitemap_urls=[f"{SITE}/a"])
    assert set(hits) == {"/b"}
    orphan = flagged(sitemaps.Orphan(), pages, sitemap_urls=[f"{SITE}/a"])
    assert orphan["/a"].message == "listed in , linked from nowhere"
