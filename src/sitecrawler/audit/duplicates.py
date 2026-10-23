"""Duplicate content index: exact groups and near-duplicate clusters (ADR-0012).

Built once per :class:`~sitecrawler.audit.view.CrawlView` and reached as
``crawl.duplicates``. Every parsed HTML page with any main text has a
:class:`~sitecrawler.models.Fingerprint`; pages with the same content hash
form an *exact group*, and pages of :data:`MIN_WORDS` words or more whose
SimHash values are within :data:`NEAR_DUPLICATE_DISTANCE` bits of each
other, directly or through other members, form a *near cluster*. Each has a
representative: the best-linked member (highest Link Score, then first URL).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from sitecrawler.models import PageRecord
from sitecrawler.parse.fingerprint import BITS, hamming

if TYPE_CHECKING:
    from sitecrawler.audit.view import CrawlView

NEAR_DUPLICATE_DISTANCE = 10
"""SimHash bits (of 64) two pages may differ by and still count as near-duplicates.

Ten bits is roughly 88% of three-word runs in common; three bits, the
textbook value for web-scale deduplication, would only catch pages that
differ by a word or two.
"""

MIN_WORDS = 200
"""Main-text words below which a page is low content.

Also the floor for near-duplicate clustering: below it the SimHash of a page
is a vote among a few dozen features and unrelated short pages land within
a few bits of each other.
"""


@dataclass(slots=True, frozen=True)
class Cluster:
    """Pages that share, or nearly share, their main text."""

    representative: str
    """The member to keep: highest Link Score, then the first URL."""
    members: tuple[PageRecord, ...]
    """Every member, in URL order; at least two."""

    @property
    def urls(self) -> tuple[str, ...]:
        """The members' URLs."""
        return tuple(p.url for p in self.members)

    def others(self, url: str) -> list[PageRecord]:
        """Every member except the one at ``url``."""
        return [p for p in self.members if p.url != url]

    @property
    def texts(self) -> frozenset[str]:
        """The distinct content hashes among the members; one means they are all identical."""
        return frozenset(_hash(p) for p in self.members)


def _hash(page: PageRecord) -> str:
    return page.fingerprint.content_hash if page.fingerprint else ""


def _simhash(page: PageRecord) -> int:
    return page.fingerprint.simhash if page.fingerprint else 0


def _words(page: PageRecord) -> int:
    return page.fingerprint.words if page.fingerprint else 0


def candidate_pairs(values: Sequence[int], max_distance: int) -> Iterator[tuple[int, int]]:
    """Index pairs of ``values`` that may be within ``max_distance`` bits of each other.

    Splits the 64 bits into ``max_distance + 1`` blocks: two values within
    the distance agree on at least one block (pigeonhole), so only values
    sharing a block are compared. A pair can come back more than once.
    """
    blocks = min(max_distance + 1, BITS)
    bounds = [BITS * i // blocks for i in range(blocks + 1)]
    for lo, hi in pairwise(bounds):
        mask = ((1 << (hi - lo)) - 1) << lo
        buckets: dict[int, list[int]] = defaultdict(list)
        for index, value in enumerate(values):
            buckets[value & mask].append(index)
        for members in buckets.values():
            for a in range(len(members)):
                for b in range(a + 1, len(members)):
                    yield members[a], members[b]


def _components(values: Sequence[int], max_distance: int) -> list[list[int]]:
    """Connected components of ``values`` under "within ``max_distance`` bits", as index lists."""
    parent = list(range(len(values)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in candidate_pairs(values, max_distance):
        if hamming(values[a], values[b]) <= max_distance:
            parent[find(a)] = find(b)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(values)):
        groups[find(i)].append(i)
    return list(groups.values())


class DuplicateIndex:
    """Exact groups and near clusters over the fingerprinted pages of one crawl."""

    def __init__(
        self,
        crawl: CrawlView,
        max_distance: int = NEAR_DUPLICATE_DISTANCE,
        min_words: int = MIN_WORDS,
    ) -> None:
        """Group the pages of ``crawl``; the work is done here, lookups are dict reads."""
        self.max_distance = max_distance
        self.min_words = min_words
        self.pages: list[PageRecord] = [
            p for p in crawl.html_pages if p.fingerprint is not None and not p.fingerprint.empty
        ]
        """Every page with a non-empty fingerprint, in URL order."""
        scores = crawl.link_graph.metrics
        self._rank = {p.url: (-scores[p.url].link_score, p.url) for p in self.pages}
        self._exact_of: dict[str, Cluster] = {}
        by_hash: dict[str, list[PageRecord]] = defaultdict(list)
        for page in self.pages:
            by_hash[_hash(page)].append(page)
        self.exact: tuple[Cluster, ...] = self._clusters(by_hash.values(), self._exact_of)
        """Groups of pages with identical main text, by representative URL."""
        self._near_of: dict[str, Cluster] = {}
        self.near: tuple[Cluster, ...] = self._clusters(self._near_groups(), self._near_of)
        """Clusters of pages within ``max_distance`` bits, by representative URL.

        Members have at least ``min_words`` words; a cluster may be made of
        exact duplicates alone."""

    def _near_groups(self) -> Iterable[list[PageRecord]]:
        eligible = [p for p in self.pages if _words(p) >= self.min_words]
        by_simhash: dict[int, list[PageRecord]] = defaultdict(list)
        for page in eligible:
            by_simhash[_simhash(page)].append(page)
        values = list(by_simhash)
        for component in _components(values, self.max_distance):
            yield [p for i in component for p in by_simhash[values[i]]]

    def _clusters(
        self, groups: Iterable[list[PageRecord]], lookup: dict[str, Cluster]
    ) -> tuple[Cluster, ...]:
        found: list[Cluster] = []
        for group in groups:
            if len(group) < 2:
                continue
            members = tuple(sorted(group, key=lambda p: p.url))
            representative = min(members, key=lambda p: self._rank[p.url]).url
            cluster = Cluster(representative, members)
            found.append(cluster)
            for page in members:
                lookup[page.url] = cluster
        return tuple(sorted(found, key=lambda c: c.representative))

    def exact_group(self, url: str) -> Cluster | None:
        """The exact group the page at ``url`` belongs to, or None."""
        return self._exact_of.get(url)

    def near_cluster(self, url: str) -> Cluster | None:
        """The near cluster the page at ``url`` belongs to, or None."""
        return self._near_of.get(url)

    @staticmethod
    def distance(a: PageRecord, b: PageRecord) -> int:
        """SimHash bits that differ between two pages."""
        return hamming(_simhash(a), _simhash(b))

    @staticmethod
    def same_text(a: PageRecord, b: PageRecord) -> bool:
        """True when the two pages' main text is identical."""
        return _hash(a) == _hash(b)
