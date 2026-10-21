from sitecrawler.audit.rules.response import BlockedByRobots, ClientError, FetchError, ServerError
from sitecrawler.models import Outcome
from tests.unit.audit.helpers import SITE, blocked, flagged, links, page


def test_client_error_only_4xx_with_link_context() -> None:
    home = page("/", links=links("/gone", "/also"))
    other = page("/c", links=links("/gone"))
    hits = flagged(ClientError(), [home, other, page("/gone", 404), page("/ok"), page("/e", 503)])
    assert set(hits) == {"/gone"}
    assert hits["/gone"].message == f"404, linked from {SITE}/ and 1 more"


def test_server_error_message_without_inlinks() -> None:
    hits = flagged(ServerError(), [page("/boom", 500), page("/gone", 404), page("/ok")])
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
