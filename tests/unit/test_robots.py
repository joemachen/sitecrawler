"""RobotsPolicy loading through the fetcher (mocked transport)."""

from __future__ import annotations

import httpx
import respx

from sitecrawler.crawl.fetcher import Fetcher
from sitecrawler.crawl.robots import RobotsPolicy

ROBOTS = b"User-agent: *\nDisallow: /private/\nSitemap: https://x.test/sitemap.xml\n"


async def test_loads_rules_and_sitemaps(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("https://x.test/robots.txt").mock(
        return_value=httpx.Response(200, content=ROBOTS, headers={"Content-Type": "text/plain"})
    )
    policy = RobotsPolicy("ua")
    async with Fetcher("ua", 0, 5.0) as fetcher:
        await policy.load(fetcher, "https://x.test/some/page")

    assert policy.loaded
    assert policy.allowed("https://x.test/public")
    assert not policy.allowed("https://x.test/private/x")
    assert policy.sitemaps() == ["https://x.test/sitemap.xml"]


async def test_missing_robots_allows_everything(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("https://x.test/robots.txt").mock(return_value=httpx.Response(404))
    policy = RobotsPolicy("ua")
    async with Fetcher("ua", 0, 5.0) as fetcher:
        await policy.load(fetcher, "https://x.test/")

    assert not policy.loaded
    assert policy.allowed("https://x.test/private/x")
    assert policy.sitemaps() == []


async def test_unreachable_robots_allows_everything(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("https://x.test/robots.txt").mock(side_effect=httpx.ConnectError("down"))
    policy = RobotsPolicy("ua")
    async with Fetcher("ua", 0, 5.0) as fetcher:
        await policy.load(fetcher, "https://x.test/")

    assert not policy.loaded
    assert policy.allowed("https://x.test/anything")
