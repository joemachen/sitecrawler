# Roadmap

Phases are ordered so that every one ships something usable on its own and
each later phase builds on stored data from earlier ones. Each phase maps to a
GitHub milestone and ends with a tagged release.

A phase is **done** when every acceptance criterion is covered by a test
against `tests/fixtures/site/`, the user guide has a page for it, and
`CHANGELOG.md` has the entry.

| Phase | Name | Release | Status |
| --- | --- | --- | --- |
| 0 | Foundation | v0.1.0 | Done (live-site check parked) |
| 1 | Core crawl and storage | v0.2.0 | Done (2026-10-21) |
| 2 | Audit checks and issues engine | v0.3.0 | Done (2026-10-21) |
| 3 | Local web UI | v0.4.0 | Done (2026-10-21) |
| 4 | Live crawl UI | v0.5.0 | Done (2026-10-21) |
| 5 | JavaScript rendering | v0.6.0 | Done (2026-10-21) |
| 6 | Custom extraction and search | v0.7.0 | Done (2026-10-22) |
| 7 | XML sitemap audit and generation | v0.8.0 | Implemented (2026-10-22), release pending |
| 8 | Internal linking analysis | v0.9.0 | |
| 9 | Duplicate content detection | v0.10.0 | |
| 10 | Structured data validation | v1.0.0 | |
| 11 | API integrations | v1.x | |

---

## Phase 0: Foundation

**Goal:** a project that is safe to change. Tooling, tests, docs, CI, and the
original crawler ported into a package without behaviour changes.

Deliverables:

- `src/sitecrawler` package, `uv`, ruff, mypy strict, pytest, pre-commit, CI on Windows + Linux.
- `sitecrawler crawl URL -o out.csv` reproducing the original script's output.
- Fixture site covering redirects, loops, 404, robots blocking, sitemap-only page, off-site links.
- `docs/DEVELOPMENT.md`, `docs/ARCHITECTURE.md`, this roadmap, ADRs.

Acceptance:

- [x] All quality gates green locally and in CI (2026-10-21).
- [ ] A capped crawl of mabelslabels.com matches the original CSV row for row (blocked: site returning 503 after the first full crawl; retry with a longer delay).

---

## Phase 1: Core crawl and storage

**Goal:** the crawler records everything a later phase could need, and keeps
it in a database rather than a CSV.

Deliverables:

- `asyncio` + `httpx` fetcher with per-host rate limit and HTTP/2.
- SQLite store (`store/`): schema from ARCHITECTURE §3; `--db crawl.db`.
- Full redirect capture: every hop, status, and final URL. Chains and loops detectable from data.
- Response headers stored (`X-Robots-Tag`, `Content-Type`, `Last-Modified`, size).
- **List mode:** `sitecrawler list urls.txt` and `sitecrawler list -` (stdin). Crawls exactly the given URLs, no link following unless `--follow`.
- Exports: `sitecrawler export crawl.db --format csv|xlsx|json`. XLSX has one sheet per table.
- Resume: a crashed crawl can continue from its DB.

Acceptance:

- [x] Fixture redirect chain yields two `redirect_hops` rows; the loop yields a `redirect_loop` outcome after N hops, not a timeout (`tests/integration/test_store_crawl.py`, `tests/unit/test_fetcher.py`).
- [x] List mode on the fixture sitemap's URLs fetches exactly those and nothing else (`tests/integration/test_list_mode.py`).
- [x] `export --format xlsx` opens in Excel with pages, links, redirects sheets (`tests/e2e/test_export.py`; opened in Excel by hand still to do).
- [x] Killing a crawl and re-running with `--resume` finishes without re-fetching done pages (`tests/integration/test_store_crawl.py`).

---

## Phase 2: Audit checks and issues engine

**Goal:** the reason the tool exists. Every "must-have" on-page check, and a
ranked, explained fix list.

Checks (each is a `Rule` with fixture coverage):

