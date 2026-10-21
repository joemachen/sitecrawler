"""robots.txt handling."""

from __future__ import annotations

import urllib.robotparser
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from sitecrawler.models import Outcome

if TYPE_CHECKING:
    from sitecrawler.crawl.fetcher import Fetcher


class RobotsPolicy:
    """Answers "may I fetch this URL?" for one site.

    A policy that was never loaded (or whose robots.txt could not be fetched)
    allows everything, which matches how browsers and most crawlers behave.
    """

    def __init__(self, user_agent: str) -> None:
        """Create an empty, allow-all policy for the given user agent."""
        self._agent = user_agent
        self._parser = urllib.robotparser.RobotFileParser()
        self._parser.parse([])
        self.loaded = False

    async def load(self, fetcher: Fetcher, site_url: str) -> None:
        """Fetch and parse ``/robots.txt`` for the site that ``site_url`` belongs to."""
        result = await fetcher.fetch(urljoin(site_url, "/robots.txt"))
        if result.outcome is Outcome.FETCHED and result.status_code == 200:
            self._parser.parse(result.content.decode("utf-8", errors="replace").splitlines())
            self.loaded = True

    def allowed(self, url: str) -> bool:
        """True unless robots.txt disallows ``url`` for our agent or for ``*``."""
        return self._parser.can_fetch(self._agent, url) and self._parser.can_fetch("*", url)

    def sitemaps(self) -> list[str]:
        """Sitemap URLs declared in robots.txt, if any."""
        return list(self._parser.site_maps() or [])
