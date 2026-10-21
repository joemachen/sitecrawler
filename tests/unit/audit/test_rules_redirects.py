from sitecrawler.audit.rules.redirects import (
    Chain,
    LinksToRedirects,
    Loop,
    OffSite,
    Temporary,
    ToError,
)
from sitecrawler.models import Outcome, RedirectHop
from tests.unit.audit.helpers import SITE, flagged, links, page


def hops(*pairs: tuple[str, str, int]) -> tuple[RedirectHop, ...]:
    return tuple(
        RedirectHop(i + 1, f"{SITE}{a}", f"{SITE}{b}", s) for i, (a, b, s) in enumerate(pairs)
    )


def test_chain_needs_two_hops() -> None:
    two = page(
        "/a", final_url=f"{SITE}/c", redirect_hops=hops(("/a", "/b", 301), ("/b", "/c", 301))
    )
    one = page("/x", final_url=f"{SITE}/y", redirect_hops=hops(("/x", "/y", 301)))
    hits = flagged(Chain(), [two, one, page("/plain")])
    assert set(hits) == {"/a"}
    assert hits["/a"].message == f"2 hops: {SITE}/a -> {SITE}/b -> {SITE}/c"


def test_loop() -> None:
    loop = page("/l", None, outcome=Outcome.REDIRECT_LOOP, error="redirect loop: l -> m -> l")
    hits = flagged(Loop(), [loop, page("/ok")])
    assert set(hits) == {"/l"}
    assert hits["/l"].message.startswith("redirect loop")


def test_to_error() -> None:
    bad = page("/old", 404, final_url=f"{SITE}/gone", redirect_hops=hops(("/old", "/gone", 302)))
    plain404 = page("/missing", 404)
    good = page("/moved", final_url=f"{SITE}/new", redirect_hops=hops(("/moved", "/new", 301)))
    hits = flagged(ToError(), [bad, plain404, good])
    assert set(hits) == {"/old"}
    assert hits["/old"].message == f"404 at {SITE}/gone"


def test_off_site() -> None:
    away = page(
        "/away",
        302,
        final_url="https://other.test/x",
        redirect_hops=(RedirectHop(1, f"{SITE}/away", "https://other.test/x", 302),),
    )
    home_hop = page("/in", final_url=f"{SITE}/in/", redirect_hops=hops(("/in", "/in/", 301)))
    hits = flagged(OffSite(), [away, home_hop, page("/ok")])
    assert set(hits) == {"/away"}
    assert hits["/away"].message == "to https://other.test/x"


def test_temporary_lists_the_codes() -> None:
    mixed = page(
        "/t", final_url=f"{SITE}/u", redirect_hops=hops(("/t", "/t2", 302), ("/t2", "/u", 307))
    )
    permanent = page("/p", final_url=f"{SITE}/q", redirect_hops=hops(("/p", "/q", 301)))
    to_404 = page("/bad", 404, final_url=f"{SITE}/gone", redirect_hops=hops(("/bad", "/gone", 302)))
    loop = page("/l", None, outcome=Outcome.REDIRECT_LOOP, redirect_hops=hops(("/l", "/m", 302)))
    away = page(
        "/away",
        302,
        final_url="https://other.test/x",
        redirect_hops=(RedirectHop(1, f"{SITE}/away", "https://other.test/x", 302),),
    )
    hits = flagged(Temporary(), [mixed, permanent, to_404, loop, away])
    assert set(hits) == {"/t"}
    assert hits["/t"].message.startswith("302, 307 in ")


def test_links_to_redirects_ignores_trailing_slash_and_loops() -> None:
    moved = page("/old", final_url=f"{SITE}/new", redirect_hops=hops(("/old", "/new", 301)))
    moved2 = page("/old2", final_url=f"{SITE}/new2", redirect_hops=hops(("/old2", "/new2", 301)))
    slash = page("/dir", final_url=f"{SITE}/dir/", redirect_hops=hops(("/dir", "/dir/", 301)))
    loop = page(
        "/loop", None, outcome=Outcome.REDIRECT_LOOP, redirect_hops=hops(("/loop", "/loop", 302))
    )
    home = page("/", links=(*links("/old", "/old", "/old2", "/dir/", "/loop", "/new"),))
    clean = page("/clean", links=links("/new", "/dir/"))
    hits = flagged(LinksToRedirects(), [moved, moved2, slash, loop, home, clean])
    assert set(hits) == {"/"}
    assert hits["/"].message == f"2 link(s) redirect, e.g. {SITE}/old and 1 more"