- **Response codes:** 4xx, 5xx, blocked by robots, timeouts, off-site redirects.
- **Redirects:** chains (> 1 hop), loops, redirect to 4xx, HTTP→HTTPS missing, temporary (302/307) where permanent expected, internal links pointing at redirects.
- **Titles:** missing, duplicate, too long (> 60 chars / ~580 px), too short, multiple `<title>`, same as H1.
- **Meta descriptions:** missing, duplicate, too long (> 155), too short, multiple.
- **Headings:** missing H1, multiple H1, duplicate H1, missing H2s, H1 too long.
- **Canonicals:** missing, pointing to non-200, pointing off-site, canonical chain, canonicalised page that is linked internally, self-referencing check, canonical vs. `og:url` mismatch, conflicting canonicals (HTML vs header).
- **Robots directives:** `noindex` (meta or `X-Robots-Tag`), `nofollow`, `none`, conflicting directives, noindex page in sitemap, noindex page with internal links, blocked by robots.txt but linked.
- **Hreflang:** missing return links, invalid language codes, pointing to non-200 or non-canonical URLs, missing `x-default`, self-reference missing.
- **Pagination:** `rel=prev/next` pointing to non-200, paginated pages with canonical to page 1, sequence gaps.
- **Indexability verdict** per page: indexable / non-indexable with reason.

Deferred from this phase: `redirect.http_to_https_missing` needs an HTTPS fixture server (pytest-httpserver with a self-signed certificate and a `--insecure` crawl flag); it lands with the first phase that adds TLS to the test site.

Engine:

- `sitecrawler audit crawl.db` runs all rules, writes `issues` table, prints a table grouped by severity with counts and a one-line explanation.
- `sitecrawler issues crawl.db --rule title.missing` lists affected URLs.
- Rule docs auto-generated into `docs/user-guide/rules/`.

Acceptance:

- [x] 100% branch coverage on `audit/` (enforced by a CI step).
- [x] Every rule has a triggering and a non-triggering fixture page (`tests/integration/test_audit.py` maps each rule to the exact fixture paths it flags).
- [x] `audit` on a stored 10k-page crawl runs in under 10 s (3.5 s on a synthetic 10k-page, 300k-link crawl in SQLite: 0.9 s load, 1.4 s rules, 1.3 s storing issues; measured 2026-10-21 on the development machine).

---

## Phase 3: Local web UI

**Goal:** the "Issues tab" and friends in a browser, over a stored crawl.

- `sitecrawler serve crawl.db` opens `http://127.0.0.1:8765`.
- FastAPI + Jinja2 + HTMX; Tabulator for sortable, filterable, exportable grids.
- Tabs: **Overview** (counts, status breakdown, depth histogram), **Pages** (all columns, filter, search), **Issues** (grouped by rule, ranked by severity, click to see URLs and explanation), **Redirects**, **Page detail** (everything we know about one URL, including inlinks).
- Export any filtered grid to CSV.
- No login, binds to localhost only.

Acceptance:

