from sitecrawler.audit.rules import indexability, robots
from tests.unit.audit.helpers import SITE, blocked, flagged, links, page


def test_directive_rules() -> None:
    pages = [
        page("/noindex", meta_robots="noindex, follow"),
        page("/header", headers={"x-robots-tag": "NOINDEX"}),
        page("/nofollow", meta_robots="nofollow"),
        page("/none", meta_robots="none"),
        page("/conflict", meta_robots="index", headers={"x-robots-tag": "noindex"}),
        page("/conflict2", meta_robots="follow, nofollow"),
        page("/ok", meta_robots="index, follow"),
    ]
    assert set(flagged(robots.Noindex(), pages)) == {"/noindex", "/header", "/conflict"}
    assert set(flagged(robots.Nofollow(), pages)) == {"/nofollow", "/conflict2"}
    assert set(flagged(robots.NoneDirective(), pages)) == {"/none"}
    conflicts = flagged(robots.Conflicting(), pages)
    assert set(conflicts) == {"/conflict", "/conflict2"}
    assert conflicts["/conflict"].message == "index, noindex"


def test_noindex_in_sitemap_and_linked() -> None:
    home = page("/", links=links("/linked", "/plain"))
    pages = [
        home,
        page("/linked", meta_robots="noindex"),
        page("/listed", meta_robots="none"),
        page("/both", meta_robots="noindex"),
        page("/plain"),
    ]
    sitemap = [f"{SITE}/listed", f"{SITE}/both", f"{SITE}/plain"]
    assert set(flagged(robots.NoindexInSitemap(), pages, sitemap_urls=sitemap)) == {
        "/listed",
        "/both",
    }
    linked = flagged(robots.NoindexLinked(), pages)
    assert set(linked) == {"/linked"}
    assert linked["/linked"].message == f"linked from {SITE}/"


def test_blocked_but_linked() -> None:
    home = page("/", links=links("/b", "/b"))
    other = page("/o", links=links("/b"))
    pages = [home, other, blocked("/b"), blocked("/sitemap-only"), page("/ok")]
    hits = flagged(robots.BlockedButLinked(), pages)
    assert set(hits) == {"/b"}
    assert hits["/b"].message == f"linked from {SITE}/ and 2 more"


def test_non_indexable_lists_reasons() -> None:
    pages = [page("/ok"), page("/gone", 404), blocked("/b"), page("/ni", meta_robots="noindex")]
    hits = flagged(indexability.NonIndexable(), pages)
    assert {path: issue.message for path, issue in hits.items()} == {
        "/gone": "status 404",
        "/b": "blocked by robots.txt",
        "/ni": "noindex",
    }
