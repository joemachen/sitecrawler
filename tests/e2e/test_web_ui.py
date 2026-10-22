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

import re
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, Locator, Page, expect, sync_playwright

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


def url_cell(page: Page, url: str) -> Locator:
    """The grid cell holding exactly ``url``."""
    return page.locator(
        '.tabulator-cell[tabulator-field="url"]', has_text=re.compile(f"^{re.escape(url)}$")
    )


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


def test_row_click_fills_the_detail_pane_and_links_to_the_full_page(
    page: Page, ui: str, site: str
) -> None:
    page.goto(f"{ui}/#internal/all")
    page.fill("[data-grid-search]", f"{site}/missing")
    url_cell(page, f"{site}/missing").click()
    pane = page.locator("[data-detail]")
    expect(pane).to_have_attribute("data-url", f"{site}/missing")
    expect(pane.locator("[data-detail-url]")).to_have_text(f"{site}/missing")
    expect(pane.locator("table.fields")).to_contain_text("404")

    pane.locator('[data-sub="issues"]').click()
    expect(pane.locator('table.issues tr[data-rule="response.4xx"]')).to_have_count(1)
    pane.locator('[data-sub="inlinks"]').click()
    expect(pane.locator(f'table.inlinks tr[data-src="{site}/"]')).to_have_count(1)

    pane.locator(f'table.inlinks a[data-url="{site}/"]').click()  # follow an inlink in the pane
    expect(pane).to_have_attribute("data-url", f"{site}/")

    pane.locator("[data-detail-open]").click()
    expect(page).to_have_url(f"{ui}/page?url={site.replace(':', '%3A').replace('/', '%2F')}%2F")
    expect(page.locator("h1.url")).to_have_text(f"{site}/")


@pytest.fixture
def idle_ui(tmp_path: Path) -> Iterator[str]:
    """Serve an empty session from a thread on a free loopback port."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(crawls_dir=tmp_path / "crawls")
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_live_crawl_from_the_ui(page: Page, idle_ui: str, site: str, summary: Summary) -> None:
    page.goto(idle_ui)
    app = page.locator(".app")
    expect(app).to_have_attribute("data-status", "idle")
    page.click("summary:has-text('Settings')")
    page.fill('input[name="delay_seconds"]', "0")
    page.fill('input[name="workers"]', "1")
    page.click("summary:has-text('Settings')")  # close the panel again
    page.fill("[data-url-input]", site)
    page.click('[data-action="start"]')

    expect(app).to_have_attribute("data-status", "running")
    expect(app).to_have_attribute("data-status", "done", timeout=60_000)
    counter = page.locator("[data-grid-count]")
    expect(counter).to_have_attribute("data-rows", str(len(site_pages())))
    expect(page.locator('[data-stat="pages"]')).to_have_text(str(len(site_pages())))

    page.click('[data-tree] a[data-tab="titles"][data-filter="missing"]')
    expect(counter).to_have_attribute("data-rows", str(summary.tabs["titles"]["missing"]))
    url_cell(page, f"{site}/notitle").click()
    pane = page.locator("[data-detail]")
    pane.locator('[data-sub="issues"]').click()
    expect(pane.locator('table.issues tr[data-rule="title.missing"]')).to_have_count(1)

    page.click('[data-tree] a[data-tab="response_codes"][data-filter="4xx"]')
    expect(counter).to_have_attribute("data-rows", "1")
    expect(url_cell(page, f"{site}/missing")).to_have_count(1)

    page.click('[data-tabstrip] [data-tab="issues"]')
    expect(page.locator('tr[data-rule="response.4xx"] [data-count]')).to_have_text("1")


def test_stop_mid_crawl_from_the_ui(page: Page, idle_ui: str, site: str) -> None:
    page.goto(idle_ui)
    page.click("summary:has-text('Settings')")
    page.fill('input[name="delay_seconds"]', "0.3")
    page.fill('input[name="workers"]', "1")
    page.click("summary:has-text('Settings')")  # close the panel again
    page.fill("[data-url-input]", site)
    page.click('[data-action="start"]')
    app = page.locator(".app")
    expect(app).to_have_attribute("data-status", "running")
    expect(page.locator("[data-grid-count]")).not_to_have_attribute(
        "data-rows", "0", timeout=30_000
    )

    page.click('[data-action="stop"]')
    expect(app).to_have_attribute("data-status", "stopped", timeout=30_000)
    rows = int(page.locator("[data-grid-count]").get_attribute("data-rows") or "0")
    assert 0 < rows < len(site_pages())
    expect(page.locator('[data-action="start"]')).to_be_enabled()
