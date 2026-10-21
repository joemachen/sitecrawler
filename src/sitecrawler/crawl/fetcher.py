"""HTTP fetching with a per-host politeness delay and explicit redirect following."""

from __future__ import annotations

import time
from collections.abc import Callable
from types import TracebackType
from urllib.parse import urljoin, urlparse

import httpx

from sitecrawler.crawl.throttle import HostThrottle
from sitecrawler.models import FetchResult, Outcome, RedirectHop

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_ACCEPT = "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"


def _host(url: str) -> str:
    return urlparse(url).netloc.lower()


def _loop_key(url: str) -> str:
    """Identity used for loop detection: case-insensitive host, no fragment."""
    parts = urlparse(url)
    return parts._replace(netloc=parts.netloc.lower(), fragment="").geturl()


def _headers(response: httpx.Response) -> dict[str, str]:
    """Lower-cased header map; repeated headers are joined with ``", "``."""
    merged: dict[str, str] = {}
    for key, value in response.headers.multi_items():
        name = key.lower()
        merged[name] = f"{merged[name]}, {value}" if name in merged else value
    return merged


class Fetcher:
    """Fetches URLs through one shared async client, never faster than ``delay`` per host.

    Redirects are followed by hand so that every hop is recorded in the
    result. A chain that revisits a URL, or runs past ``max_redirects``, ends
    with :attr:`~sitecrawler.models.Outcome.REDIRECT_LOOP` instead of an error.

    Use as an async context manager so the connection pool is closed::

        async with Fetcher(agent, 0.5, 20.0) as fetcher:
            result = await fetcher.fetch(url)
    """

    def __init__(
        self,
        user_agent: str,
        delay_seconds: float,
        timeout_seconds: float,
        *,
        max_redirects: int = 10,
        http2: bool = True,
        client: httpx.AsyncClient | None = None,
        hop_allowed: Callable[[str], bool] | None = None,
    ) -> None:
        """Create a fetcher.

        Args:
            user_agent: Sent as ``User-Agent``.
            delay_seconds: Minimum gap between requests to one host.
            timeout_seconds: Per-request timeout.
            max_redirects: Chains longer than this report ``redirect_loop``.
            http2: Negotiate HTTP/2 when offered.
            client: A pre-configured client, for tests.
            hop_allowed: Called with each redirect target; when it returns
                ``False`` the chain stops there and the redirect response is
                returned as the result, so out-of-scope sites are never fetched.
        """
        self.throttle = HostThrottle(delay_seconds)
        self._max_redirects = max_redirects
        self._hop_allowed = hop_allowed
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept": _ACCEPT},
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            http2=http2,
        )

    async def __aenter__(self) -> Fetcher:
        """Enter the context; the client is already open."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the connection pool."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying client and its connections."""
        await self._client.aclose()

    async def fetch(self, url: str) -> FetchResult:
        """GET ``url``, following redirects hop by hop, and return what came back.

        Never raises for HTTP or network errors; those are reported in the result.
        """
        started = time.monotonic()
        hops: list[RedirectHop] = []
        visited = {_loop_key(url)}
        current = url
        try:
            while True:
                await self.throttle.acquire(_host(current))
                response = await self._client.get(current)
                location = response.headers.get("location", "")
                if response.status_code not in _REDIRECT_STATUSES or not location:
                    break
                target = urljoin(current, location)
                hops.append(RedirectHop(len(hops) + 1, current, target, response.status_code))
                if self._hop_allowed is not None and not self._hop_allowed(target):
                    return self._result(url, response, hops, started, final_url=target)
                reason = ""
                if _loop_key(target) in visited:
                    chain = " -> ".join([url, *(hop.to_url for hop in hops)])
                    reason = f"redirect loop: {chain}"
                elif len(hops) > self._max_redirects:
                    reason = f"more than {self._max_redirects} redirects"
                if reason:
                    return self._failed(url, Outcome.REDIRECT_LOOP, reason, hops, started)
                visited.add(_loop_key(target))
                current = target
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            return self._failed(url, Outcome.ERROR, str(exc)[:200], hops, started)

        return self._result(url, response, hops, started)

    @staticmethod
    def _result(
        url: str,
        response: httpx.Response,
        hops: list[RedirectHop],
        started: float,
        *,
        final_url: str | None = None,
    ) -> FetchResult:
        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        return FetchResult(
            url=url,
            outcome=Outcome.FETCHED,
            status_code=response.status_code,
            final_url=final_url if final_url is not None else str(response.url),
            content_type=content_type,
            text=response.text if "html" in content_type else "",
            content=response.content,
            headers=_headers(response),
            size_bytes=len(response.content),
            elapsed_ms=_elapsed(started),
            hops=tuple(hops),
        )

    @staticmethod
    def _failed(
        url: str, outcome: Outcome, error: str, hops: list[RedirectHop], started: float
    ) -> FetchResult:
        return FetchResult(
            url=url, outcome=outcome, error=error, hops=tuple(hops), elapsed_ms=_elapsed(started)
        )


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
