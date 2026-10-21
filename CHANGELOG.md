# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Phase 4: live crawl UI (in progress).

### Added

- A running crawl can be paused, resumed and stopped from another thread
  through `CrawlControl`; a stopped crawl marks its file `stopped` so the
  CLI can resume it.
- `CrawlSession` runs a crawl on a worker thread, keeps every page in
  memory, re-runs the audit while pages arrive and writes issues and
  verdicts to the file when the crawl ends. It also opens a finished file
  read-only. New crawls go to `crawls/<host>-<timestamp>.db` (ADR-0007).
- `Store.indexability()` reads stored verdicts back.

## [0.4.0] - 2026-10-21

Phase 3: local web UI.

### Added

- `sitecrawler serve crawl.db` opens the local web UI on
  `http://127.0.0.1:8765`: Overview (status and depth breakdowns, issue
  totals, indexability), Pages and Redirects grids (sortable, filterable,
  the filtered rows download as CSV), an Issues tab grouped by rule with
  the flagged URLs a click away, a page per rule explaining why and how to
  fix, and a page detail with headers, parsed HTML, issues, inlinks and
  outlinks. `--port` and `--no-open`.
  The crawl is read once into memory; FastAPI, uvicorn and Jinja2 are new
  dependencies, htmx and Tabulator are vendored (ADR-0006).

## [0.3.0] - 2026-10-21

Phase 2: audit checks and issues engine, 51 rules.

### Added

- `sitecrawler audit crawl.db` runs every audit rule over a stored crawl,
  writes the `issues` table and an indexability verdict per page, and prints
  the fix list grouped by severity. `sitecrawler issues crawl.db --rule ID`
  lists the affected URLs.
- Rule framework under `audit/`: `Rule`, `PageRule`, `HtmlPageRule`,
  `CrawlView`; rules are discovered from `audit/rules/` and the rules
  reference page is generated from them.
- Rules: `response.4xx`, `response.5xx`, `response.error`,
  `response.blocked_by_robots`; `redirect.chain`, `redirect.loop`,
  `redirect.to_error`, `redirect.off_site`, `redirect.temporary`,
  `link.to_redirect`; `title.missing`, `title.duplicate`, `title.too_long`,
  `title.too_short`, `title.multiple`, `title.same_as_h1`;
  `meta_description.missing`, `.duplicate`, `.too_long`, `.too_short`,
  `.multiple`; `h1.missing`, `h1.multiple`, `h1.duplicate`, `h1.too_long`,
  `h2.missing`; `canonical.missing`, `.to_non_200`, `.off_site`, `.chain`,
  `.canonicalised_but_linked`, `.not_self_referencing`, `.og_url_mismatch`,
  `.conflict`; `robots.noindex`, `.nofollow`, `.none`, `.conflicting`,
  `.noindex_in_sitemap`, `.noindex_linked`, `.blocked_but_linked`;
  `page.non_indexable` (the verdict as a list); `hreflang.invalid_lang`,
  `.missing_self`, `.missing_x_default`, `.missing_return_link`, `.to_non_200`,
  `.to_non_canonical`; `pagination.to_non_200`, `.canonical_to_first`,
  `.broken_sequence`.
- The fetcher stops at the first redirect hop that leaves the crawl's hosts
  and reports the redirect instead of fetching the other site.
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
