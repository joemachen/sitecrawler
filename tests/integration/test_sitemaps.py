"""Phase 7 end to end: sitemap files and entries from a crawl, the report, generation."""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree
from typer.testing import CliRunner

from sitecrawler.analysis import sitemap_report
from sitecrawler.audit import CrawlView
from sitecrawler.cli.main import app
from sitecrawler.store import open_store
from tests.integration.test_audit import IN_SITEMAP, NON_INDEXABLE
from tests.unit.test_sitemap_export import SCHEMAS, locs

runner = CliRunner()


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def test_every_sitemap_file_is_recorded_with_its_outcome(crawled_db: Path, site: str) -> None:
    with open_store(crawled_db) as store:
        files = {f.url.removeprefix(site): f for f in store.sitemap_files()}
        entries = store.sitemap_entries()
    assert set(files) == {
        "/sitemap.xml",
        "/sitemap-index.xml",
        "/sitemap-extra.xml.gz",
        "/sitemap-missing.xml",
    }
    assert (files["/sitemap.xml"].found_in, files["/sitemap.xml"].kind) == ("robots.txt", "urlset")
    assert files["/sitemap.xml"].url_count == 7
    assert (files["/sitemap-index.xml"].kind, files["/sitemap-index.xml"].url_count) == ("index", 2)
    gz = files["/sitemap-extra.xml.gz"]
    assert (gz.found_in, gz.kind, gz.url_count) == (f"{site}/sitemap-index.xml", "urlset", 2)
    missing = files["/sitemap-missing.xml"]
    assert (missing.ok, missing.status_code, missing.error) == (False, 404, "status 404")

    twice = [e for e in entries if e.loc == f"{site}/audit/sitemap-twice"]
    assert sorted(e.sitemap_url.removeprefix(site) for e in twice) == [
        "/sitemap-extra.xml.gz",
        "/sitemap.xml",
    ]
    extra = next(e for e in twice if e.sitemap_url.endswith(".gz"))
    assert (extra.lastmod, extra.changefreq, extra.priority) == (
        "2026-10-20T09:30:00+00:00",
        "weekly",
        "0.8",
    )


def test_report_names_the_other_host_and_the_duplicate(crawled_db: Path, site: str) -> None:
    with open_store(crawled_db) as store:
        report = sitemap_report(CrawlView.from_store(store))
    assert [e.loc for e in report.other_host] == ["https://elsewhere.test/page"]
    assert report.not_crawled == ()
    assert list(report.duplicates) == [f"{site}/audit/sitemap-twice"]
    assert [f.url.removeprefix(site) for f in report.unreadable] == ["/sitemap-missing.xml"]
    assert report.entries == 9
    assert report.pages_listed == 8


def test_sitemap_report_command(crawled_db: Path, site: str) -> None:
    result = runner.invoke(app, ["sitemap", "report", str(crawled_db)])
    assert result.exit_code == 0, result.output
    out = result.output
    assert f"other host\thttps://elsewhere.test/page\t{site}/sitemap-extra.xml.gz" in out
    assert f"duplicate\t{site}/audit/sitemap-twice\t" in out
    assert "status404" in _squash(out)
    assert "3file(s)read,9entriesnaming8pages" in _squash(out)


def test_audit_prints_the_sitemap_summary_line(crawled_db: Path) -> None:
    result = runner.invoke(app, ["audit", str(crawled_db)])
    assert result.exit_code == 0, result.output
    assert "Sitemaps:3file(s)read" in _squash(result.output)
    assert "sitemap.orphan" in result.output
    assert "sitemap.non_indexable" in result.output
    assert "sitemap.missing" in result.output


def test_generate_writes_every_indexable_200_page_and_validates(
    crawled_db: Path, site: str, tmp_path: Path, pages: frozenset[str]
) -> None:
    out = tmp_path / "generated.xml"
    result = runner.invoke(app, ["sitemap", "generate", str(crawled_db), "-o", str(out)])
    assert result.exit_code == 0, result.output
    doc = etree.parse(out)
    etree.XMLSchema(etree.parse(SCHEMAS / "sitemap.xsd")).assertValid(doc)
    written = {u.removeprefix(site) or "/" for u in locs(doc)}
    assert written == pages - set(NON_INDEXABLE)
    assert "/blog/post-2" in written  # the page sitemap.missing flags
    assert "/orphan" in written
    assert "/blocked/secret" not in written
    assert not written & (set(NON_INDEXABLE) - IN_SITEMAP)
    assert "<lastmod>" not in out.read_text(encoding="utf-8")
    assert f"{len(written)}URLswrittento" in _squash(result.output)


def test_generate_lastmod_comes_from_the_header(
    crawled_db: Path, site: str, tmp_path: Path
) -> None:
    out = tmp_path / "sitemap.xml"
    result = runner.invoke(
        app, ["sitemap", "generate", str(crawled_db), "-o", str(out), "--lastmod"]
    )
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    # Only /notitle sends Last-Modified, and it is noindex, so no page qualifies for lastmod
    assert "<lastmod>" not in text
    etree.XMLSchema(etree.parse(SCHEMAS / "sitemap.xsd")).assertValid(etree.parse(out))


def test_generate_default_output_sits_next_to_the_db(crawled_db: Path) -> None:
    result = runner.invoke(app, ["sitemap", "generate", str(crawled_db)])
    assert result.exit_code == 0, result.output
    assert (crawled_db.parent / "sitemap.xml").is_file()


def test_generate_fails_cleanly_on_an_unwritable_output(crawled_db: Path, tmp_path: Path) -> None:
    out = tmp_path / "no-such-dir" / "sitemap.xml"
    result = runner.invoke(app, ["sitemap", "generate", str(crawled_db), "-o", str(out)])
    assert result.exit_code == 2
    assert "cannot write" in result.output


def test_generate_rejects_a_non_db(tmp_path: Path) -> None:
    bogus = tmp_path / "x.db"
    bogus.write_text("nope")
    result = runner.invoke(app, ["sitemap", "generate", str(bogus)])
    assert result.exit_code == 2
