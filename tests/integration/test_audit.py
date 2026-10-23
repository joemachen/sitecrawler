"""Every rule against the stored fixture crawl: exactly these pages trigger it.

Add a line to ``TRIGGERS`` for every new rule. A rule that is missing from the
table fails the test, and so does a rule that fires on a page not listed
here, so each rule has a triggering page and the rest of the site is the
non-triggering case.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sitecrawler.audit import CrawlView, load_rules, run_audit
from sitecrawler.crawl import Crawler
from sitecrawler.models import CrawlConfig
from sitecrawler.store import open_store
from tests.conftest import follow_inlink_sources, site_pages

OLD_HTML = {
    "/",
    "/about",
    "/blog",
    "/blog/post-1",
    "/blog/post-2",
    "/notitle",
    "/dup-title-1",
    "/dup-title-2",
    "/orphan",
}
"""Phase 0 pages: written before the content rules existed, so they trip several."""

CANONICALISED = {
    "/about",
    "/audit/canonical-to-404",
    "/audit/canonical-off-site",
    "/audit/canonical-chain-1",
    "/audit/canonical-chain-2",
    "/audit/canonical-conflict",
    "/audit/paged-bad-2",
    "/audit/dup-exact-canonical",
}
"""Linked pages whose effective canonical is a different URL."""

DUPLICATE_CONTENT = {
    "/audit/dup-exact-1",
    "/audit/dup-exact-2",
    "/audit/dup-exact-canonical",
    "/audit/dup-near-1",
    "/audit/dup-near-2",
}
"""Phase 9 fixtures: long articles, so the only fixture pages over the low-content floor
besides ``/audit/many-outlinks`` (301 anchor texts)."""

TRIGGERS: dict[str, set[str]] = {
    "response.4xx": {"/missing"},
    "response.5xx": {"/audit/server-error"},
    "response.error": {"/audit/truncated"},
    "response.blocked_by_robots": {"/blocked/sitemap-only"},
    "redirect.chain": {"/redirect-start"},
    "redirect.loop": {"/loop-a"},
    "redirect.to_error": {"/audit/redirect-to-missing"},
    "redirect.off_site": {"/audit/redirect-off-site"},
    "redirect.temporary": {"/redirect-start"},
    "link.to_redirect": {"/", "/audit"},
    "title.missing": {"/notitle"},
    "title.duplicate": {"/dup-title-1", "/dup-title-2"},
    "title.too_long": {"/audit/title-long"},
    "title.too_short": (OLD_HTML - {"/notitle"}) | {"/audit", "/audit/title-short"},
    "title.multiple": {"/audit/title-multiple"},
    "title.same_as_h1": {"/blog", "/blog/post-1", "/blog/post-2", "/audit/title-same-as-h1"},
    "meta_description.missing": OLD_HTML - {"/", "/about"},
    "meta_description.duplicate": {"/audit/meta-dup-1", "/audit/meta-dup-2"},
    "meta_description.too_long": {"/audit/meta-long"},
    "meta_description.too_short": {"/", "/about", "/audit", "/audit/meta-short"},
    "meta_description.multiple": {"/audit/meta-multiple"},
    "h1.missing": {"/notitle"},
    "h1.multiple": {"/about"},
    "h1.duplicate": {"/audit/h1-dup-1", "/audit/h1-dup-2"} | DUPLICATE_CONTENT,
    "h1.too_long": {"/audit/h1-long"},
    "h2.missing": OLD_HTML,
    "canonical.missing": (OLD_HTML - {"/", "/about"})
    | {"/audit/canonical-missing", "/js-injected"},
    "canonical.to_non_200": {"/audit/canonical-to-404"},
    "canonical.off_site": {"/about", "/audit/canonical-off-site"},
    "canonical.chain": {"/audit/canonical-chain-1"},
    "canonical.canonicalised_but_linked": CANONICALISED,
    "canonical.not_self_referencing": CANONICALISED,
    "canonical.og_url_mismatch": {"/audit/og-url-mismatch"},
    "canonical.conflict": {"/audit/canonical-conflict"},
    "robots.noindex": {
        "/notitle",
        "/audit/noindex",
        "/audit/noindex-in-sitemap",
        "/audit/robots-conflict",
    },
    "robots.nofollow": {"/audit/nofollow"},
    "robots.none": {"/audit/robots-none"},
    "robots.conflicting": {"/audit/robots-conflict"},
    "robots.noindex_in_sitemap": {"/audit/noindex-in-sitemap"},
    "robots.noindex_linked": {
        "/notitle",
        "/audit/noindex",
        "/audit/robots-conflict",
        "/audit/robots-none",
    },
    "robots.blocked_but_linked": {"/blocked/secret"},
    "hreflang.invalid_lang": {"/audit/hreflang-bad"},
    "hreflang.missing_self": {"/audit/hreflang-bad"},
    "hreflang.missing_x_default": {"/audit/hreflang-bad", "/audit/hreflang-no-return"},
    "hreflang.missing_return_link": {"/audit/hreflang-bad"},
    "hreflang.to_non_200": {"/audit/hreflang-bad"},
    "hreflang.to_non_canonical": {"/audit/hreflang-bad"},
    "pagination.to_non_200": {"/audit/paged-bad-1"},
    "pagination.canonical_to_first": {"/audit/paged-bad-2"},
    "pagination.broken_sequence": {"/audit/paged-bad-2"},
    # Rendering rules need --render; tests/integration/test_render.py crawls the site with it
    # and expects /js-injected under render.differs and /audit/render-download under render.failed.
    "render.differs": set(),
    "render.failed": set(),
    "sitemap.orphan": {"/orphan"},
    "link.to_error": {"/", "/audit"},
    "link.high_depth": {"/audit/link-deep-3"},
    "link.generic_anchor": {"/audit/generic-anchor"},
    "link.nofollow_internal": {"/audit/nofollow-link"},
    "link.too_many_outlinks": {"/audit/many-outlinks"},
    "sitemap.non_indexable": {
        "/about",
        "/blocked/secret",
        "/blocked/sitemap-only",
        "/audit/noindex-in-sitemap",
    },
    "sitemap.duplicate": {"/audit/sitemap-twice"},
    # h1-dup-1 and h1-dup-2 share their whole (tiny) main text, not just the H1.
    "content.duplicate": {
        "/audit/dup-exact-1",
        "/audit/dup-exact-2",
        "/audit/h1-dup-1",
        "/audit/h1-dup-2",
    },
    "content.near_duplicate": {"/audit/dup-near-1", "/audit/dup-near-2"},
    # /audit/schema-product is complete and trips none of these.
    "schema.invalid_json": {"/audit/schema-invalid-json"},
    "schema.missing_required": {"/audit/schema-no-price"},
    "schema.unknown_type": {"/audit/schema-unknown"},
    "schema.conflicting": {"/audit/schema-conflict"},
    "schema.unknown_property": {"/audit/schema-unknown"},
    "schema.missing_recommended": {"/audit/schema-article"},
}

IN_SITEMAP = {
    "/",
    "/about",
    "/orphan",
    "/blocked/secret",
    "/blocked/sitemap-only",
    "/audit/noindex-in-sitemap",
    "/audit/sitemap-twice",
}
"""On-site pages the fixture sitemaps list (``tests/fixtures/site/sitemap*.xml``)."""

NON_INDEXABLE: dict[str, str] = {
    "/missing": "status 404",
    "/audit/server-error": "status 500",
    "/audit/truncated": "fetch error",
    "/blocked/secret": "blocked by robots.txt",
    "/loop-a": "redirect loop",
    "/redirect-start": "redirects to",
    "/audit/redirect-to-missing": "redirects to",
    "/audit/redirect-off-site": "redirects to https://example.org/elsewhere",
    "/about": "canonicalised to https://www.fixture.test/about",
    "/notitle": "noindex",
    "/blocked/sitemap-only": "blocked by robots.txt",
    "/audit/noindex": "noindex",
    "/audit/noindex-in-sitemap": "noindex",
    "/audit/robots-none": "noindex",
    "/audit/robots-conflict": "noindex",
    "/audit/canonical-to-404": "canonicalised to",
    "/audit/canonical-off-site": "canonicalised to https://example.org/elsewhere",
    "/audit/canonical-chain-1": "canonicalised to",
    "/audit/canonical-chain-2": "canonicalised to",
    "/audit/canonical-conflict": "canonicalised to",
    "/audit/paged-bad-2": "canonicalised to",
    "/audit/dup-exact-canonical": "canonicalised to",
}
TRIGGERS["page.non_indexable"] = set(NON_INDEXABLE)
TRIGGERS["content.low_word_count"] = (
    set(site_pages()) - set(NON_INDEXABLE) - DUPLICATE_CONTENT - {"/audit/many-outlinks"}
)
"""Every indexable page under 200 words of main text: the whole fixture site bar the
Phase 9 articles and the 301-link page."""
TRIGGERS["sitemap.missing"] = set(site_pages()) - set(NON_INDEXABLE) - IN_SITEMAP
"""Every indexable 200 page the sitemaps do not list; ``/blog/post-2`` is the roadmap's example."""
WELL_LINKED = {path for path, sources in follow_inlink_sources().items() if len(sources) >= 2}
TRIGGERS["link.few_inlinks"] = set(site_pages()) - set(NON_INDEXABLE) - {"/"} - WELL_LINKED
"""Every indexable page (bar the start page) with at most one other page linking to it
without nofollow: most of the audit fixtures, which only the hub links to."""


