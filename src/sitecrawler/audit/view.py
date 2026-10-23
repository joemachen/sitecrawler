"""Read-only view of a stored crawl, with the lookups rules need."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from sitecrawler.audit.duplicates import DuplicateIndex
from sitecrawler.audit.graph import LinkGraph
from sitecrawler.audit.structured import StructuredIndex
from sitecrawler.crawl.urls import normalize, strip_www
from sitecrawler.models import LinkRef, Outcome, PageRecord, SitemapEntry, SitemapFile

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
    """Every URL listed in any sitemap, as written there; derived from ``sitemap_entries``."""
    keep_query: bool = False
    sitemap_entries: tuple[SitemapEntry, ...] = ()
    """Every sitemap entry with the file it came from."""
    sitemap_files: tuple[SitemapFile, ...] = ()
    """Every sitemap file the crawl tried to read."""
    _by_url: dict[str, PageRecord] = field(init=False, repr=False)
    _normalized: dict[str, str | None] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        """Index the pages and reconcile the two sitemap fields."""
        self.pages = sorted(self.pages, key=lambda p: p.url)
        self._by_url = {p.url: p for p in self.pages}
        if self.sitemap_entries:
            self.sitemap_urls = frozenset(e.loc for e in self.sitemap_entries)
        elif self.sitemap_urls:
            # Built from bare URLs (older callers, tests): one entry each, file unknown.
            self.sitemap_entries = tuple(SitemapEntry("", loc) for loc in sorted(self.sitemap_urls))

    @classmethod
    def from_records(
        cls,
        pages: Iterable[PageRecord],
        *,
        sitemap_urls: Iterable[str] = (),
        sitemap_entries: Iterable[SitemapEntry] = (),
        sitemap_files: Iterable[SitemapFile] = (),
        keep_query: bool = False,
    ) -> CrawlView:
        """Build a view from in-memory records.

        Give ``sitemap_entries`` when the files are known; ``sitemap_urls``
        alone is enough for the membership lookups.
        """
        return cls(
            list(pages),
            frozenset(sitemap_urls),
            keep_query,
            tuple(sitemap_entries),
            tuple(sitemap_files),
        )

    @classmethod
    def from_store(cls, store: Store) -> CrawlView:
        """Load every fetched page, sitemap file and sitemap entry from ``store``."""
        config = json.loads(store.crawl().config_json or "{}")
        keep_query = bool(config.get("keep_query", False))
        return cls(
            list(store.iter_pages()),
            keep_query=keep_query,
            sitemap_entries=tuple(store.sitemap_entries()),
            sitemap_files=tuple(store.sitemap_files()),
        )

    # ------------------------------------------------------------ lookups
    def normalize(self, url: str) -> str | None:
        """The crawl's normalised form of ``url`` (scheme kept). Memoised per view."""
        try:
            return self._normalized[url]
        except KeyError:
            result = self._normalized[url] = normalize(url, keep_query=self.keep_query)
            return result

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

    @cached_property
    def start_page(self) -> PageRecord | None:
        """The page the crawl started from, or None in list mode."""
        return next((p for p in self.pages if p.found_on == "start"), None)

    @cached_property
    def link_graph(self) -> LinkGraph:
        """Inlink counts, click depth and Link Score for every page (ADR-0011)."""
        return LinkGraph(self)

    @cached_property
    def duplicates(self) -> DuplicateIndex:
        """Exact groups and near clusters over the fingerprinted pages (ADR-0012)."""
        return DuplicateIndex(self)

    @cached_property
    def structured(self) -> StructuredIndex:
        """Structured data findings per parsed HTML page (ADR-0013)."""
        return StructuredIndex(self)

    def group_html_pages(self, key: Callable[[PageRecord], str]) -> dict[str, list[PageRecord]]:
        """HTML pages grouped by ``key(page)``; empty keys are dropped."""
        groups: dict[str, list[PageRecord]] = defaultdict(list)
        for page in self.html_pages:
            value = key(page)
            if value:
                groups[value].append(page)
        return dict(groups)

    @cached_property
    def sitemap_listings(self) -> dict[str, list[SitemapEntry]]:
        """Sitemap entries grouped by the normalised URL they name, in file order."""
        index: dict[str, list[SitemapEntry]] = defaultdict(list)
        for entry in self.sitemap_entries:
            key = self.normalize(entry.loc)
            if key is not None:
                index[key].append(entry)
        return dict(index)

    @cached_property
    def in_sitemap(self) -> frozenset[str]:
        """Normalised URLs listed in a sitemap."""
        return frozenset(self.sitemap_listings)

    def listed_in_sitemap(self, url: str) -> bool:
        """True when ``url`` appears in any sitemap."""
        key = self.normalize(url)
        return key in self.in_sitemap if key else False

    def sitemap_listings_for(self, url: str) -> list[SitemapEntry]:
        """Every sitemap entry naming ``url`` (any form); several means it is listed twice."""
        key = self.normalize(url)
        return self.sitemap_listings.get(key, []) if key else []

    def pages_matching(self, predicate: Callable[[PageRecord], bool]) -> Sequence[PageRecord]:
        """Pages for which ``predicate`` holds."""
        return [p for p in self.pages if predicate(p)]
