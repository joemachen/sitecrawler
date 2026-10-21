from sitecrawler.audit.rules.response import BlockedByRobots, ClientError, FetchError, ServerError
from sitecrawler.models import Outcome, RedirectHop
from tests.unit.audit.helpers import SITE, blocked, flagged, links, page


def test_client_error_only_4xx_with_link_context() -> None:
    home = page("/", links=links("/gone", "/also"))
    other = page("/c", links=links("/gone"))
    via_redirect = page(
        "/old", 404, redirect_hops=(RedirectHop(1, f"{SITE}/old", f"{SITE}/gone", 301),)
    )
    hits = flagged(
        ClientError(),
        [home, other, page("/gone", 404), page("/ok"), page("/e", 503), via_redirect],
    )
    assert set(hits) == {"/gone"}  # the redirected one is redirect.to_error's job
    assert hits["/gone"].message == f"404, linked from {SITE}/ and 1 more"


def test_server_error_message_without_inlinks() -> None:
    via_redirect = page(
        "/r", 503, redirect_hops=(RedirectHop(1, f"{SITE}/r", f"{SITE}/boom", 302),)
    )
    hits = flagged(
        ServerError(), [page("/boom", 500), page("/gone", 404), page("/ok"), via_redirect]
    )
    assert set(hits) == {"/boom"}
    assert hits["/boom"].message == "500, no internal links; found via start"


def test_fetch_error() -> None:
    hits = flagged(
        FetchError(),
        [page("/t", None, outcome=Outcome.ERROR, error="timed out"), page("/ok"), blocked("/b")],
    )
    assert set(hits) == {"/t"}
    assert hits["/t"].message == "timed out"


def test_blocked_by_robots() -> None:
    home = page("/", links=links("/b"))
    hits = flagged(BlockedByRobots(), [home, blocked("/b"), page("/ok")])
    assert set(hits) == {"/b"}
    assert hits["/b"].message == f"linked from {SITE}/"
