"""Read-only view of a stored crawl, with the lookups rules need."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from sitecrawler.crawl.urls import normalize, strip_www
from sitecrawler.models import LinkRef, Outcome, PageRecord

if TYPE_CHECKING:
    from sitecrawler.store import Store


@dataclass(slots=True, frozen=True)
class Inlink:
    """A link from ``src`` to the page being looked at."""

    src: str
    link: LinkRef


@dataclass
class CrawlView:
    """Everything the audit knows about one crawl, indexed for fast lookups.

    Build one with :meth:`from_store` (the CLI) or :meth:`from_records` (tests).
    URLs are looked up in their normalised form, using the same rules the
    crawler used, so ``page_for("https://www.x/a/")`` finds ``https://x/a``.
    """

    pages: list[PageRecord]
    """Every fetched page, sorted by URL."""
    sitemap_urls: frozenset[str] = frozenset()
    keep_query: bool = False
    _by_url: dict[str, PageRecord] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Index the pages."""
        self.pages = sorted(self.pages, key=lambda p: p.url)
        self._by_url = {p.url: p for p in self.pages}

    @classmethod
    def from_records(
        cls,
        pages: Iterable[PageRecord],
        *,
        sitemap_urls: Iterable[str] = (),
        keep_query: bool = False,
    ) -> CrawlView:
        """Build a view from in-memory records."""
        return cls(list(pages), frozenset(sitemap_urls), keep_query)

    @classmethod
    def from_store(cls, store: Store) -> CrawlView:
        """Load every fetched page and sitemap URL from ``store``."""
        config = json.loads(store.crawl().config_json or "{}")
        keep_query = bool(config.get("keep_query", False))
        return cls(list(store.iter_pages()), store.sitemap_urls(), keep_query)

    # ------------------------------------------------------------ lookups
    def normalize(self, url: str) -> str | None:
        """The crawl's normalised form of ``url`` (scheme kept)."""
        return normalize(url, keep_query=self.keep_query)

    def page_for(self, url: str) -> PageRecord | None:
        """The fetched page at ``url`` (any form), or ``None`` if it was not crawled."""
        key = self.normalize(url)
        if key is None:
            return None
        page = self._by_url.get(key)
        if page is None and key.startswith("http://"):
            page = self._by_url.get("https://" + key.removeprefix("http://"))
        if page is None and key.startswith("https://"):
            page = self._by_url.get("http://" + key.removeprefix("https://"))
        return page

    def status_of(self, url: str) -> int | None:
        """HTTP status of the page at ``url``, or ``None`` when unknown."""
        page = self.page_for(url)
        return page.status_code if page else None

    def same_page(self, a: str, b: str) -> bool:
        """True when two URLs normalise to the same page (``www.`` and fragments ignored)."""
        return self.normalize(a) == self.normalize(b)

    @cached_property
    def hosts(self) -> frozenset[str]:
        """Every host the crawl fetched from, without ``www.``."""
        return frozenset(strip_www(urlparse(p.url).netloc) for p in self.pages)

    def is_internal(self, url: str) -> bool:
        """True when ``url`` is on one of the crawl's hosts."""
        return strip_www(urlparse(url).netloc) in self.hosts

    def is_html_page(self, page: PageRecord) -> bool:
        """True for pages whose own HTML was parsed.

        Fetched as HTML with a status below 400, and not redirected to a
        different page (that content belongs to the redirect's target).
        """
        return (
            page.outcome is Outcome.FETCHED
            and "html" in page.content_type
            and page.status_code is not None
            and page.status_code < 400
            and (not page.final_url or self.same_page(page.final_url, page.url))
        )

    @cached_property
    def html_pages(self) -> list[PageRecord]:
        """Pages whose HTML was parsed."""
        return [p for p in self.pages if self.is_html_page(p)]

    @cached_property
    def inlinks(self) -> dict[str, list[Inlink]]:
        """Internal links pointing at each page, keyed by the target's normalised URL."""
        index: dict[str, list[Inlink]] = defaultdict(list)
        for page in self.pages:
            for link in page.links:
                target = self.normalize(link.href)
                if target is not None and self.is_internal(link.href):
                    index[target].append(Inlink(page.url, link))
        return dict(index)

    def inlinks_to(self, url: str) -> list[Inlink]:
        """Internal links pointing at ``url``."""
        key = self.normalize(url)
        return self.inlinks.get(key, []) if key else []

    def group_html_pages(self, key: Callable[[PageRecord], str]) -> dict[str, list[PageRecord]]:
        """HTML pages grouped by ``key(page)``; empty keys are dropped."""
        groups: dict[str, list[PageRecord]] = defaultdict(list)
        for page in self.html_pages:
            value = key(page)
            if value:
                groups[value].append(page)
        return dict(groups)

    @cached_property
    def in_sitemap(self) -> frozenset[str]:
        """Normalised URLs listed in a sitemap."""
        return frozenset(n for n in (self.normalize(u) for u in self.sitemap_urls) if n)

    def listed_in_sitemap(self, url: str) -> bool:
        """True when ``url`` appears in any sitemap."""
        key = self.normalize(url)
        return key in self.in_sitemap if key else False

    def pages_matching(self, predicate: Callable[[PageRecord], bool]) -> Sequence[PageRecord]:
        """Pages for which ``predicate`` holds."""
        return [p for p in self.pages if predicate(p)]
