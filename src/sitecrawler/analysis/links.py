"""Internal linking report: every link that deserves a look, and what the site calls each page.

The per-page metrics (inlinks, click depth, Link Score) and the rules that
read them live in the audit (``crawl.link_graph``, ADR-0011). This module
lists the individual links: those pointing at broken or redirecting
targets, with their source page and anchor text, and the anchor texts used
for every target. ``sitecrawler links report`` and ``links anchors`` print it.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sitecrawler.audit.graph import is_broken, redirects_elsewhere
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import LinkRef


@dataclass(slots=True, frozen=True)
class ProblemLink:
    """One internal link whose target is broken or redirects."""

    src: str
    """The page the link is on."""
    link: LinkRef
    """The anchor as written: href, text, rel, position."""
    target: str
    """What the link lands on: the status text for a broken target
    (``404``, ``error``, ``redirect_loop``), the final URL for a redirect."""


@dataclass(slots=True, frozen=True)
class LinkReport:
    """Everything the internal link graph says about one crawl, for printing."""

    pages: int
    """Crawled pages, every outcome."""
    links: int
    """Internal link instances from parsed pages to crawled pages, self-links included."""
    broken: tuple[ProblemLink, ...]
    """Links to targets that return an error, in page order."""
    redirecting: tuple[ProblemLink, ...]
    """Links to targets that redirect to a different page, in page order."""
    highest: tuple[str, int] | None
    """``(url, score)`` of the page with the highest Link Score."""
    lowest: tuple[str, int] | None
    unreachable: int
    """Pages the start page cannot reach by clicking; 0 in list mode."""

    def summary(self) -> str:
        """One line for the audit output."""
        parts = [f"Links: {self.links} internal links between {self.pages} pages"]
        if self.broken:
            parts.append(f"{len(self.broken)} to errors")
        if self.redirecting:
            parts.append(f"{len(self.redirecting)} to redirects")
        if self.unreachable:
            parts.append(f"{self.unreachable} page(s) unreachable from the start page")
        if self.highest and self.lowest:
            parts.append(
                f"Link Score {self.highest[1]} at {self.highest[0]} "
                f"down to {self.lowest[1]} at {self.lowest[0]}"
            )
        return "; ".join(parts) + "."


def link_report(crawl: CrawlView) -> LinkReport:
    """Walk every internal link in ``crawl`` and collect the ones worth reporting."""
    graph = crawl.link_graph
    broken: list[ProblemLink] = []
    redirecting: list[ProblemLink] = []
    count = 0
    for page in crawl.html_pages:
        for link in page.links:
            target = crawl.page_for(link.href)
            if target is None:
                continue
            count += 1
            if is_broken(target):
                broken.append(ProblemLink(page.url, link, target.status))
            elif redirects_elsewhere(crawl, target):
                redirecting.append(ProblemLink(page.url, link, target.final_url))
    unreachable = (
        sum(1 for m in graph.metrics.values() if m.link_depth is None)
        if crawl.start_page is not None
        else 0
    )
    return LinkReport(
        pages=len(crawl.pages),
        links=count,
        broken=tuple(broken),
        redirecting=tuple(redirecting),
        highest=graph.highest(),
        lowest=graph.lowest(),
        unreachable=unreachable,
    )


def anchor_texts(crawl: CrawlView) -> dict[str, list[tuple[str, int]]]:
    """What the site calls each page: anchor texts per crawled target, most used first.

    Keyed by the target page's URL; each value lists ``(text, count)`` over
    every internal link to it from a parsed page, self-links included, ties
    in alphabetical order. An image link with no text counts as ``""``.
    """
    texts: dict[str, Counter[str]] = defaultdict(Counter)
    for page in crawl.html_pages:
        for link in page.links:
            target = crawl.page_for(link.href)
            if target is not None:
                texts[target.url][link.text] += 1
    return {
        url: sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        for url, counter in sorted(texts.items())
    }
