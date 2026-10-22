"""The internal link graph: inlink counts, click depth and Link Score (ADR-0011).

Built once per :class:`~sitecrawler.audit.view.CrawlView` and reached as
``crawl.link_graph``. Nodes are every crawled page; the *follow graph* has
an edge from each parsed HTML page to every page a link on it lands on
(through redirects) unless the link, or the page, is ``nofollow``. Link
Score is PageRank over that graph on a log scale from 0 to 100; click depth
is a breadth-first walk from the start page over every internal link.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Mapping
from typing import TYPE_CHECKING

from sitecrawler.audit.directives import page_nofollow
from sitecrawler.models import LinkMetrics, Outcome, PageRecord

if TYPE_CHECKING:
    from sitecrawler.audit.view import CrawlView

DAMPING = 0.85
"""PageRank damping factor: the share of rank that follows links rather than teleporting."""

MAX_ITERATIONS = 100
TOLERANCE = 1e-6
"""Stop iterating when the total change in rank over one round is below this."""


def is_broken(target: PageRecord) -> bool:
    """True when a link to ``target`` lands on nothing usable.

    An error or redirect-loop outcome, or a status of 400 and up (including
    a redirect that ends on one). Robots-blocked pages are not broken: the
    crawler never asked, and ``robots.blocked_but_linked`` covers them.
    """
    if target.outcome is Outcome.BLOCKED:
        return False
    if target.outcome is not Outcome.FETCHED:
        return True
    return target.status_code is None or target.status_code >= 400


def redirects_elsewhere(crawl: CrawlView, target: PageRecord) -> bool:
    """True when ``target`` redirects to a different page (``/a`` to ``/a/`` does not count)."""
    return bool(target.final_url) and not crawl.same_page(target.final_url, target.url)


class LinkGraph:
    """Per-page link metrics for one crawl, computed on construction.

    Args:
        crawl: The view to walk. Only its pages and lookups are used.
    """

    def __init__(self, crawl: CrawlView) -> None:
        """Index the links, run PageRank and the depth walk, and keep the results."""
        self._crawl = crawl
        self._sources: dict[str, set[str]] = defaultdict(set)
        """Target URL to the other pages linking to it directly, any ``rel``."""
        self._follow_sources: dict[str, set[str]] = defaultdict(set)
        """Target URL to the other pages with a follow link to it."""
        follow_edges: dict[str, set[str]] = defaultdict(set)
        click_edges: dict[str, set[str]] = defaultdict(set)
        for page in crawl.html_pages:
            blanket = page_nofollow(page)
            for link in page.links:
                target = crawl.page_for(link.href)
                if target is None or target is page:
                    continue
                landed = self.landing(target)
                self._sources[target.url].add(page.url)
                click_edges[page.url].update((target.url, landed.url))
                if blanket or link.nofollow:
                    continue
                self._follow_sources[target.url].add(page.url)
                if landed is not page:
                    follow_edges[page.url].add(landed.url)
        urls = [p.url for p in crawl.pages]
        scores = _link_scores(urls, follow_edges)
        depths = _click_depths(crawl.start_page, click_edges)
        self.metrics: dict[str, LinkMetrics] = {
            url: LinkMetrics(
                inlinks=len(self._sources.get(url, ())),
                follow_inlinks=len(self._follow_sources.get(url, ())),
                link_depth=depths.get(url),
                link_score=scores[url],
            )
            for url in urls
        }
        """Every crawled page's metrics, keyed by its URL."""

    def landing(self, target: PageRecord) -> PageRecord:
        """The page a click on ``target`` ends up on: its crawled final URL, or itself."""
        if not target.final_url:
            return target
        final = self._crawl.page_for(target.final_url)
        return final if final is not None and final is not target else target

    def follow_sources(self, url: str) -> list[str]:
        """The other pages with a follow link to ``url``, sorted."""
        page = self._crawl.page_for(url)
        return sorted(self._follow_sources.get(page.url, ())) if page else []

    def highest(self) -> tuple[str, int] | None:
        """``(url, score)`` of the best-linked page; ties go to the first URL."""
        if not self.metrics:
            return None
        best = max(m.link_score for m in self.metrics.values())
        return self._first_with(best), best

    def lowest(self) -> tuple[str, int] | None:
        """``(url, score)`` of the least-linked page; ties go to the first URL."""
        if not self.metrics:
            return None
        worst = min(m.link_score for m in self.metrics.values())
        return self._first_with(worst), worst

    def _first_with(self, score: int) -> str:
        return min(url for url, m in self.metrics.items() if m.link_score == score)


def _link_scores(urls: list[str], edges: Mapping[str, set[str]]) -> dict[str, int]:
    """PageRank over ``edges`` (page URL to the URLs it links to), log-scaled 0-100."""
    n = len(urls)
    if n == 0:
        return {}
    index = {url: i for i, url in enumerate(urls)}
    out: list[list[int]] = [sorted(index[t] for t in edges.get(url, ())) for url in urls]
    rank = [1.0 / n] * n
    for _ in range(MAX_ITERATIONS):
        dangling = sum(rank[i] for i in range(n) if not out[i])
        base = (1.0 - DAMPING) / n + DAMPING * dangling / n
        fresh = [base] * n
        for i, targets in enumerate(out):
            if targets:
                share = DAMPING * rank[i] / len(targets)
                for j in targets:
                    fresh[j] += share
        change = sum(abs(a - b) for a, b in zip(fresh, rank, strict=True))
        rank = fresh
        if change < TOLERANCE:
            break
    low, high = math.log(min(rank)), math.log(max(rank))
    if high - low < 1e-12:
        return dict.fromkeys(urls, 100)
    return {
        url: round(100 * (math.log(r) - low) / (high - low))
        for url, r in zip(urls, rank, strict=True)
    }


def _click_depths(start: PageRecord | None, edges: Mapping[str, set[str]]) -> dict[str, int]:
    """Breadth-first depth of every page reachable from ``start`` over ``edges``."""
    if start is None:
        return {}
    depths = {start.url: 0}
    queue = deque([start.url])
    while queue:
        url = queue.popleft()
        for nxt in sorted(edges.get(url, ())):
            if nxt not in depths:
                depths[nxt] = depths[url] + 1
                queue.append(nxt)
    return depths
