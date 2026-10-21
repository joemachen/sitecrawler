"""robots.txt handling."""

from __future__ import annotations

import urllib.robotparser
from urllib.parse import urljoin

import requests


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

    def load(self, session: requests.Session, site_url: str, timeout: float) -> None:
        """Fetch and parse ``/robots.txt`` for the site that ``site_url`` belongs to."""
        try:
            response = session.get(urljoin(site_url, "/robots.txt"), timeout=timeout)
        except requests.RequestException:
            return
        if response.ok:
            self._parser.parse(response.text.splitlines())
            self.loaded = True

    def allowed(self, url: str) -> bool:
        """True unless robots.txt disallows ``url`` for our agent or for ``*``."""
        return self._parser.can_fetch(self._agent, url) and self._parser.can_fetch("*", url)

    def sitemaps(self) -> list[str]:
        """Sitemap URLs declared in robots.txt, if any."""
        return list(self._parser.site_maps() or [])
