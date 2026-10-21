"""Fetcher behaviour against a mocked transport (no network)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from sitecrawler.crawl.fetcher import Fetcher
from sitecrawler.models import Outcome, RedirectHop


@pytest.fixture
async def fetcher() -> AsyncIterator[Fetcher]:
    async with Fetcher("test-agent", 0, 5.0, max_redirects=10) as f:
        yield f


def _redirect(location: str, status: int = 302) -> httpx.Response:
    return httpx.Response(status, headers={"Location": location})


async def test_two_hop_chain_records_every_hop(
    respx_mock: respx.MockRouter, fetcher: Fetcher
) -> None:
    respx_mock.get("https://x.test/a").mock(return_value=_redirect("/b", 301))
    respx_mock.get("https://x.test/b").mock(return_value=_redirect("https://x.test/c"))
    respx_mock.get("https://x.test/c").mock(return_value=httpx.Response(200, html="<p>c</p>"))

    result = await fetcher.fetch("https://x.test/a")

    assert result.outcome is Outcome.FETCHED
    assert result.status_code == 200
    assert result.final_url == "https://x.test/c"
    assert result.hops == (
        RedirectHop(1, "https://x.test/a", "https://x.test/b", 301),
        RedirectHop(2, "https://x.test/b", "https://x.test/c", 302),
    )
    assert result.text == "<p>c</p>"


async def test_loop_is_reported_not_retried(respx_mock: respx.MockRouter, fetcher: Fetcher) -> None:
    a = respx_mock.get("https://x.test/a").mock(return_value=_redirect("/b"))
    b = respx_mock.get("https://x.test/b").mock(return_value=_redirect("/a"))

    result = await fetcher.fetch("https://x.test/a")

    assert result.outcome is Outcome.REDIRECT_LOOP
    assert result.status_code is None
    assert len(result.hops) == 2
    assert result.error == "redirect loop: https://x.test/a -> https://x.test/b -> https://x.test/a"
    assert a.call_count == 1
    assert b.call_count == 1


async def test_chain_longer_than_max_redirects_is_a_loop(respx_mock: respx.MockRouter) -> None:
    for i in range(12):
        respx_mock.get(f"https://x.test/{i}").mock(return_value=_redirect(f"/{i + 1}"))
    respx_mock.get("https://x.test/12").mock(return_value=httpx.Response(200))

    async with Fetcher("ua", 0, 5.0, max_redirects=10) as fetcher:
        result = await fetcher.fetch("https://x.test/0")

    assert result.outcome is Outcome.REDIRECT_LOOP
    assert result.error == "more than 10 redirects"
    assert len(result.hops) == 11


async def test_chain_of_exactly_max_redirects_succeeds(respx_mock: respx.MockRouter) -> None:
    for i in range(3):
        respx_mock.get(f"https://x.test/{i}").mock(return_value=_redirect(f"/{i + 1}"))
    respx_mock.get("https://x.test/3").mock(return_value=httpx.Response(200))

    async with Fetcher("ua", 0, 5.0, max_redirects=3) as fetcher:
        result = await fetcher.fetch("https://x.test/0")

    assert result.outcome is Outcome.FETCHED
    assert len(result.hops) == 3


async def test_redirect_without_location_is_terminal(
    respx_mock: respx.MockRouter, fetcher: Fetcher
) -> None:
    respx_mock.get("https://x.test/odd").mock(return_value=httpx.Response(302))

    result = await fetcher.fetch("https://x.test/odd")

    assert result.outcome is Outcome.FETCHED
    assert result.status_code == 302
    assert result.hops == ()


async def test_headers_and_size_are_captured(
    respx_mock: respx.MockRouter, fetcher: Fetcher
) -> None:
    body = b"<html><body>hello</body></html>"
    respx_mock.get("https://x.test/h").mock(
        return_value=httpx.Response(
            200,
            content=body,
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "X-Robots-Tag": "noindex",
                "Last-Modified": "Wed, 21 Oct 2026 10:00:00 GMT",
            },
        )
    )

    result = await fetcher.fetch("https://x.test/h")

    assert result.content_type == "text/html"
    assert result.headers["x-robots-tag"] == "noindex"
    assert result.headers["last-modified"] == "Wed, 21 Oct 2026 10:00:00 GMT"
    assert result.size_bytes == len(body)
    assert result.content == body


async def test_non_html_keeps_bytes_but_not_text(
    respx_mock: respx.MockRouter, fetcher: Fetcher
) -> None:
    respx_mock.get("https://x.test/s.xml").mock(
        return_value=httpx.Response(
            200, content=b"<urlset/>", headers={"Content-Type": "application/xml"}
        )
    )

    result = await fetcher.fetch("https://x.test/s.xml")

    assert result.text == ""
    assert result.content == b"<urlset/>"
    assert not result.is_html


@pytest.mark.parametrize(
    "exc",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), httpx.RemoteProtocolError("bad")],
)
async def test_transport_errors_become_error_outcome(
    respx_mock: respx.MockRouter, fetcher: Fetcher, exc: Exception
) -> None:
    respx_mock.get("https://x.test/boom").mock(side_effect=exc)

    result = await fetcher.fetch("https://x.test/boom")

    assert result.outcome is Outcome.ERROR
    assert result.status_code is None
    assert result.error


async def test_error_mid_chain_keeps_hops_so_far(
    respx_mock: respx.MockRouter, fetcher: Fetcher
) -> None:
    respx_mock.get("https://x.test/a").mock(return_value=_redirect("/b"))
    respx_mock.get("https://x.test/b").mock(side_effect=httpx.ConnectError("refused"))

    result = await fetcher.fetch("https://x.test/a")

    assert result.outcome is Outcome.ERROR
    assert len(result.hops) == 1


async def test_can_be_built_without_http2() -> None:
    async with Fetcher("ua", 0, 5.0, http2=False) as fetcher:
        assert fetcher.throttle is not None


async def test_loop_detection_ignores_host_case_and_fragment(
    respx_mock: respx.MockRouter, fetcher: Fetcher
) -> None:
    respx_mock.get("https://x.test/a").mock(return_value=_redirect("https://X.test/a#top"))

    result = await fetcher.fetch("https://x.test/a")

    assert result.outcome is Outcome.REDIRECT_LOOP
    assert result.error.startswith("redirect loop:")
    assert len(result.hops) == 1


async def test_repeated_headers_are_joined(respx_mock: respx.MockRouter, fetcher: Fetcher) -> None:
    respx_mock.get("https://x.test/r").mock(
        return_value=httpx.Response(
            200, headers=[("X-Robots-Tag", "noindex"), ("X-Robots-Tag", "nofollow")]
        )
    )

    result = await fetcher.fetch("https://x.test/r")

    assert result.headers["x-robots-tag"] == "noindex, nofollow"


async def test_hop_outside_scope_is_not_followed(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("https://x.test/go").mock(return_value=_redirect("https://other.test/landing"))
    other = respx_mock.get("https://other.test/landing").mock(return_value=httpx.Response(200))

    async with Fetcher("ua", 0, 5.0, hop_allowed=lambda url: "other.test" not in url) as fetcher:
        result = await fetcher.fetch("https://x.test/go")

    assert result.outcome is Outcome.FETCHED
    assert result.status_code == 302
    assert result.final_url == "https://other.test/landing"
    assert len(result.hops) == 1
    assert other.call_count == 0
