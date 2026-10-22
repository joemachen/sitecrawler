"""The link graph: inlink counts, click depth, Link Score and the target classifiers."""

from __future__ import annotations

import pytest

from sitecrawler.audit import graph as graph_module
from sitecrawler.audit.graph import LinkGraph, is_broken, redirects_elsewhere
from sitecrawler.models import LinkRef, Outcome, PageRecord, RedirectHop
from tests.unit.audit.helpers import SITE, blocked, links, page, view


def _scores(pages: list[PageRecord]) -> dict[str, int]:
    return {u.removeprefix(SITE): m.link_score for u, m in view(pages).link_graph.metrics.items()}


def test_scores_follow_the_links() -> None:
    home = page("/", links=links("/a", "/b"))
    a = page("/a", links=links("/b"))
    b = page("/b")
    scores = _scores([home, a, b])
    assert scores["/b"] == 100  # linked from both
    assert scores["/"] == 0  # linked from nothing
    assert 0 < scores["/a"] < 100
    g = view([home, a, b]).link_graph
    assert g.metrics[f"{SITE}/b"].inlinks == 2
    assert g.metrics[f"{SITE}/b"].follow_inlinks == 2
    assert g.highest() == (f"{SITE}/b", 100)
    assert g.lowest() == (f"{SITE}/", 0)


def test_nofollow_links_and_nofollow_pages_pass_nothing() -> None:
    home = page("/", links=(*links("/a", rel="nofollow"), *links("/b")))
    c = page("/c", meta_robots="nofollow", links=links("/a", "/b"))
    pages = [home, c, page("/a"), page("/b")]
    g = view(pages).link_graph
    a, b = g.metrics[f"{SITE}/a"], g.metrics[f"{SITE}/b"]
    assert (a.inlinks, a.follow_inlinks) == (2, 0)
    assert (b.inlinks, b.follow_inlinks) == (2, 1)
    assert a.link_score < b.link_score
    assert g.follow_sources(f"{SITE}/b/") == [f"{SITE}/"]
    assert g.follow_sources("not a url") == []
    assert (a.link_depth, b.link_depth) == (1, 1)  # depth counts nofollow links too


def test_links_resolve_through_redirects() -> None:
    home = page("/", links=links("/old", "/dir", "/back"))  # /back lands on / itself
    old = page(
        "/old",
        final_url=f"{SITE}/new",
        redirect_hops=(RedirectHop(1, f"{SITE}/old", f"{SITE}/new", 301),),
    )
    new = page("/new", links=links("/back"))
    back = page(
        "/back",
        final_url=f"{SITE}/",
        redirect_hops=(RedirectHop(1, f"{SITE}/back", f"{SITE}/", 301),),
    )
    slash = page("/dir", final_url=f"{SITE}/dir/")
    away = page("/away", 302, final_url="https://other.test/x")
    g = view([home, old, new, back, slash, away]).link_graph
    assert g.landing(old) is new
    assert g.landing(slash) is slash  # same page, different spelling
    assert g.landing(away) is away  # the target was never crawled
    assert g.landing(new) is new
    assert g.metrics[f"{SITE}/old"].inlinks == 1  # the link is still to /old...
    assert g.metrics[f"{SITE}/new"].inlinks == 0
    assert (
        g.metrics[f"{SITE}/new"].link_score > g.metrics[f"{SITE}/old"].link_score
    )  # ...equity lands on /new
    assert g.metrics[f"{SITE}/new"].link_depth == 1
    assert g.metrics[f"{SITE}/old"].link_depth == 1
    assert g.metrics[f"{SITE}/back"].link_depth == 1  # linked from / directly
    # /new -> /back -> / is a link from /new to the home page, which keeps / off the floor
    assert g.metrics[f"{SITE}/"].link_score > g.metrics[f"{SITE}/away"].link_score


def test_click_depth_is_a_shortest_path_from_the_start_page() -> None:
    home = page("/", links=links("/a"))
    a = page("/a", found_on=f"{SITE}/", links=links("/b"))
    b = page("/b", found_on=f"{SITE}/a", links=links("/c", "/"))
    c = page("/c", found_on=f"{SITE}/b")
    orphan = page("/orphan", found_on=f"sitemap:{SITE}/sitemap.xml")
    g = view([home, a, b, c, orphan]).link_graph
    depths = {u.removeprefix(SITE): m.link_depth for u, m in g.metrics.items()}
    assert depths == {"/": 0, "/a": 1, "/b": 2, "/c": 3, "/orphan": None}


def test_list_mode_has_no_depth() -> None:
    a = page("/a", found_on="list", links=links("/b"))
    b = page("/b", found_on="list")
    g = view([a, b]).link_graph
    assert {m.link_depth for m in g.metrics.values()} == {None}
    assert g.metrics[f"{SITE}/b"].link_score == 100


def test_self_links_external_links_and_uncrawled_targets_are_ignored() -> None:
    home = page(
        "/", links=(*links("/", "/nope"), LinkRef("https://other.test/x", "x"), LinkRef("nope", ""))
    )
    g = view([home, blocked("/b")]).link_graph
    assert g.metrics[f"{SITE}/"].inlinks == 0
    assert g.metrics[f"{SITE}/"].link_score == 100  # everything is equal
    assert g.metrics_for(f"{SITE}/nope") is None
    assert g.metrics_for("https://www.site.test/") == g.metrics[f"{SITE}/"]


def test_empty_crawl_and_single_page() -> None:
    empty = view([]).link_graph
    assert empty.metrics == {}
    assert empty.highest() is None
    assert empty.lowest() is None
    assert view([page("/")]).link_graph.metrics[f"{SITE}/"].link_score == 100


def test_ties_go_to_the_first_url() -> None:
    g = view([page("/b"), page("/a")]).link_graph
    assert g.highest() == (f"{SITE}/a", 100)
    assert g.lowest() == (f"{SITE}/a", 100)


def test_iteration_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graph_module, "MAX_ITERATIONS", 1)
    pages = [page("/", links=links("/a")), page("/a")]  # not symmetric, so one round is not enough
    capped = view(pages).link_graph
    assert set(capped.metrics) == {f"{SITE}/", f"{SITE}/a"}


@pytest.mark.parametrize(
    ("record", "broken"),
    [
        (page("/ok"), False),
        (page("/missing", 404), True),
        (page("/boom", 500), True),
        (page("/odd", None), True),
        (page("/err", None, outcome=Outcome.ERROR), True),
        (page("/loop", None, outcome=Outcome.REDIRECT_LOOP), True),
        (blocked("/b"), False),
        (page("/r404", 404, final_url=f"{SITE}/gone"), True),
    ],
)
def test_is_broken(record: PageRecord, broken: bool) -> None:
    assert is_broken(record) is broken


def test_redirects_elsewhere_ignores_spelling_variants() -> None:
    v = view([page("/a")])
    assert redirects_elsewhere(v, page("/old", final_url=f"{SITE}/new"))
    assert not redirects_elsewhere(v, page("/dir", final_url=f"{SITE}/dir/"))
    assert not redirects_elsewhere(v, page("/plain", final_url=""))
    assert isinstance(view([]).link_graph, LinkGraph)
