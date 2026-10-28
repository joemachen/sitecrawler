"""Crawl the fixture site with ``--render``: the JS-injected page is seen as a browser sees it.

Needs ``uv run playwright install chromium``; deselect with ``-m "not browser"``.
These run on the main thread through ``Crawler.run`` and Playwright's async
API, so they must not share a session with the sync Playwright used by
``tests/e2e/test_web_ui.py`` (that one is opened per module, see there).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer
from typer.testing import CliRunner
from werkzeug.wrappers import Request, Response

from sitecrawler.audit import CrawlView, run_audit
from sitecrawler.cli.main import app
from sitecrawler.crawl import Crawler, Renderer, RenderUnavailableError
from sitecrawler.models import CrawlConfig, PageRecord
from sitecrawler.store import open_store
from tests.conftest import serve_site, site_pages

pytestmark = pytest.mark.browser

RAW_TITLE = "Raw title before JavaScript runs on this page"
RENDERED_TITLE = "Rendered title set by JavaScript on load"


def _config(site: str, **options: object) -> CrawlConfig:
    return CrawlConfig(start_url=site, delay_seconds=0, workers=1, **options)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def site_module() -> Iterator[str]:
    """The fixture site on a server of its own, so one rendered crawl can serve the module."""
    server = HTTPServer(host="127.0.0.1", port=0)
    server.start()
    try:
        yield serve_site(server)
    finally:
        server.stop()


@pytest.fixture(scope="module")
def rendered(site_module: str) -> dict[str, PageRecord]:
    """One rendered crawl of the whole site, shared by the module (Chromium is slow to start)."""
    records = Crawler(_config(site_module, render=True, render_timeout_seconds=15)).run()
    return {r.url.removeprefix(site_module): r for r in records}


@pytest.mark.skipif(sys.platform != "win32", reason="Microsoft Edge ships with Windows")
def test_falls_back_to_edge_without_playwrights_chromium(
    site: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An empty browsers folder is what the exe sees: no `playwright install chromium`.
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    records = Crawler(_config(site, max_pages=100, render=True, render_timeout_seconds=15)).run()
    page = next(r for r in records if r.url.endswith("/js-injected"))
    assert page.render_status == "rendered"
    assert page.title == RENDERED_TITLE


def test_neither_chromium_nor_edge_is_a_render_unavailable_error(
    site: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    monkeypatch.setattr("sitecrawler.crawl.renderer.EDGE_CHANNEL", "no-such-browser")
    with pytest.raises(
        RenderUnavailableError, match=r"could not start Chromium .* or Microsoft Edge"
    ):
        Crawler(_config(site, render=True)).run()


def test_without_render_the_page_is_what_the_server_sent(site: str) -> None:
    records = Crawler(_config(site, max_pages=100)).run()
    page = next(r for r in records if r.url.endswith("/js-injected"))
    assert page.title == RAW_TITLE
    assert page.canonical == ""
    assert page.links == ()
    assert page.render is None
    assert page.render_error == ""
    assert page.render_ms == 0


def test_with_render_the_injected_title_canonical_and_links_are_reported(
    rendered: dict[str, PageRecord], site_module: str
) -> None:
    page = rendered["/js-injected"]
    assert page.title == RENDERED_TITLE
    assert page.canonical == f"{site_module}/js-injected"
    assert [link.href for link in page.links] == [
        f"{site_module}/about",
        f"{site_module}/blog/",
        f"{site_module}/audit/",
    ]
    assert page.internal_links == 3
    assert page.render_ms > 0
    assert page.render_error == ""


def test_diff_lists_exactly_the_injected_items(
    rendered: dict[str, PageRecord], site_module: str
) -> None:
    diff = rendered["/js-injected"].render
    assert diff is not None
    assert diff.changes == ("title", "canonical", "links")
    assert (diff.raw_title, diff.rendered_title) == (RAW_TITLE, RENDERED_TITLE)
    assert (diff.raw_canonical, diff.rendered_canonical) == ("", f"{site_module}/js-injected")
    assert (diff.raw_link_count, diff.rendered_link_count) == (0, 3)
    assert diff.links_added == (
        f"{site_module}/about",
        f"{site_module}/blog/",
        f"{site_module}/audit/",
    )
    assert diff.links_removed == ()
    assert diff.describe() == "title, canonical, links +3"


def test_every_other_html_page_renders_the_same_as_its_raw_html(
    rendered: dict[str, PageRecord],
) -> None:
    assert set(rendered) == set(site_pages())
    html = {path: r for path, r in rendered.items() if r.render is not None}
    assert "/js-injected" in html
    failed = sorted(path for path, r in rendered.items() if r.render_error)
    assert failed == ["/audit/render-download"], "the download fixture is the only failure"
    assert rendered["/audit/render-download"].render_error.startswith("render failed: ")
    differing = sorted(path for path, r in html.items() if r.render and r.render.changed)
    assert differing == ["/js-injected"]
    # redirect sources carry the target's content and are not rendered themselves
    assert rendered["/redirect-start"].render is None
    assert rendered["/redirect-start"].render_error == ""
    # pages that are not parsable HTML are never rendered
    assert rendered["/missing"].render is None
    assert rendered["/audit/server-error"].render is None
    assert rendered["/blocked/secret"].render is None


def test_render_rules_fire_only_on_the_fixture_page(rendered: dict[str, PageRecord]) -> None:
    result = run_audit(CrawlView.from_records(rendered.values()))
    by_rule: dict[str, set[str]] = {}
    for issue in result.issues:
        by_rule.setdefault(issue.rule_id, set()).add(issue.url.rsplit("/", 1)[-1])
    assert by_rule["render.differs"] == {"js-injected"}
    assert by_rule["render.failed"] == {"render-download"}
    message = next(i.message for i in result.issues if i.rule_id == "render.differs")
    assert message == "title, canonical, links +3"
    # the rendered canonical is self-referencing, so canonical.missing no longer fires
    assert "js-injected" not in by_rule.get("canonical.missing", set())


def test_render_timeout_is_reported_not_raised(site: str) -> None:
    config = CrawlConfig(
        seed_urls=(f"{site}/js-injected",),
        follow_links=False,
        delay_seconds=0,
        render=True,
        render_selector="#never-appears",
        render_timeout_seconds=0.5,
    )
    (page,) = Crawler(config).run()
    assert page.status_code == 200
    assert page.title == RAW_TITLE, "the raw parse is kept"
    assert page.render is None
    assert page.render_error.startswith("render timed out after 0.5s")
    assert "#never-appears" in page.render_error
    assert page.render_ms > 0


def test_render_that_gets_an_http_error_keeps_the_raw_parse(
    site: str, httpserver: HTTPServer
) -> None:
    """The second (browser) request may be throttled; its error page must not become the page."""
    hits: list[int] = []

    def flaky(_request: Request) -> Response:
        hits.append(len(hits))
        if len(hits) == 1:
            return Response(
                "<html><head><title>Real title</title></head><body><h1>Real</h1></body></html>",
                content_type="text/html",
            )
        return Response(
            "<html><head><title>Service Unavailable</title></head></html>",
            status=503,
            content_type="text/html",
        )

    httpserver.expect_request("/audit/flaky").respond_with_handler(flaky)
    config = CrawlConfig(
        seed_urls=(f"{site}/audit/flaky",), follow_links=False, delay_seconds=0, render=True
    )
    (page,) = Crawler(config).run()
    assert len(hits) == 2, "one raw fetch, one browser load"
    assert page.status_code == 200
    assert page.title == "Real title"
    assert page.render is None
    assert page.render_error == "render returned HTTP 503"
    assert page.render_ms > 0


def test_transient_network_error_is_retried_once(
    site: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``net::ERR_*`` failure on the browser's first attempt must not become render.failed.

    The failure is provoked from inside the browser: the renderer's own request
    filter aborts the first document request, which Chromium reports as
    ``net::ERR_FAILED``, the same class of error as a reset socket.
    """
    aborted: list[str] = []
    original = Renderer.should_block

    def abort_first_document(self: Renderer, resource_type: str) -> bool:
        if resource_type == "document" and not aborted:
            aborted.append(resource_type)
            return True
        return original(self, resource_type)

    monkeypatch.setattr(Renderer, "should_block", abort_first_document)
    config = CrawlConfig(
        seed_urls=(f"{site}/js-injected",), follow_links=False, delay_seconds=0, render=True
    )
    (page,) = Crawler(config).run()
    assert aborted == ["document"], "the first attempt was aborted, the retry went through"
    assert page.render_error == ""
    assert page.render is not None
    assert page.title == RENDERED_TITLE


