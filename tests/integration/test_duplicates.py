"""Phase 9 end to end: clusters over the fixture crawl, the CLI, the store and the web UI."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from sitecrawler.analysis import duplicate_report
from sitecrawler.audit import CrawlView
from sitecrawler.audit.duplicates import MIN_WORDS, NEAR_DUPLICATE_DISTANCE
from sitecrawler.cli.main import app
from sitecrawler.store import open_store
from sitecrawler.store.dump import PAGE_COLUMNS, dump_tables
from sitecrawler.web import create_app
from tests.integration.test_audit import TRIGGERS

runner = CliRunner()

EXACT = ("/audit/dup-exact-1", "/audit/dup-exact-2", "/audit/dup-exact-canonical")
NEAR = ("/audit/dup-near-1", "/audit/dup-near-2")


def test_pages_differing_by_one_sentence_cluster_and_unrelated_pages_do_not(
    crawled_db: Path, site: str
) -> None:
    with open_store(crawled_db) as store:
        crawl = CrawlView.from_store(store)
    index = crawl.duplicates
    near = index.near_cluster(f"{site}/audit/dup-near-1")
    assert near is not None
    assert near.urls == tuple(f"{site}{p}" for p in NEAR)
    assert near.representative == f"{site}/audit/dup-near-1"
    one, two = near.members
    assert 0 < index.distance(one, two) <= NEAR_DUPLICATE_DISTANCE
    assert not index.same_text(one, two)
    # every other page of the fixture site is unrelated to the pair, so one near cluster
    # of two texts is the whole story; the identical trio is a cluster of one text
    assert [c.urls for c in index.near] == [
        tuple(f"{site}{p}" for p in EXACT),
        near.urls,
    ]
    exact = index.exact_group(f"{site}/audit/dup-exact-2")
    assert exact is not None
    assert exact.urls == tuple(f"{site}{p}" for p in EXACT)
    assert exact.representative == f"{site}/audit/dup-exact-1"
    assert index.exact_group(f"{site}/audit/dup-near-1") is None
    assert all(index.near_cluster(f"{site}{p}") is None for p in ("/", "/audit", "/about"))
    many = crawl.page_for(f"{site}/audit/many-outlinks")
    assert many is not None
    assert many.fingerprint is not None
    assert many.fingerprint.words >= MIN_WORDS  # compared, and still in no cluster
    assert index.near_cluster(many.url) is None


def test_duplicates_report_command(crawled_db: Path, site: str) -> None:
    result = runner.invoke(app, ["duplicates", "report", str(crawled_db)])
    assert result.exit_code == 0, result.output
    lines = [line.split("\t") for line in result.output.splitlines() if "\t" in line]
    rep = f"{site}/audit/dup-exact-1"
    assert ["exact", rep, rep, "0", "indexable"] in lines
    assert ["exact", rep, f"{site}/audit/dup-exact-2", "0", "indexable"] in lines
    assert [
        "exact",
        rep,
        f"{site}/audit/dup-exact-canonical",
        "0",
        f"canonicalised to {rep}",
    ] in lines
    near = [line for line in lines if line[0] == "near"]
    assert [line[2] for line in near] == [f"{site}{p}" for p in NEAR]
    assert near[0][3] == "0"
    assert 0 < int(near[1][3]) <= NEAR_DUPLICATE_DISTANCE
    assert "Duplicates: " in result.output
    assert "near-duplicate cluster(s)" in result.output

    strict = runner.invoke(app, ["duplicates", "report", str(crawled_db), "--max-distance", "0"])
    assert strict.exit_code == 0, strict.output
    assert "near\t" not in strict.output
    assert "exact\t" in strict.output
    bad = runner.invoke(app, ["duplicates", "report", str(crawled_db), "--max-distance", "64"])
    assert bad.exit_code == 2
    assert "between 0 and 63" in bad.output


def test_audit_prints_the_duplicate_summary(crawled_db: Path) -> None:
    result = runner.invoke(app, ["audit", str(crawled_db)])
    assert result.exit_code == 0, result.output
    assert "Duplicates: " in result.output
    assert "sitecrawlerduplicatesreport" in re.sub(r"\s+", "", result.output)  # Rich wraps
    with open_store(crawled_db) as store:
        counts = store.issue_counts()
    assert counts["content.duplicate"] == len(TRIGGERS["content.duplicate"])
    assert counts["content.near_duplicate"] == 2
    assert counts["content.low_word_count"] == len(TRIGGERS["content.low_word_count"])


def test_fingerprints_are_stored_and_exported(crawled_db: Path, site: str) -> None:
    with open_store(crawled_db) as store:
        pages = next(t for t in dump_tables(store, ("pages",)) if t.name == "pages")
        crawl = CrawlView.from_store(store)
    assert pages.columns[-3:] == ("content_words", "content_hash", "simhash")
    assert PAGE_COLUMNS[-3:] == ("content_words", "content_hash", "simhash")
    by_url = {row[0]: dict(zip(pages.columns, row, strict=True)) for row in pages.rows}
    one = by_url[f"{site}/audit/dup-exact-1"]
    two = by_url[f"{site}/audit/dup-exact-2"]
    assert one["content_hash"] == two["content_hash"]
    assert one["simhash"] == two["simhash"]
    assert len(str(one["content_hash"])) == 64
    assert len(str(one["simhash"])) == 16
    assert isinstance(one["content_words"], int)
    assert one["content_words"] >= MIN_WORDS
    missing = by_url[f"{site}/missing"]
    assert (missing["content_words"], missing["content_hash"], missing["simhash"]) == (
        None,
        None,
        None,
    )
    stored = crawl.page_for(f"{site}/audit/dup-exact-1")
    assert stored is not None
    assert stored.fingerprint is not None
    assert stored.fingerprint.content_hash == one["content_hash"]
    assert stored.fingerprint.simhash_hex == one["simhash"]
    report = duplicate_report(crawl)
    assert len(report.exact) == 2
    assert len(report.near) == 1


def test_content_tab_cells_and_detail(audited_db: Path, site: str) -> None:
    with TestClient(create_app(audited_db)) as client:
        rows = {r["url"]: r for r in client.get("/api/rows").json()["rows"]}
        one = rows[f"{site}/audit/dup-exact-1"]
        assert (one["exact_duplicates"], one["near_duplicates"], one["duplicate_of"]) == (2, 0, "")
        assert one["content_words"] >= MIN_WORDS
        assert len(one["content_hash"]) == 64
        copy = rows[f"{site}/audit/dup-exact-canonical"]
        assert copy["duplicate_of"] == f"{site}/audit/dup-exact-1"
        assert "content.duplicate" not in copy["rules"]
        near = rows[f"{site}/audit/dup-near-2"]
        assert (near["exact_duplicates"], near["near_duplicates"]) == (0, 1)
        assert near["duplicate_of"] == f"{site}/audit/dup-near-1"
        assert "content.near_duplicate" in near["rules"]
        missing = rows[f"{site}/missing"]
        assert (missing["content_words"], missing["content_hash"]) == (None, "")
        assert "content.low_word_count" in rows[f"{site}/blog/post-1"]["rules"]

        summary = client.get("/api/summary").json()["tabs"]["content"]
        assert summary["duplicate"] == len(TRIGGERS["content.duplicate"])
        assert summary["near_duplicate"] == 2
        assert summary["low_word_count"] == len(TRIGGERS["content.low_word_count"])
        assert summary["no_text"] == 0
        tabs = {t["id"]: t for t in client.get("/api/tabs").json()}
        assert "duplicate_of" in tabs["content"]["columns"]

        detail = client.get("/detail/content", params={"url": f"{site}/audit/dup-exact-2"}).text
        assert f'data-dup="{site}/audit/dup-exact-1"' in detail
        assert f'data-dup="{site}/audit/dup-exact-canonical"' in detail
        assert 'data-kind="exact"' in detail
        assert "canonicalised to" in detail
        near_detail = client.get("/detail/content", params={"url": f"{site}/audit/dup-near-1"}).text
        assert f'data-dup="{site}/audit/dup-near-2" data-kind="near"' in near_detail
        alone = client.get("/detail/content", params={"url": f"{site}/about"}).text
        assert "No other page shares" in alone
        assert "Main text words" in alone