- [x] Playwright e2e test opens each tab on the fixture crawl and asserts key numbers (`tests/e2e/test_web_ui.py`; every route is also covered through FastAPI's test client in `tests/integration/test_web.py` and `test_web_tabs.py`).
- [x] Any Issues-tab row links to the rule's explanation page (`/rules/<id>`, rendered in the app from the rule class; `tests/integration/test_web_tabs.py`).

Design notes: ADR-0006. The crawl is read once into memory and the file
closed; grids sort, filter and export client-side; htmx and Tabulator are
vendored. The UI reads `pages.indexable` from the export tables rather than
through `PageRecord`, which has no verdict field.

---

## Phase 4: Live crawl UI

**Goal:** the Screaming Frog experience in the browser: start a crawl, watch
the tabs fill, click through to any URL.

- `sitecrawler serve` with no file opens an empty session. A URL bar with
  Start, Pause, Resume, Stop and Clear, a progress bar, and new crawls
  written to `crawls/<host>-<timestamp>.db`. `serve crawl.db` still opens a
  stored crawl, read-only.
- Three panes: a tab strip (Internal, External, Response Codes, URL, Page
  Titles, Meta Description, H1, H2, Canonicals, Pagination, Directives,
  Hreflang, Links, Sitemaps, Issues) with a filter dropdown per tab over a
  grid; a right-hand Overview tree with a count per filter; a bottom detail
  pane for the selected URL (details, inlinks, outlinks, redirect chain,
  headers, hreflang, issues).
- Filters are the audit rules wherever one exists (Page Titles > Missing is
  `title.missing`) plus computed columns such as title length. The audit
  re-runs while pages arrive and is written to the file when the crawl ends.
- The crawler gains pause and stop (`CrawlControl`); `CrawlSession` runs it
  on a worker thread and the browser polls for new rows (ADR-0007).

Acceptance:

- [x] Starting a crawl of the fixture site from the UI ends with the page count and every rule-backed filter count equal to the audit test's numbers (`tests/integration/test_web_live.py`).
- [x] Stop mid-crawl leaves `crawls.status = stopped` and the UI shows the partial crawl (`test_web_live.py::test_stop_mid_crawl`, `tests/e2e/test_web_ui.py::test_stop_mid_crawl_from_the_ui`).
- [x] A Playwright test drives URL, Start, a tab and filter, a row, the detail sub-tabs and a sidebar count (`tests/e2e/test_web_ui.py::test_live_crawl_from_the_ui`).
- [x] `serve crawl.db` shows a stored, audited crawl with the same numbers as v0.4.0 (`tests/integration/test_web.py`, `test_web_tabs.py`).

Design notes: ADR-0007. Tabs and filters are data in `web/tabs.py`; a
filter backed by a rule is the rule, so the UI never disagrees with
`audit`. The browser polls; nothing is pushed.

---

## Phase 5: JavaScript rendering

**Goal:** see what Google sees on JS-heavy and app-injected pages.

- `--render` flag uses Playwright headless Chromium. Raw fetch still happens first.
- Parses both the raw HTML and the rendered DOM; the rendered fields become the page's, the raw values are kept in the diff. The two HTML bodies themselves are not stored (ADR-0008); revisit if Phase 6 wants the rendered DOM back.
- Diff report: links, titles, canonicals, metas that exist only after rendering (or only before). Rules `render.differs` and `render.failed`, a JavaScript tab and a Rendering detail section.
- Configurable wait strategy (`--render-wait load|domcontentloaded|networkidle`, `--render-selector`, `--render-timeout`) and resource blocking (images, fonts, media; blocking by host, for analytics, is not done).
- Render concurrency separate from fetch concurrency (`--render-workers`, default 2 tabs).

Acceptance:

- [x] Fixture page that injects its title, canonical and three links via JS is reported correctly only with `--render` (`tests/fixtures/site/js-injected.html`, `tests/integration/test_render.py`).
- [x] Rendered-vs-raw diff lists exactly those injected items (`test_render.py::test_diff_lists_exactly_the_injected_items`).

Design notes: ADR-0008. Playwright is the optional extra `sitecrawler[render]`;
`--render` without it fails before the first request with the install hint.

---

## Phase 6: Custom extraction and custom search

**Goal:** pull anything off any page, across a whole site.

- `--extract name=css:SELECTOR`, `--extract name=xpath:EXPR`, `--extract name=regex:PATTERN`, repeatable; also loadable from a TOML file.
- Modes per extractor: text, inner HTML, attribute, all matches vs. first.
- `--search "pattern"` (regex, case-insensitive) flags pages containing / not containing text or HTML (e.g. a GA4 tag ID).
- Results stored in `extractions`, shown as columns in Pages tab and exports.
- Works on rendered HTML when `--render` is on.

Acceptance:

- [x] Extracting price via CSS, SKU via XPath and GA tag via regex from fixture product pages yields expected values (`tests/fixtures/site/products/`, `tests/integration/test_extract.py::test_price_sku_and_ga_tag_come_off_the_product_pages`).
- [x] `--search` lists pages missing the GA tag (`test_extract.py::test_search_lists_the_pages_missing_the_ga_tag`; the CLI summary prints the contain / do-not-contain counts).

Design notes: ADR-0009. Extractors run inside the crawl over the HTML in hand
(the rendered DOM under `--render`); the bodies are still not stored, so
changing an extractor means crawling again. The grammar is
`NAME=KIND[MODIFIERS]:EXPRESSION` on the command line and the same keys in
TOML; columns are `extract_<name>` and `search_<name>`. The UI's **Custom** tab
builds its columns from the stored results, so a crawl file opened read-only
shows them without its configuration. lxml + cssselect replaced BeautifulSoup
here. Left for later: storing HTML bodies behind a flag for re-extraction, a
`--render` flag on `list`, and extractors in the UI as anything richer than
one spec per line.

---

## Phase 7: XML sitemap audit and generation

**Goal:** sitemaps that match reality.

- Parse every sitemap and sitemap index (gz supported); store all URLs with source.
- Reports: **orphans** (in sitemap, not reachable by links), **non-indexable in sitemap** (noindex, 3xx, 4xx, canonicalised elsewhere), **indexable missing from sitemap**, sitemap URLs on other hosts, duplicates across sitemaps.
- `sitecrawler sitemap generate crawl.db` writes a valid sitemap (or index when > 50k) of indexable 200 pages, with optional `lastmod` from headers.

Acceptance:

- [x] Fixture `orphan` page is reported as an orphan; `blocked/secret` is reported as non-indexable-in-sitemap; `blog/post-2` as missing-from-sitemap (`tests/integration/test_audit.py` `TRIGGERS` for `sitemap.orphan`, `sitemap.non_indexable`, `sitemap.missing`).
- [x] Generated sitemap validates against the sitemaps.org XSD (`tests/unit/test_sitemap_export.py` and `tests/integration/test_sitemaps.py::test_generate_writes_every_indexable_200_page_and_validates`, against the schemas vendored in `tests/fixtures/schemas/`).

Design notes: ADR-0010. The per-page findings are four audit rules in a
`Sitemaps` category (`sitemap.orphan`, `sitemap.non_indexable`,
`sitemap.missing`, `sitemap.duplicate`) that compare the sitemap entries,
normalised the crawl's way, with the pages and their indexability verdict.
File-level facts (files read or unreadable, entries on other hosts, entries
never crawled) are a `SitemapReport` in `analysis/sitemaps.py`, printed by
`sitecrawler sitemap report` and as one line under `audit`. Every file tried
is stored in a new `sitemaps` table; `sitemap_urls` gained `lastmod`,
`changefreq` and `priority`. `sitecrawler sitemap generate` is an export
(`export/sitemap.py`): indexable 200 pages, an index plus numbered parts over
50,000 URLs, `<lastmod>` from `Last-Modified` only with `--lastmod`, never
`changefreq` or `priority`. `/sitemap.xml` is now guessed only when
robots.txt names no sitemap. Fixture: `sitemap-index.xml` listing a gzipped
`sitemap-extra.xml.gz` (one page also in `sitemap.xml`, one entry on another
host) and a missing file; `audit/sitemap-twice.html`. Left for later: a
grid of sitemap entries in the web UI (the report is CLI-only), `<image:>` /
`<video:>` / `<xhtml:link>` extensions, and generating per-section sitemaps.

---

## Phase 8: Internal linking analysis

**Goal:** the quick wins.

- Inlinks and outlinks per page with anchor text, rel, position, nofollow.
- Crawl depth from the start URL (already) plus shortest-path depth.
- **Link Score:** PageRank over the internal follow graph, scaled 0-100.
- Reports: pages with few inlinks, high-depth pages, links to redirects/404s, generic anchors ("click here"), nofollow internal links, pages with excessive outlinks.
- Anchor text per target URL (what the site "calls" each page).

Acceptance:

- [ ] Link Score of the fixture home page is highest; the orphan's is lowest.
- [ ] Every internal link to a 404 or redirect in the fixture site appears in the report with its source and anchor.

---

## Phase 9: Duplicate and near-duplicate content

- Exact duplicates via content hash of main text (boilerplate stripped).
- Near-duplicates via SimHash with a configurable Hamming threshold; clusters reported with a representative URL.
- Low-content pages (word count below threshold).
- Cross-check against canonicals: duplicates without a shared canonical are the issue.

Acceptance:

- [ ] Two fixture pages differing by one sentence cluster together; unrelated pages do not.

---

## Phase 10: Structured data validation

- Extract JSON-LD, microdata and RDFa (`extruct`).
- Validate types and properties against the schema.org vocabulary (bundled JSON-LD, updated by a script).
- Google rich-result rules per type (Product, Article, BreadcrumbList, FAQPage, Organization, LocalBusiness, Recipe, Event, VideoObject, ...): required vs. recommended properties.
- Reports: invalid JSON, unknown types/properties, missing required fields, multiple conflicting entities.

Acceptance:

- [ ] Fixture product page with a missing `offers.price` is flagged; a complete one passes.

---

## Phase 11: API integrations (future)

Each integration is an `Enricher`: given URLs, return extra columns stored in
the crawl DB and shown next to crawl data.

- **Google Search Console:** clicks, impressions, CTR, position per URL; URL Inspection API for indexing status and last crawl.
- **GA4:** sessions, conversions per landing page.
- **PageSpeed Insights / CrUX:** Core Web Vitals, lab scores.
- **Ahrefs / Majestic / Moz:** backlinks and authority per URL.

OAuth and API keys via `.env`; all integrations are optional and off by default.

Acceptance:

- [ ] "Thin title with 40k impressions" is a single filter in the Issues tab.

---

## Ideas parked for later

Not scheduled; captured so they are not forgotten.

- Scheduled re-crawls and crawl-to-crawl diff ("what changed since last week").
- Core Web Vitals from the Playwright run itself.
- Image audit (alt text, size, lazy loading).
- Spelling and grammar.
- AMP, mobile usability.
- Log file analysis.
- Packaging as a single executable.