def test_cli_render_stores_the_diff_and_audit_reports_it(site: str, tmp_path: Path) -> None:
    db = tmp_path / "crawl.db"
    runner = CliRunner()
    crawl = runner.invoke(
        app, ["crawl", site, "--db", str(db), "--delay", "0", "--workers", "1", "--render"]
    )
    assert crawl.exit_code == 0, crawl.output
    with open_store(db) as store:
        page = next(r for r in store.iter_pages() if r.url.endswith("/js-injected"))
        assert page.title == RENDERED_TITLE
        assert page.render is not None
        assert page.render.describe() == "title, canonical, links +3"
        assert store.crawl().config_json.count('"render": true') == 1

    audit = runner.invoke(app, ["audit", str(db)])
    assert audit.exit_code == 0, audit.output
    flat = " ".join(audit.output.split())
    assert "render.differs" in flat
    assert "1 differ from their raw HTML" in flat
    assert "1 could not be rendered" in flat

    issues = runner.invoke(app, ["issues", str(db), "--rule", "render.differs"])
    assert issues.exit_code == 0, issues.output
    assert "".join(issues.output.split()).endswith("title,canonical,links+3")


def test_cli_render_wait_is_validated_before_any_request(site: str) -> None:
    result = CliRunner().invoke(app, ["crawl", site, "--render", "--render-wait", "soon"])
    assert result.exit_code == 2
    assert "render_wait must be one of" in " ".join(result.output.split())
