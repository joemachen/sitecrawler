"""The web UI in a real browser, on the audited fixture crawl.

The numbers asserted here are the ones ``tests/integration/test_audit.py``
already pins down. Needs ``uv run playwright install chromium``; deselect
with ``-m "not browser"`` on a machine without it.

Playwright's sync API keeps an asyncio loop running on the main thread for
as long as it is open, which breaks every ``asyncio.run`` elsewhere in the
session. So the browser is opened per module here, not through the
pytest-playwright plugin's session fixtures.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, Page, expect, sync_playwright

from sitecrawler.session import CrawlSession
from sitecrawler.web import RowStore, Summary, create_app
from tests.conftest import site_pages

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    context = browser.new_context()
    yield context.new_page()
    context.close()


@pytest.fixture
def ui(audited_db: Path) -> Iterator[str]:
    """Serve the audited fixture crawl from a thread on a free loopback port."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(
        create_app(audited_db), host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def summary(audited_db: Path, tmp_path: Path) -> Summary:
    session = CrawlSession.open(audited_db, tmp_path / "crawls")
    try:
        return RowStore(session).summary()
    finally:
        session.close()


def test_sidebar_shows_the_crawl_numbers(page: Page, ui: str, summary: Summary) -> None:
    page.goto(ui)
    expect(page.locator('[data-stat="pages"]')).to_have_text(str(len(site_pages())))
    expect(page.locator('[data-stat="non_indexable"]')).to_have_text(str(summary.non_indexable))
    expect(page.locator('[data-stat="issues"]')).to_have_text(str(sum(summary.issues.values())))
    node = page.locator('[data-tree] a[data-tab="response_codes"][data-filter="4xx"] [data-count]')
    expect(node).to_have_text(str(summary.tabs["response_codes"]["4xx"]))


def test_internal_grid_lists_every_page_and_filters(page: Page, ui: str) -> None:
    page.goto(f"{ui}/#internal/all")
    counter = page.locator("[data-grid-count]")
    expect(counter).to_have_attribute("data-rows", str(len(site_pages())))
    page.fill("[data-grid-search]", "blocked/sitemap-only")
    expect(counter).to_have_attribute("data-rows", "1")
    page.fill("[data-grid-search]", "")
    expect(counter).to_have_attribute("data-rows", str(len(site_pages())))


def test_tab_and_filter_narrow_the_grid(page: Page, ui: str, summary: Summary) -> None:
    page.goto(ui)
    page.click('[data-tabstrip] [data-tab="titles"]')
    page.select_option("[data-filter]", "missing")
    counter = page.locator("[data-grid-count]")
    expect(counter).to_have_attribute("data-rows", str(summary.tabs["titles"]["missing"]))
    expect(page).to_have_url(f"{ui}/#titles/missing")
    page.click('[data-tree] a[data-tab="response_codes"][data-filter="3xx"]')
    expect(counter).to_have_attribute("data-rows", str(summary.tabs["response_codes"]["3xx"]))
    expect(page.locator('[data-tabstrip] [data-tab="response_codes"]')).to_have_attribute(
        "aria-selected", "true"
    )


def test_issues_row_loads_its_urls_and_links_to_the_rule(page: Page, ui: str, site: str) -> None:
    page.goto(f"{ui}/#issues/all")
    row = page.locator('tr[data-rule="response.4xx"]')
    expect(row.locator("[data-count]")).to_have_text("1")
    row.locator("td").last.click()
    urls = page.locator("#issue-urls tr[data-url]")
    expect(urls).to_have_count(1)
    expect(urls.first).to_have_attribute("data-url", f"{site}/missing")

    row.locator("a.rule-link").click()
    expect(page).to_have_url(f"{ui}/rules/response.4xx")
    expect(page.locator("h1")).to_contain_text("response.4xx")
    expect(page.locator("[data-count]")).to_have_attribute("data-count", "1")


def test_page_detail_reached_from_the_grid_shows_inlinks(page: Page, ui: str, site: str) -> None:
    page.goto(f"{ui}/#internal/all")
    page.fill("[data-grid-search]", f"{site}/missing")
    page.locator(".tabulator-cell a", has_text=f"{site}/missing").first.click()
    expect(page).to_have_url(
        f"{ui}/page?url={site.replace(':', '%3A').replace('/', '%2F')}%2Fmissing"
    )
    expect(page.locator("h1.url")).to_have_text(f"{site}/missing")
    expect(page.locator(f'table.inlinks tr[data-src="{site}/"]')).to_have_count(1)
    expect(page.locator('table.issues tr[data-rule="response.4xx"]')).to_have_count(1)
