"""Computed row cells, audit cells and the RowStore over a small stored crawl."""

from __future__ import annotations

from pathlib import Path

from sitecrawler.audit import run_audit
from sitecrawler.models import (
    CrawlConfig,
    HreflangRef,
    LinkRef,
    Outcome,
    PageRecord,
    RedirectHop,
    SitemapEntry,
    SitemapFile,
)
from sitecrawler.session import CrawlSession
from sitecrawler.store import open_store
from sitecrawler.web.rows import NO_AUDIT, AuditIndex, RowStore, base_row, external_rows
from tests.unit.audit.helpers import SITE, blocked, links, page, view


def test_base_row_computes_lengths_counts_and_kinds() -> None:
    record = page(
        "/a_b",
        title="Hello",
        meta_description="Desc",
        h1="One",
        h1s=("One", "Two"),
        h2s=("Sub", "Sub2"),
        hreflang=(HreflangRef("en", f"{SITE}/a_b"), HreflangRef("fr", f"{SITE}/fr/a_b")),
        rel_next=f"{SITE}/a_b?page=2",
        meta_robots="noindex, follow",
        headers={"x-robots-tag": "nofollow"},
        links=(*links("/x", "/y", rel="nofollow"), LinkRef("https://other.test/z", "z")),
    )
    row = base_row(record, sitemap=frozenset({f"{SITE}/a_b"}))
    assert row["status_class"] == "2xx"
    assert row["first_status"] == 200
    assert row["content_class"] == "html"
    assert (row["title_length"], row["meta_length"], row["h1_length"]) == (5, 4, 3)
    assert (row["h1_count"], row["h2_count"], row["h2"]) == (2, 2, "Sub")
    assert row["canonical_kind"] == "self"
    assert row["has_canonical"] is True
    assert row["directives"] == "follow nofollow noindex"
    assert row["x_robots_tag"] == "nofollow"
    assert (row["outlinks"], row["outlinks_internal"], row["outlinks_external"]) == (3, 2, 1)
    assert row["nofollow_outlinks"] == 2
    assert (row["hreflang_count"], row["hreflang_langs"]) == (2, "en, fr")
    assert row["paginated"] is True
    assert row["url_flags"] == "underscores"
    assert row["in_sitemap"] is True


def test_url_flags_and_long_urls() -> None:
    long_path = "/" + "x" * 120
    row = base_row(page(f"/Caf%C3%A9?b=1&a=2{long_path}".replace("%C3%A9", "é")))
    assert set(str(row["url_flags"]).split()) == {"non_ascii", "uppercase", "parameters", "long"}
    assert row["url_length"] == len(row["url"])  # type: ignore[arg-type]


def test_status_class_uses_the_first_hop_and_outcomes() -> None:
    redirected = page(
        "/r",
        final_url=f"{SITE}/t",
        redirect_hops=(RedirectHop(1, f"{SITE}/r", f"{SITE}/t", 301),),
    )
    assert base_row(redirected)["status_class"] == "3xx"
    assert base_row(redirected)["first_status"] == 301
    assert base_row(redirected)["redirect_hops"] == 1
    assert base_row(redirected)["canonical_kind"] == "self"  # the helper sets a self canonical
    assert base_row(page("/m", status=404))["status_class"] == "4xx"
    assert base_row(page("/m", status=404))["canonical_kind"] == ""
    assert base_row(blocked("/b"))["status_class"] == "blocked"
    assert base_row(blocked("/b"))["content_class"] == ""
    error = PageRecord(url=f"{SITE}/e", outcome=Outcome.ERROR, depth=1, found_on="x", error="boom")
    assert base_row(error)["status_class"] == "no_response"
    loop = PageRecord(
        url=f"{SITE}/l",
        outcome=Outcome.REDIRECT_LOOP,
        depth=1,
        found_on="x",
        redirect_hops=(RedirectHop(1, f"{SITE}/l", f"{SITE}/l2", 302),),
    )
    assert base_row(loop)["status_class"] == "3xx"


def test_canonical_kinds() -> None:
    assert base_row(page("/a", canonical=""))["canonical_kind"] == "missing"
    assert base_row(page("/a", canonical=f"{SITE}/b"))["canonical_kind"] == "other"
    assert base_row(page("/a", canonical=f"{SITE}/a/"))["canonical_kind"] == "self"
    header = page("/a", canonical="", canonical_header=f"{SITE}/c")
    assert base_row(header)["canonical_kind"] == "other"


def test_external_rows_aggregate_link_targets() -> None:
    home = page(
        "/", links=(LinkRef("https://o.test/x", "x"), LinkRef("https://o.test/y", "y", "nofollow"))
    )
    a = page(
        "/a", links=(LinkRef("https://o.test/x", "again", "nofollow"), LinkRef("mailto:a@b", "m"))
    )
    rows = external_rows([home, a])
    assert [r["url"] for r in rows] == ["https://o.test/x", "https://o.test/y"]
    assert rows[0] == {
        "url": "https://o.test/x",
        "inlinks": 2,
        "nofollow_inlinks": 1,
        "nofollow_only": False,
        "first_found_on": f"{SITE}/",
    }
    assert rows[1]["nofollow_only"] is True


