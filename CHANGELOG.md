# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

Phase 6: custom extraction and custom search.

### Added

- `sitecrawler crawl --extract NAME=KIND:EXPRESSION` (and the same on
  `list`): custom extractors that run on every parsable HTML page, with
  `css`, `xpath` and `regex` kinds and the modifiers `text` (default),
  `html`, `attr=NAME`, `all` and `first` in brackets after the kind, e.g.
  `images=css[attr=src,all]:img`. `--extract-file extract.toml` loads any
  number of extractors and searches from one file. A bad selector,
  expression or pattern, or a name used twice, exits 2 before the first
  request.
- `--search [NAME=]PATTERN`: a case-insensitive regex every HTML page is
  checked for, giving a `True`/`False` column per page; the crawl summary
  prints how many pages contain it and how many do not.
- Results are stored in a new `extractions` table (`name`, `kind`, `count`,
  kept values) and read back as `PageRecord.extractions`. With `--render`
  they come from the rendered DOM (ADR-0009).
- Exports: one `extract_<name>` / `search_<name>` column per name after the
  fixed columns of the CSV and the `pages` table, plus an `extractions`
  table in XLSX and JSON.
- Web UI: a **Custom** tab (one column per extractor and search, found /
  not-found and contains / does-not-contain filters), a **Custom** detail
  section, **Extract** and **Search** boxes in Settings, and `/api/tabs`.
- Fixture product pages under `/products/` with a price, a SKU and (on two
  of three) a Google Analytics tag; `tests/integration/test_extract.py`.

### Changed

- The HTML parser is now lxml with cssselect instead of BeautifulSoup; the
  parsed fields are unchanged (`<br>` and nested tags still separate words,
  comments and `<noscript>` are not text).

## [0.6.0] - 2026-10-21

Phase 5: JavaScript rendering.

### Added

- `sitecrawler crawl --render` loads every parsable HTML page in headless
  Chromium (Playwright, async API) after the raw fetch and parses the
  rendered DOM: the page's title, metas, canonical, links and word count
  are then what a browser sees, and links that only exist after rendering
  are crawled. `--render-workers` (default 2 tabs), `--render-wait`
  (`load`, `domcontentloaded`, `networkidle`), `--render-selector` and
  `--render-timeout` tune it; images, fonts and media are never loaded.
  Playwright is the optional extra `sitecrawler[render]`; without it
  `--render` exits 2 with the install commands before any request.
- A rendered-vs-raw diff per page (`RenderDiff`, table `page_render`):
  title, meta description, meta robots, canonical, H1, word count and link
  count on both sides, plus the links present only after or only before
  rendering. A page the browser could not load keeps its raw fields and
  records the error.
- Rules `render.differs` (medium, names the changed fields) and
  `render.failed` (low); `audit` prints a one-line rendering summary.
- Web UI: **Render JavaScript** in Settings, a **JavaScript** tab (Rendered,
  Same as raw HTML, Changed by JavaScript, Render failed) and a
  **Rendering** detail section with raw and rendered values side by side.
- Exports: `render_status` and `render_changes` columns on `pages`; the
  CSV gains `render_changes` as its last column.
- Fixture page `/js-injected`, whose title, canonical and three links exist
  only after its script runs; `tests/integration/test_render.py` crawls it
  with and without `--render`. ADR-0008 records the design.

## [0.5.0] - 2026-10-21

Phase 4: live crawl UI.

### Added

- A detail pane under the grid: click a row for its URL Details, HTML,
  Inlinks, Outlinks, Redirects, HTTP Headers, Hreflang and Issues; links
  in the pane select that URL; **Open full page** keeps the `/page?url=`
  view. `/detail/<section>?url=` serves the fragments.

- A running crawl can be paused, resumed and stopped from another thread
  through `CrawlControl`; a stopped crawl marks its file `stopped` so the
  CLI can resume it.
- `CrawlSession` runs a crawl on a worker thread, keeps every page in
  memory, re-runs the audit while pages arrive and writes issues and
  verdicts to the file when the crawl ends. It also opens a finished file
  read-only. New crawls go to `crawls/<host>-<timestamp>.db` (ADR-0007).
- `Store.indexability()` reads stored verdicts back.
- The web UI is one page with a Screaming-Frog-style layout: a tab strip
  (Internal, External, Response Codes, URL, Page Titles, Meta Description,
  H1, H2, Canonicals, Pagination, Directives, Hreflang, Links, Sitemaps,
  Issues) with a filter dropdown per tab over one grid, an Overview tree
  with a count per filter, and `#tab/filter` in the address bar. Filters
  that correspond to an audit rule show exactly the URLs it flagged. New
  JSON endpoints: `/api/crawl`, `/api/rows`, `/api/summary`,
  `/api/external`. A file that was never audited is audited in memory when
  `serve` opens it.

- Crawl from the browser: `sitecrawler serve` with no file opens an empty
  UI with a URL bar, Start / Pause / Resume / Stop / Clear, a progress bar
  and a Settings panel with the `crawl` options. Rows, counts and the
  Issues tab update while the crawl runs; each crawl is written to
  `crawls/<host>-<timestamp>.db` (`--crawls-dir`) with its final audit.
  `POST /api/crawl/start|pause|resume|stop|clear`.

### Removed

- The Overview, Pages and Redirects pages and their `/api/pages` and
  `/api/redirects` endpoints; the same data is on the Internal and Response
  Codes tabs and in `/api/rows`.

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
