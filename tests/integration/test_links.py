"""Phase 8 end to end: the link graph over the fixture crawl, the CLI, the store and the web UI."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from sitecrawler.analysis import anchor_texts, link_report
from sitecrawler.audit import CrawlView
from sitecrawler.cli.main import app
from sitecrawler.parse import parse_html
from sitecrawler.store import open_store
from sitecrawler.store.dump import dump_tables
from sitecrawler.store.schema import PageRow
from sitecrawler.web import create_app
from tests.conftest import FIXTURE_SITE, _url_path

runner = CliRunner()

BROKEN = {
    "/missing",
    "/loop-a",
    "/audit/server-error",
    "/audit/truncated",
    "/audit/redirect-to-missing",
}
"""Fixture routes a link lands on an error at (``routes.json``)."""

REDIRECTING = {"/redirect-start", "/audit/redirect-off-site"}
"""Fixture routes that redirect to a different page."""


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _fixture_links(paths: set[str]) -> set[tuple[str, str, str]]:
    """``(source path, href path, anchor text)`` for each fixture anchor pointing into ``paths``."""
    found: set[tuple[str, str, str]] = set()
    for file in FIXTURE_SITE.rglob("*.html"):
        served = _url_path(file)
        parsed = parse_html(file.read_text(encoding="utf-8"), f"https://fixture.test{served}")
        for anchor in parsed.anchors:
            href = anchor.href.removeprefix("https://fixture.test")
            if href in paths:
                found.add((served.rstrip("/") or "/", href, anchor.text))
    return found


def test_home_scores_highest_and_the_orphan_lowest(crawled_db: Path, site: str) -> None:
    with open_store(crawled_db) as store:
        crawl = CrawlView.from_store(store)
    metrics = crawl.link_graph.metrics
    scores = {url.removeprefix(site) or "/": m.link_score for url, m in metrics.items()}
    assert scores["/"] == 100
    assert scores["/"] > max(score for path, score in scores.items() if path != "/")
    assert scores["/orphan"] == 0
    assert scores["/orphan"] == min(scores.values())
    assert crawl.link_graph.highest() == (f"{site}/", 100)
    orphan = metrics[f"{site}/orphan"]
    assert (orphan.inlinks, orphan.follow_inlinks, orphan.link_depth) == (0, 0, None)
    depths = {url.removeprefix(site) or "/": m.link_depth for url, m in metrics.items()}
    assert depths["/"] == 0
    assert depths["/audit"] == 1
    assert depths["/audit/link-deep-1"] == 2
    assert depths["/audit/link-deep-3"] == 4
    assert depths["/about"] == 1  # also reached through /redirect-start
    assert depths["/blog/post-1"] == 2
    about = metrics[f"{site}/about"]
    assert about.inlinks == about.follow_inlinks + 1  # the nofollow-link page does not count


def test_every_link_to_an_error_or_redirect_is_reported_with_source_and_anchor(
    crawled_db: Path, site: str
) -> None:
    with open_store(crawled_db) as store:
        report = link_report(CrawlView.from_store(store))
    broken = {
        (p.src.removeprefix(site) or "/", p.link.href.removeprefix(site), p.link.text)
        for p in report.broken
    }
    redirecting = {
        (p.src.removeprefix(site) or "/", p.link.href.removeprefix(site), p.link.text)
        for p in report.redirecting
    }
    assert broken == _fixture_links(BROKEN)
    assert redirecting == _fixture_links(REDIRECTING)
    assert len(broken) == 5
    assert len(redirecting) == 2
    assert {p.target for p in report.broken} == {"404", "500", "error", "redirect_loop"}
    targets = {p.link.href.removeprefix(site): p.target for p in report.redirecting}
    assert targets == {
        "/redirect-start": f"{site}/about",
        "/audit/redirect-off-site": "https://example.org/elsewhere",
    }
    assert report.unreachable == 3  # /orphan, /blocked/sitemap-only, /audit/noindex-in-sitemap
    assert all(p.link.position == "body" for p in report.broken)


def test_links_report_command(crawled_db: Path, site: str) -> None:
    result = runner.invoke(app, ["links", "report", str(crawled_db), "--top", "3"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert f"error\t{site}/\t{site}/missing\t404\tDead link" in out
    assert f"redirect\t{site}/\t{site}/redirect-start\t{site}/about\tTwo-hop redirect" in out
    assert f"error\t{site}/audit\t{site}/audit/redirect-to-missing\t404\tRedirect to a 404" in out
    squashed = _squash(out)
    assert "LinkScorein" in squashed
    # the home page row: URL, score 100, 9 inlinks, depth 0 (Rich draws borders between cells)
    assert re.search(rf"{re.escape(site)}/\W+100\W+9\W+0\W", squashed)
    assert "..." in out  # the table is cut between the top and the bottom
    assert "5toerrors;2toredirects" in squashed
    full = runner.invoke(app, ["links", "report", str(crawled_db), "--top", "100"])
    assert full.exit_code == 0
    assert "..." not in full.output.split("error\t")[0]


def test_links_anchors_command(crawled_db: Path, site: str) -> None:
    result = runner.invoke(app, ["links", "anchors", str(crawled_db)])
    assert result.exit_code == 0, result.output
    lines = {tuple(line.split("\t")) for line in result.output.splitlines() if "\t" in line}
    assert (f"{site}/about", "1", "Click here") in lines
    assert (f"{site}/about", "1", "About us") in lines
    assert (f"{site}/", "9", "Home") in lines

    one = runner.invoke(app, ["links", "anchors", str(crawled_db), f"{site}/about/"])
    assert one.exit_code == 0, one.output
    assert all(
        line.startswith(f"{site}/about\t") for line in one.output.splitlines() if "\t" in line
    )
    assert "Click here" in one.output

    with open_store(crawled_db) as store:
        texts = anchor_texts(CrawlView.from_store(store))
    assert texts[f"{site}/missing"] == [("Dead link", 1)]

    missing = runner.invoke(app, ["links", "anchors", str(crawled_db), f"{site}/nope"])
    assert missing.exit_code == 2
    assert "not a page" in missing.output


def test_audit_stores_the_metrics_and_prints_the_summary(crawled_db: Path, site: str) -> None:
    result = runner.invoke(app, ["audit", str(crawled_db)])
    assert result.exit_code == 0, result.output
    assert "Links:" in result.output
    assert "link.few_inlinks" in result.output
    assert "link.to_error" in result.output
    with open_store(crawled_db) as store:
        with Session(store.engine) as session:
            rows = {
                url.removeprefix(site) or "/": (inlinks, depth, score)
                for url, inlinks, depth, score in session.execute(
                    select(
                        PageRow.url, PageRow.inlinks, PageRow.link_depth, PageRow.link_score
                    ).where(PageRow.state == "done")
                )
            }
        tables = {t.name: t for t in dump_tables(store, ("pages", "links"))}
    assert rows["/"] == (9, 0, 100)
    assert rows["/orphan"] == (0, None, 0)
    assert rows["/audit/link-deep-3"][1] == 4
    assert tables["pages"].columns[-3:] == ("inlinks", "link_depth", "link_score")
    home = next(r for r in tables["pages"].rows if r[0] == f"{site}/")
    assert home[-3:] == (9, 0, 100)
    assert tables["links"].columns[-1] == "position"
    positions = {
        (str(r[0]).removeprefix(site) or "/", str(r[1]).removeprefix(site)): r[-1]
        for r in tables["links"].rows
    }
    assert positions[("/audit", "/")] == "footer"
    assert positions[("/products", "/")] == "nav"
    assert positions[("/", "/about")] == "body"


def test_web_rows_and_detail_show_the_link_metrics(audited_db: Path, site: str) -> None:
    with TestClient(create_app(audited_db)) as client:
        rows = {row["url"]: row for row in client.get("/api/rows").json()["rows"]}
        home = rows[f"{site}/"]
        assert (home["link_score"], home["link_depth"], home["unique_inlinks"]) == (100, 0, 9)
        assert home["unreachable"] is False
        orphan = rows[f"{site}/orphan"]
        assert (orphan["link_score"], orphan["link_depth"], orphan["unreachable"]) == (
            0,
            None,
            True,
        )
        summary = client.get("/api/summary").json()
        assert summary["tabs"]["links"]["unreachable"] == 3
        assert summary["tabs"]["links"]["high_depth"] == 1
        assert summary["tabs"]["links"]["to_error"] == 2

        detail = client.get("/detail/inlinks", params={"url": f"{site}/about"}).text
        assert "Link Score" in detail
        assert "Click here" in detail
        assert "<td>body</td>" in detail
        details = client.get("/detail/details", params={"url": f"{site}/orphan"}).text
        assert "unreachable" in details
        outlinks = client.get("/detail/outlinks", params={"url": f"{site}/audit"}).text
        assert "<td>footer</td>" in outlinks
