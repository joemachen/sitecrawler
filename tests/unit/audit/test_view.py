from sitecrawler.models import Outcome, PageRecord
from tests.unit.audit.helpers import SITE, blocked, links, page, view


def test_page_lookup_normalises_forms() -> None:
    v = view([page("/a"), page("/b/")])
    assert v.page_for(f"{SITE}/a/") is not None
    assert v.page_for(f"{SITE}/a#x") is not None
    assert v.page_for("https://www.site.test/a?utm_source=x") is not None
    assert v.page_for(f"{SITE}/missing") is None
    assert v.page_for("not a url") is None
    assert v.status_of(f"{SITE}/a") == 200
    assert v.status_of(f"{SITE}/nope") is None


def test_lookup_falls_back_across_schemes() -> None:
    https_view = view([page("/a")])
    assert https_view.page_for("http://site.test/a") is not None
    http_page = PageRecord(
        url="http://site.test/a", outcome=Outcome.FETCHED, depth=0, found_on="s", status_code=200
    )
    http_view = view([http_page])
    assert http_view.page_for("https://site.test/a") is http_page


def test_same_page_and_internal() -> None:
    v = view([page("/a")])
    assert v.same_page(f"{SITE}/a/", "https://www.site.test/a")
    assert not v.same_page(f"{SITE}/a", f"{SITE}/b")
    assert v.is_internal("https://www.site.test/x")
    assert not v.is_internal("https://other.test/x")


def test_html_pages_excludes_errors_and_non_html() -> None:
    pages = [
        page("/ok"),
        page("/missing", 404),
        page("/pdf", content_type="application/pdf"),
        blocked("/blocked"),
        page("/err", None, outcome=Outcome.ERROR),
    ]
    v = view(pages)
    assert [p.url.removeprefix(SITE) for p in v.html_pages] == ["/ok"]


def test_inlinks_index_internal_links_only() -> None:
    home = page("/", links=(*links("/a", "/a", "/b"), *links("/x")))
    other = page("/c", links=links("/a"))
    v = view([home, other])
    assert sorted(i.src for i in v.inlinks_to(f"{SITE}/a")) == [f"{SITE}/", f"{SITE}/", f"{SITE}/c"]
    assert [i.src for i in v.inlinks_to(f"{SITE}/b")] == [f"{SITE}/"]
    assert v.inlinks_to(f"{SITE}/nothing") == []
    assert v.inlinks_to("garbage") == []


def test_external_links_are_not_inlinks() -> None:
    home = page("/", links=links("/a"))
    external = PageRecord(
        url="https://other.test/",
        outcome=Outcome.FETCHED,
        depth=0,
        found_on="list",
        status_code=200,
    )
    v = view([home, external])
    assert v.inlinks_to("https://other.test/") == []


def test_group_and_sitemap() -> None:
    v = view(
        [page("/a", title="Same"), page("/b", title="Same"), page("/c", title="")],
        sitemap_urls=[f"{SITE}/a/", f"{SITE}/zzz", "not a url"],
    )
    groups = v.group_html_pages(lambda p: p.title)
    assert sorted(groups) == ["Same"]
    assert len(groups["Same"]) == 2
    assert v.listed_in_sitemap(f"{SITE}/a")
    assert not v.listed_in_sitemap(f"{SITE}/b")
    assert not v.listed_in_sitemap("nope")
    assert [p.url for p in v.pages_matching(lambda p: p.title == "")] == [f"{SITE}/c"]
