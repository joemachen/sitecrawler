from sitecrawler.analysis import anchor_texts, link_report
from sitecrawler.models import LinkRef, Outcome, RedirectHop
from tests.unit.audit.helpers import SITE, blocked, links, page, view


def _site() -> list:  # type: ignore[type-arg]
    home = page(
        "/",
        links=(
            LinkRef(f"{SITE}/a", "A", position="nav"),
            LinkRef(f"{SITE}/missing", "Dead", position="body"),
            LinkRef(f"{SITE}/old", "Moved"),
            LinkRef(f"{SITE}/loop", "Loop"),
            LinkRef(f"{SITE}/blocked", "Blocked"),
            LinkRef("https://other.test/", "Off-site"),
            LinkRef(f"{SITE}/never-crawled", "Capped"),
        ),
    )
    return [
        home,
        page("/a", links=(LinkRef(f"{SITE}/", "Home"), LinkRef(f"{SITE}/a", "A again"))),
        page("/missing", 404),
        page(
            "/old",
            final_url=f"{SITE}/a",
            redirect_hops=(RedirectHop(1, f"{SITE}/old", f"{SITE}/a", 301),),
            links=links("/missing"),  # a redirect source's links belong to its target
        ),
        page("/loop", None, outcome=Outcome.REDIRECT_LOOP),
        blocked("/blocked"),
        page("/orphan", found_on="sitemap:x"),
    ]


def test_report_lists_broken_and_redirecting_links_with_their_anchors() -> None:
    report = link_report(view(_site()))
    assert report.pages == 7
    assert report.links == 7  # 5 crawled targets from /, 2 from /a
    assert [(p.src, p.link.href, p.link.text, p.target) for p in report.broken] == [
        (f"{SITE}/", f"{SITE}/missing", "Dead", "404"),
        (f"{SITE}/", f"{SITE}/loop", "Loop", "redirect_loop"),
    ]
    assert [(p.link.href, p.target) for p in report.redirecting] == [(f"{SITE}/old", f"{SITE}/a")]
    assert report.broken[0].link.position == "body"
    assert report.highest == (f"{SITE}/", 100)  # / and /a link each other: a tie, first URL wins
    assert report.lowest is not None
    assert report.unreachable == 1
    assert report.summary() == (
        f"Links: 7 internal links between 7 pages; 2 to errors; 1 to redirects; "
        f"1 page(s) unreachable from the start page; Link Score 100 at {SITE}/ "
        f"down to {report.lowest[1]} at {report.lowest[0]}."
    )


def test_summary_without_problems_and_in_list_mode() -> None:
    clean = link_report(view([page("/", links=links("/a")), page("/a")]))
    assert clean.summary() == (
        f"Links: 1 internal links between 2 pages; Link Score 100 at {SITE}/a down to 0 at {SITE}/."
    )
    listed = link_report(view([page("/a", found_on="list"), page("/b", found_on="list")]))
    assert listed.unreachable == 0
    assert link_report(view([])).summary() == "Links: 0 internal links between 0 pages."


def test_anchor_texts_per_target() -> None:
    texts = anchor_texts(view(_site()))
    assert list(texts) == [
        f"{SITE}/",
        f"{SITE}/a",
        f"{SITE}/blocked",
        f"{SITE}/loop",
        f"{SITE}/missing",
        f"{SITE}/old",
    ]
    assert texts[f"{SITE}/a"] == [("A", 1), ("A again", 1)]
    assert texts[f"{SITE}/"] == [("Home", 1)]
    assert f"{SITE}/orphan" not in texts
