"""The duplicate index: exact groups, near clusters, representatives and the blocking."""

from __future__ import annotations

import random

from sitecrawler.audit.duplicates import (
    MIN_WORDS,
    NEAR_DUPLICATE_DISTANCE,
    DuplicateIndex,
    _components,
    candidate_pairs,
)
from sitecrawler.models import Fingerprint, LinkRef, Outcome, PageRecord
from sitecrawler.parse import fingerprint_text, hamming
from tests.unit.audit.helpers import SITE, links, long_text, page, view

LONG = long_text(MIN_WORDS + 20)
LONG_NEAR = LONG.replace("word100 word101", "changed words")
LONG_OTHER = long_text(MIN_WORDS + 20, prefix="other")
SHORT = "a short page with the same few words on it"


def _page(path: str, text: str, **fields: object) -> PageRecord:
    return page(path, fingerprint=fingerprint_text(text), **fields)  # type: ignore[arg-type]


def test_exact_groups_near_clusters_and_lookups() -> None:
    pages = [
        _page("/", LONG_OTHER, links=links("/a", "/b", "/c")),
        _page("/a", LONG),
        _page("/b", LONG),
        _page("/c", LONG_NEAR),
        _page("/d", LONG_NEAR + " and a tail", found_on="list"),
        _page("/s1", SHORT),
        _page("/s2", SHORT),
        _page("/s3", SHORT + " plus"),
        page("/none", fingerprint=Fingerprint()),
        page("/not-parsed", fingerprint=None),
        page("/gone", 404, fingerprint=fingerprint_text(LONG)),
    ]
    index = view(pages).duplicates
    assert [p.url.removeprefix(SITE) for p in index.pages] == [
        "/",
        "/a",
        "/b",
        "/c",
        "/d",
        "/s1",
        "/s2",
        "/s3",
    ]
    assert [c.urls for c in index.exact] == [
        (f"{SITE}/a", f"{SITE}/b"),
        (f"{SITE}/s1", f"{SITE}/s2"),
    ]
    assert index.exact[0].representative == f"{SITE}/a"  # a and b tie on score; first URL wins
    assert index.exact_group(f"{SITE}/b") is index.exact[0]
    assert index.exact_group(f"{SITE}/c") is None
    assert index.exact_group(f"{SITE}/gone") is None  # not an HTML page
    # near clusters only over pages of MIN_WORDS or more: the short pages stay out
    assert [c.urls for c in index.near] == [(f"{SITE}/a", f"{SITE}/b", f"{SITE}/c", f"{SITE}/d")]
    cluster = index.near[0]
    assert index.near_cluster(f"{SITE}/d") is cluster
    assert index.near_cluster(f"{SITE}/s1") is None
    assert index.near_cluster(f"{SITE}/") is None
    assert cluster.others(f"{SITE}/a") == [pages[2], pages[3], pages[4]]
    a, c = pages[1], pages[3]
    assert 0 < index.distance(a, c) <= NEAR_DUPLICATE_DISTANCE
    assert index.distance(a, pages[2]) == 0
    assert index.same_text(a, pages[2])
    assert not index.same_text(a, c)
    assert index.max_distance == NEAR_DUPLICATE_DISTANCE
    assert index.min_words == MIN_WORDS


def test_representative_is_the_best_linked_member() -> None:
    pages = [
        _page("/", LONG_OTHER, links=links("/b", "/b", "/z")),
        _page("/b", LONG, links=links("/z")),
        _page("/z", LONG),
    ]
    crawl = view(pages)
    assert (
        crawl.link_graph.metrics[f"{SITE}/z"].link_score
        > crawl.link_graph.metrics[f"{SITE}/b"].link_score
    )
    assert crawl.duplicates.exact[0].representative == f"{SITE}/z"
    assert crawl.duplicates.near[0].representative == f"{SITE}/z"


def test_distance_and_floor_are_parameters() -> None:
    pages = [_page("/a", LONG), _page("/c", LONG_NEAR), _page("/s1", SHORT), _page("/s2", SHORT)]
    crawl = view(pages)
    strict = DuplicateIndex(crawl, max_distance=0)
    assert strict.near == ()
    loose = DuplicateIndex(crawl, max_distance=63, min_words=1)
    assert [c.urls for c in loose.near] == [(f"{SITE}/a", f"{SITE}/c", f"{SITE}/s1", f"{SITE}/s2")]
    assert [c.urls for c in DuplicateIndex(crawl, min_words=1).near] == [
        (f"{SITE}/a", f"{SITE}/c"),
        (f"{SITE}/s1", f"{SITE}/s2"),
    ]


def test_redirect_sources_and_blocked_pages_are_not_fingerprinted_members() -> None:
    pages = [
        _page("/a", LONG),
        _page("/moved", LONG, final_url=f"{SITE}/a"),
        page("/blocked", None, outcome=Outcome.BLOCKED, content_type=""),
    ]
    index = view(pages).duplicates
    assert [p.url for p in index.pages] == [f"{SITE}/a"]
    assert index.exact == ()
    assert view([]).duplicates.near == ()


def _brute_force(values: list[int], k: int) -> set[frozenset[int]]:
    parent = list(range(len(values)))

    def find(i: int) -> int:
        while parent[i] != i:
            i = parent[i]
        return i

    for a in range(len(values)):
        for b in range(a + 1, len(values)):
            if hamming(values[a], values[b]) <= k:
                parent[find(a)] = find(b)
    groups: dict[int, set[int]] = {}
    for i in range(len(values)):
        groups.setdefault(find(i), set()).add(i)
    return {frozenset(g) for g in groups.values()}


def test_blocking_finds_every_pair_within_the_distance() -> None:
    rng = random.Random(9)
    for k in (0, 3, 10, 63):
        values: list[int] = []
        for _ in range(60):
            base = rng.getrandbits(64)
            values.append(base)
            for _ in range(rng.randint(0, 3)):
                flipped = base
                for _ in range(rng.randint(0, k + 2)):
                    flipped ^= 1 << rng.randrange(64)
                values.append(flipped)
        expected = _brute_force(values, k)
        assert {frozenset(c) for c in _components(values, k)} == expected, k
        pairs = set(candidate_pairs(values, k))
        for group in expected:
            for a in group:
                for b in group:
                    if a < b and hamming(values[a], values[b]) <= k:
                        assert (a, b) in pairs or (b, a) in pairs


def test_candidate_pairs_only_compare_values_that_share_a_block() -> None:
    assert list(candidate_pairs([0, 2**64 - 1], 3)) == []
    assert list(candidate_pairs([0, 1], 3)) == [(0, 1), (0, 1), (0, 1)]  # three blocks agree
    assert list(candidate_pairs([], 3)) == []


def test_links_with_other_pages_do_not_matter_for_membership() -> None:
    pages = [_page("/a", LONG, links=(LinkRef("https://o.test/", "x"),)), _page("/b", LONG)]
    assert view(pages).duplicates.exact[0].urls == (f"{SITE}/a", f"{SITE}/b")
