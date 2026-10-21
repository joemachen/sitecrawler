# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `sitecrawler audit crawl.db` runs every audit rule over a stored crawl,
  writes the `issues` table and an indexability verdict per page, and prints
  the fix list grouped by severity. `sitecrawler issues crawl.db --rule ID`
  lists the affected URLs.
- Rule framework under `audit/`: `Rule`, `PageRule`, `HtmlPageRule`,
  `CrawlView`; rules are discovered from `audit/rules/` and the rules
  reference page is generated from them.
- First rules: `response.4xx`, `response.5xx`, `response.error`,
  `response.blocked_by_robots`.
- The parser keeps the title and meta description counts, `og:url`, hreflang
  alternates and `rel=prev/next`; the crawler keeps a `Link` header canonical.
  Stored in `page_html` and the new `hreflang` table; exports gain `issues`
  and `hreflang` sheets and the `indexable` columns.

## [0.2.0] - 2026-10-21

Phase 1: core crawl and storage.

### Added

- `sitecrawler export crawl.db --format csv|xlsx|json`: csv is the pages table,
  xlsx has one sheet per table (pages, links, redirects, sitemap_urls), json
  holds the crawl summary and every table.
- `sitecrawler list urls.txt` and `sitecrawler list -` fetch exactly the
  given URLs (any hosts, robots.txt and `--delay` per host); `--follow` also
  follows links within the listed hosts.
- `crawl --db crawl.db` stores the crawl in SQLite as it runs (tables
  `crawls`, `pages`, `redirect_hops`, `page_html`, `links`, `sitemap_urls`),
  and `--resume` continues an interrupted crawl without re-fetching finished
  pages. With `--db`, `-o` writes the CSV from the store.
- The parser now keeps every H1 and H2, `<meta name="robots">`, `<html lang>`
  and each anchor's text and `rel`.
- Every redirect hop (from, to, status) is recorded on each page record, and
  response headers plus body size are kept.
- `redirect_loop` status: a chain that revisits a URL or exceeds
  `--max-redirects` (default 10) stops after at most that many requests
  instead of timing out.
- `--max-redirects` and `--no-http2` options on `crawl`.
- Project scaffold: uv, ruff, mypy strict, pytest, pre-commit, GitHub Actions CI.
- `sitecrawler crawl URL` command ported from the original single-file crawler:
  sitemap seeding, robots.txt, breadth-first link following, CSV export.
- Fixture site under `tests/fixtures/site/` and unit/integration/e2e tests.
- Planning docs: development process, architecture, roadmap, ADRs.

### Changed

- HTTP is now `httpx` on `asyncio` with HTTP/2 instead of `requests` in a
  thread pool. `--delay` applies per host rather than globally. Bodies with no
  declared charset are decoded as UTF-8. `Crawler.arun()` is available for
  callers that already run an event loop.

### Removed

- The `requests` dependency.
