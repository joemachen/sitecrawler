from sitecrawler.audit.rules.links import (
    MAX_OUTLINKS,
    FewInlinks,
    GenericAnchor,
    HighDepth,
    NofollowInternal,
    ToError,
    TooManyOutlinks,
    is_generic,
)
from sitecrawler.models import LinkRef, Outcome, RedirectHop
from tests.unit.audit.helpers import SITE, blocked, flagged, links, page


def test_to_error_names_the_first_broken_target_once() -> None:
    home = page(
        "/",
        links=(
            *links("/missing", "/missing", "/boom", "/ok", "/", "/nope", "/blocked"),
            LinkRef("https://other.test/", "o"),
        ),
    )
    pages = [
        home,
        page("/missing", 404),
        page("/boom", None, outcome=Outcome.ERROR),
        page("/ok", links=links("/ok")),
        blocked("/blocked"),
        page("/one", links=links("/missing")),
    ]
    hits = flagged(ToError(), pages)
    assert set(hits) == {"/", "/one"}
    assert hits["/"].message == f"2 link(s) to errors, e.g. {SITE}/missing (404) and 1 more"
    assert hits["/one"].message == f"1 link(s) to errors, e.g. {SITE}/missing (404)"


def test_few_inlinks_counts_follow_links_from_other_pages() -> None:
    home = page("/", links=(*links("/one", "/two", "/none"), *links("/nf", rel="nofollow")))
    other = page("/other", found_on=f"{SITE}/", links=links("/two", "/other", "/noindex"))
    pages = [
        home,
        other,
        page("/one", found_on=f"{SITE}/"),
        page("/two", found_on=f"{SITE}/"),
        page("/nf", found_on=f"{SITE}/"),
        page("/none", found_on=f"{SITE}/", links=links("/none")),
        page("/orphan", found_on="sitemap:x"),
        page("/noindex", found_on=f"{SITE}/other", meta_robots="noindex"),
    ]
    hits = flagged(FewInlinks(), pages)
    assert {path: issue.message for path, issue in hits.items()} == {
        "/one": f"1 follow inlink, from {SITE}/",
        "/nf": "no follow inlinks",
        "/none": f"1 follow inlink, from {SITE}/",
        "/orphan": "no follow inlinks",
        "/other": "no follow inlinks",
    }


def test_high_depth_flags_indexable_pages_over_three_clicks() -> None:
    chain = [page("/", links=links("/1"))]
    for n in range(1, 6):
        chain.append(page(f"/{n}", found_on=f"{SITE}/{n - 1}", links=links(f"/{n + 1}")))
    chain.append(page("/6", found_on=f"{SITE}/5", meta_robots="noindex"))
    chain.append(page("/orphan", found_on="sitemap:x"))
    hits = flagged(HighDepth(), chain)
    assert set(hits) == {"/4", "/5"}
    assert hits["/4"].message == "4 clicks from the start page"


def test_generic_anchor_text() -> None:
    assert is_generic("Click here!")
    assert is_generic("  READ   MORE... ")
    assert not is_generic("Read more about pricing")
    assert not is_generic("")
    home = page(
        "/",
        links=(
            LinkRef(f"{SITE}/a", "click here"),
            LinkRef(f"{SITE}/a", "Click here"),
            LinkRef(f"{SITE}/a", "click here"),
            LinkRef(f"{SITE}/b", "More"),
            LinkRef(f"{SITE}/c", "The pricing page"),
            LinkRef("https://other.test/", "here"),
        ),
    )
    hits = flagged(GenericAnchor(), [home, page("/clean", links=links("/a"))])
    assert set(hits) == {"/"}
    assert hits["/"].message == f"3 generic anchor(s), e.g. “click here” to {SITE}/a and 2 more"


def test_nofollow_internal_ignores_external_and_follow_links() -> None:
    home = page(
        "/",
        links=(
            *links("/a", "/a", rel="nofollow"),
            *links("/b"),
            LinkRef("https://other.test/", "o", "nofollow"),
        ),
    )
    hits = flagged(NofollowInternal(), [home, page("/a"), page("/b", links=links("/a"))])
    assert set(hits) == {"/"}
    assert hits["/"].message == f"1 nofollow link(s), e.g. to {SITE}/a"


def test_too_many_outlinks_counts_every_anchor() -> None:
    many = page(
        "/many", links=tuple(LinkRef(f"{SITE}/p{i}", str(i)) for i in range(MAX_OUTLINKS + 1))
    )
    enough = page("/ok", links=tuple(LinkRef(f"{SITE}/p{i}", str(i)) for i in range(MAX_OUTLINKS)))
    hits = flagged(TooManyOutlinks(), [many, enough])
    assert set(hits) == {"/many"}
    assert hits["/many"].message == f"{MAX_OUTLINKS + 1} links on the page"


def test_redirect_sources_are_not_checked() -> None:
    moved = page(
        "/old",
        final_url=f"{SITE}/new",
        redirect_hops=(RedirectHop(1, f"{SITE}/old", f"{SITE}/new", 301),),
        links=links("/missing"),
    )
    assert flagged(ToError(), [moved, page("/new"), page("/missing", 404)]) == {}