@pytest.fixture
def audited(site: str, tmp_path: Path) -> tuple[CrawlView, dict[str, set[str]]]:
    path = tmp_path / "crawl.db"
    with open_store(path) as store:
        Crawler(CrawlConfig(start_url=site, delay_seconds=0, workers=1), sink=store).run()
        crawl = CrawlView.from_store(store)
        result = run_audit(crawl)
        store.replace_issues(result.issues)
        store.set_indexability(result.verdicts)
        stored = store.iter_issues()
    by_rule: dict[str, set[str]] = {r.id: set() for r in load_rules()}
    for issue in stored:
        by_rule[issue.rule_id].add(issue.url.removeprefix(site))
    return crawl, by_rule


def test_every_rule_is_in_the_table() -> None:
    assert sorted(TRIGGERS) == [r.id for r in load_rules()]


@pytest.mark.parametrize("rule_id", sorted(TRIGGERS))
def test_rule_fires_on_exactly_its_fixture_pages(
    audited: tuple[CrawlView, dict[str, set[str]]], rule_id: str
) -> None:
    _, by_rule = audited
    assert by_rule[rule_id] == TRIGGERS[rule_id]


def test_indexability_verdicts(
    audited: tuple[CrawlView, dict[str, set[str]]], site: str, pages: frozenset[str]
) -> None:
    crawl, _ = audited
    result = run_audit(crawl)
    non_indexable = {
        url.removeprefix(site): v.reason for url, v in result.verdicts.items() if not v.indexable
    }
    assert set(non_indexable) == set(NON_INDEXABLE)
    for path, reason in NON_INDEXABLE.items():
        assert non_indexable[path].startswith(reason), path
    assert len(result.verdicts) == len(pages)


def test_audit_table_and_verdicts_are_stored(site: str, tmp_path: Path) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from sitecrawler.store.schema import PageRow

    path = tmp_path / "c.db"
    with open_store(path) as store:
        Crawler(CrawlConfig(start_url=site, delay_seconds=0, workers=1), sink=store).run()
        result = run_audit(CrawlView.from_store(store))
        assert store.replace_issues(result.issues) == len(result.issues)
        store.set_indexability(result.verdicts)
        assert store.issue_counts()["response.4xx"] == 1
        assert [i.rule_id for i in store.iter_issues("response.5xx")] == ["response.5xx"]
        with Session(store.engine) as s:
            row = s.scalars(select(PageRow).where(PageRow.url == f"{site}/missing")).one()
            assert row.indexable is False
            assert row.indexability_reason == "status 404"
            ok = s.scalars(select(PageRow).where(PageRow.url == f"{site}/blog/post-1")).one()
            assert ok.indexable is True
        # a second run replaces rather than appends
        assert store.replace_issues(result.issues) == len(result.issues)
        assert sum(store.issue_counts().values()) == len(result.issues)