def test_audit_index_cells() -> None:
    home = page("/", links=links("/missing", "/a"))
    a = page("/a", links=links("/missing"))
    missing = page("/missing", status=404, title="", h1s=(), links=())
    v = view([home, a, missing], sitemap_urls=[f"{SITE}/missing"])
    index = AuditIndex(1, run_audit(v), v)
    cells = index.cells(f"{SITE}/missing")
    assert cells["indexable"] is False
    assert cells["indexability_reason"] == "status 404"
    assert cells["inlinks"] == 2
    assert cells["issues_n"] == len(cells["rules"])  # type: ignore[arg-type]
    assert "response.4xx" in cells["rules"]  # type: ignore[operator]
    assert cells["rules"][0] == "response.4xx"  # type: ignore[index]  # most severe first
    assert "sitemap.non_indexable" in cells["rules"]  # type: ignore[operator]
    assert index.cells("https://nowhere.test/") == {**NO_AUDIT, "inlinks": 0}


def _stored_session(tmp_path: Path, records: list[PageRecord]) -> CrawlSession:
    db = tmp_path / "crawl.db"
    with open_store(db) as store:
        store.begin(CrawlConfig(start_url=f"{SITE}/"), resume=False)
        sitemap = f"{SITE}/sitemap.xml"
        store.seeded(
            [],
            [SitemapFile(sitemap, "robots.txt", "urlset", 200, "", 1)],
            [SitemapEntry(sitemap, f"{SITE}/a", lastmod="2026-03-04")],
        )
        for record in records:
            store.page_done(record, [])
        store.finish(pages_done=len(records), complete=True)
    return CrawlSession.open(db, tmp_path / "crawls")


def test_row_store_rows_patches_and_summary(tmp_path: Path) -> None:
    session = _stored_session(
        tmp_path,
        [
            page("/", links=links("/a", "/missing")),
            page("/a", title="", links=links("/missing")),
            page("/missing", status=404, title="", h1s=(), links=()),
        ],
    )
    store = RowStore(session)

    first = store.rows()
    assert (first.seq, first.audit_rev, first.full) == (3, 1, False)
    assert [r["url"] for r in first.rows] == [f"{SITE}/", f"{SITE}/a", f"{SITE}/missing"]
    assert first.rows[1]["rules"] == ["title.missing"] or "title.missing" in first.rows[1]["rules"]  # type: ignore[operator]
    assert first.patches == []

    later = store.rows(since=2, rev=1)
    assert [r["url"] for r in later.rows] == [f"{SITE}/missing"]
    assert later.patches == []

    stale = store.rows(since=2, rev=0)  # every earlier row changed at rev 1: send the table
    assert stale.full is True
    assert len(stale.rows) == 3

    summary = store.summary()
    assert summary.pages == 3
    assert (summary.indexable, summary.non_indexable) == (2, 1)
    assert summary.status == {"2xx": 2, "4xx": 1}
    assert summary.depth == {"0": 3}
    assert summary.tabs["titles"]["missing"] == 1  # /missing is a 404, not a parsed page
    assert summary.tabs["response_codes"]["4xx"] == 1
    assert summary.tabs["sitemaps"]["in_sitemap"] == 1
    assert summary.tabs["links"]["no_inlinks"] == 1
    assert summary.tabs["issues"]["all"] == len(store.rule_rows())
    assert summary.issues["high"] >= 1
    assert store.summary() is summary  # cached at the same (seq, rev)

    assert store.issue_count("title.missing") == 1
    assert [r["url"] for r in store.issues_for("title.missing")] == [f"{SITE}/a"]
    assert store.audited
    session.close()


def test_row_store_lookup_and_page_detail(tmp_path: Path) -> None:
    session = _stored_session(
        tmp_path,
        [
            page("/", links=links("/a", "/missing")),
            page("/a", links=(*links("/missing"), LinkRef("https://o.test/", "o"))),
            page("/missing", status=404, title="", h1s=(), links=()),
        ],
    )
    store = RowStore(session)
    assert store.lookup(f"{SITE}/a/") is not None
    assert store.lookup("http://site.test/a") is not None
    assert store.lookup("https://elsewhere.test/") is None
    assert store.lookup("not a url") is None

    detail = store.page_detail(f"{SITE}/missing")
    assert detail is not None
    assert (detail.indexable, detail.indexability_reason) == (False, "status 404")
    assert detail.issues[0]["rule_id"] == "response.4xx"
    assert detail.issues[0]["summary"] == store.rules["response.4xx"].summary
    assert sorted(i.src for i in detail.inlinks) == [f"{SITE}/", f"{SITE}/a"]

    a = store.page_detail(f"{SITE}/a")
    assert a is not None
    assert [(o["href"], o["crawled"]) for o in a.outlinks] == [
        (f"{SITE}/missing", True),
        ("https://o.test/", False),
    ]
    assert store.page_detail("https://elsewhere.test/") is None
    session.close()
