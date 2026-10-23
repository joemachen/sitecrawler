# Handoff: sitecrawler

Read this first in a new session. It is the state of the project as of
2026-10-23 (v1.0.0 released: every core phase is done; Phase 11, API
integrations, not started) and everything that is not obvious from the code.

## What this is

sitecrawler is an SEO site-audit crawler in Python, growing from a single-file
script into a Screaming-Frog-style tool: crawl a site, store every page, report
ranked issues with explanations. Owner: Joe Machen (GitHub `joemachen`), solo
developer, new to formal software process. Joe wants recommended defaults with a
one-line reason, not menus of options.

- Local checkout: `D:\Projects\scraper`
- Remote: `https://github.com/joemachen/sitecrawler` (private), branch `main`
- Package: `src/sitecrawler/`, Python 3.13, managed with `uv`

## Where things stand

Phases 0, 1 and 2 are complete and on `main`, released as v0.3.0. Phase 2
landed as four squash-merged PRs (#10 framework, #11 content rules, #12
canonical/robots rules, #13 hreflang/pagination rules) plus a release PR.

**Phase 3 (local web UI) is complete and released as v0.4.0** (tag on
`main`, 2026-10-21). It landed as three stacked PRs, squash-merged in order:
#15 (`web/` package, `serve`, Overview + Pages, ADR-0006), #16 (Issues +
HTMX URL panel, `/rules/<id>`, Redirects, Page detail, 404), #17 (Playwright
e2e per tab, CI Chromium step, roadmap close-out), then #18 the release.
Stacking worked: after each squash merge,
`git rebase --onto origin/main <old-base-tip> <branch>`,
`git push --force-with-lease`, `gh pr edit N --base main`. A rebase that
changes no content (`git diff --stat <old-tip> <branch>` empty) does not
need a fresh CI run; the earlier green run tested the same tree.

**Phase 4 (live crawl UI) is complete and released as v0.5.0** (annotated
tag on `main` at 0faa950, 2026-10-21). It landed as five stacked PRs,
squash-merged in order: #21 `feat/crawl-control` (CrawlControl +
CrawlSession + ADR-0007 + roadmap renumber), #26 `feat/web-shell`
(tabs.py, rows.py, the one-page shell; it replaced #22, see the gotcha
below), #23 `feat/web-live` (start/pause/stop, polling, `serve` with no
file), #24 `feat/web-detail` (detail pane, e2e, docs) and #25
`chore/release-v0.5.0`. The train took the same recipe as Phase 3: after
each squash merge, `git rebase --onto origin/main <old-base-tip> <branch>`
for the next branch (and each later branch onto its new base),
`git push --force-with-lease`, `gh pr edit N --base main`. Every rebase
produced a byte-identical tree, so no merge waited for a fresh CI run.
The roadmap calls the live UI Phase 4 and JS rendering Phase 5 (later
phases shifted by one).

**Phase 5 (JavaScript rendering) is complete and released as v0.6.0**
(annotated tag on `main`, 2026-10-21). It was small enough for one PR
rather than a stack: #28 `feat/render` (squash-merged as 642cd91), then
#29 `chore/release-v0.6.0`. Before the merge a `/code-review` pass on #28
found six renderer bugs (an HTTP error page on the browser's request
becoming the page, a JavaScript redirect off-site parsed as the page, a
crashed browser turning pages into ERROR records, `--render-timeout 0`
meaning "wait forever", a Chromium leak when context setup failed, and a
summary/rule count mismatch for redirect sources); all were fixed on the
same PR, with a fixture page per new failure mode. ADR-0008 records the
design: every parsable HTML page is rendered (no "looks JS-dependent"
heuristic), the rendered fields become the page record and rendered-only
links feed the frontier, the raw values are kept in a `RenderDiff` stored
in `page_render`, and the two HTML bodies are not stored.

**Phase 6 (custom extraction and custom search) is complete and released
as v0.7.0** (annotated tag on `main`, 2026-10-22). One PR, `feat/extract`
(#31, squash-merged as 6e69cb5), then `chore/release-v0.7.0` (#32) and
`docs/handoff-v0.7.0` (#33). A `/code-review` pass on #31 found an XPath
expression that compiles but fails at evaluation (an XPath 2.0 function)
would have turned every page into an ERROR record; every XPath is now
probed against a tiny document at compile time and a page-specific failure
counts as no match. ADR-0009 records the design call: extractors run inside `Crawler._fetch_and_parse` over the text the
page was parsed from (the rendered DOM under `--render`), the HTML bodies
are still not stored, and lxml + cssselect replaced BeautifulSoup (every
existing parser test stayed green; `tests/unit/test_html.py` gained edge
cases for `<br>`, comments, empty documents and XHTML prologues).

**Phase 7 (XML sitemap audit and generation) is complete and released as
v0.8.0** (annotated tag on `main` at f5a7c53, 2026-10-22). One PR,
`feat/sitemaps` (#34, squash-merged as 573408b), then
`chore/release-v0.8.0` (#35) and `docs/handoff-v0.8.0` (#36). A `/code-review`
pass on #34 found and fixed: relative `<loc>` values not resolved against
the sitemap URL, a URL listed twice in one file differing between the live
session and the store, unbounded gzip inflation, the page selection living
in `cli/`, the default base URL taken from `pages[0]`, and an uncaught
`OSError` on `-o`. ADR-0010 records the design calls: the per-page
findings are four audit rules in a `Sitemaps` category that compare the
sitemap entries, normalised the crawl's way, with the pages and their
indexability verdict; facts about the sitemap *files* (unreadable files,
entries on other hosts, entries never crawled) are a `SitemapReport` in
`analysis/sitemaps.py` rather than issues, because an issue row needs a
crawled page to hang on; generation is an export (`export/sitemap.py`) with
`<lastmod>` only on request and never `changefreq`/`priority`. One
behaviour change: `/sitemap.xml` is guessed only when robots.txt names no
sitemap, so a site that declares its sitemaps no longer logs a spurious 404.

**Phase 8 (internal linking analysis) is complete and released as
v0.9.0** (annotated tag on `main` at cd85c5d, 2026-10-22). One PR,
`feat/links` (#38, squash-merged as 0cdc95d), then `chore/release-v0.9.0`
(#39) and `docs/handoff-v0.9.0` (#40). A `/code-review` pass on #38 found
and fixed:
`link.few_inlinks` firing on every page of a list-mode crawl (it is now
silent when the crawl has no start page), `links report --top 0` printing
every row, an unused `LinkGraph.metrics_for`, and a PageRank tolerance
(1e-9) that 100 damped rounds could never reach (now 1e-6). ADR-0011
records the design calls: the link graph is part of the audit index
(`audit/graph.py`, reached as `CrawlView.link_graph`) because the rules
read it and `audit` may not import `analysis`; nodes are every crawled
page, follow edges are links between crawled pages minus `rel=nofollow`,
page-wide `nofollow`/`none` and self-links, resolved through redirects to
the landing page; PageRank (d=0.85, dangling rank spread evenly) is
log-scaled 0-100; click depth is a BFS from the `found_on == "start"` page
over every internal link (nofollow included); `audit` writes `inlinks`,
`link_depth` and `link_score` onto `pages`; every anchor records its
`position`. The fixture needed `Home` links on its hub, blog and product
pages before the home page outranked the products cluster (with `/` linked
from `/about` alone, PageRank put `/products` at 100 and `/` at 20).

**Phase 9 (duplicate and near-duplicate content) is complete and released
as v0.10.0** (annotated tag on `main` at ff24999, 2026-10-22). One PR,
`feat/duplicates` (#41, squash-merged as c094428), then
`chore/release-v0.10.0` (#42) and `docs/handoff-v0.10.0` (#43). A
`/code-review` pass on #41 found and fixed: `main_text` dropped the text
that follows a role-marked
boilerplate element (lxml's `remove()` discards the tail, unlike
`strip_elements(with_tail=False)`; `_remove_keeping_tail` moves it to the
previous sibling or the parent), `duplicates report --max-distance N`
built the default index as well as its own, and the report re-implemented
the rule's low-content predicate and the hash lookup (now
`content.is_low_content()` and `Cluster.texts`). Left as is: the parser
deep-copies the body per page and the SimHash inner loop is 64 Python
iterations per shingle (both invisible behind the politeness delay).
ADR-0012 records the design calls: the fingerprint
(`content_hash`, `simhash`, `content_words`) is computed by `parse_html`
in the crawl pass over the *main text* (`<main>`, `role=main` or the body
minus `header`/`nav`/`footer`/`aside`, their ARIA roles, scripts and
styles) and stored on `page_html`, because the bodies are still not
stored (ADR-0009); the duplicate index lives in `audit/duplicates.py` as
`CrawlView.duplicates` for the reason the link graph does (the rules read
it and `audit` may not import `analysis`); the three `content.*` rules
flag indexable members only, so the canonical cross-check is the
indexability verdict. Two numbers were measured, not guessed: the
roadmap's acceptance pair (`audit/dup-near-1`/`-2`, one sentence changed
in 260 words) is 9 of 64 SimHash bits apart, so the threshold is 10 (not
the textbook 3, which only catches a word or two); and the one-sentence
fixture pages landed within 5 to 9 bits of each other, so near-duplicate
clustering only runs over pages of `MIN_WORDS` (200) or more, the
low-content floor. SimHash distance depends on the share of three-word
runs changed, not on length (`64 * acos(1 - f) / pi`). Adding `Home`
links to the new fixture pages changed the Phase 8 inlink counts, so they
link only to `/audit/`; the fifth new fixture, `dup-exact-canonical`,
joined `CANONICALISED` and `NON_INDEXABLE` in `test_audit.py`.

**Phase 10 (structured data validation) is complete and released as
v1.0.0** (annotated tag on `main` at ef07c7b, 2026-10-23). One PR,
`feat/structured-data` (#45), then `chore/release-v1.0.0` (#46) and
`docs/handoff-v1.0.0` (#47). The roadmap named extruct; ADR-0013
records why it is not used (last release 2024-11, no Python 3.13
classifier, seven dependencies including rdflib, drops broken JSON-LD
silently, parses the page again): `parse/structured.py` reads the three
syntaxes from the tree `parse_html` already has. Google retired FAQ rich
results on 2026-05-07, so FAQPage is not in the rich-result table. A
`/code-review` pass on #45 found and fixed: crawl files from before the
new table opened as crawls with no structured data (`open_store`'s
`create_all` adds missing tables silently; `missing_tables()` and
`require_crawl_db` now refuse them), microdata `itemprop` items outside any
item were dropped, the schema.org context document URL read as a foreign
vocabulary, `vocab=""` produced `/Name` types, conflicts compared unsquashed
JSON-LD whitespace and skipped `url` instead of resolving it, and the
CLI's `_view` helper existed in four copies (now `cli/_run.py::load_view`,
used by `duplicates`, `links` and `schema`; `sitemap_cmd` keeps its own,
which returns a tuple). A 40-page crawl of mabelslabels.com found
`query-input` on the sitelinks `SearchAction` flagged as unknown: schema.org
Actions allow `<property>-input` / `-output`, now understood. Joe decided
1.0 makes **no crawl-file compatibility promise**: no migrations; an older
file is refused with a re-crawl message.

What exists now:

- **Structured data.** `parse/structured.py::extract_structured(doc,
  base_url)` runs in `parse_html` before the scripts are stripped and
  returns `StructuredData(items, errors)`: each `StructuredItem(format,
  data, line)` has `format` `json-ld` / `microdata` / `rdfa` and `data` a
  `StructuredNode` (every key to a list of `str` or nested nodes; `@type`
  and `@id` kept; schema.org names bare, other vocabularies as full IRIs,
  `is_bare()` tells them apart); a `StructuredError(message, line)` per
  JSON-LD block that fails `json.loads`. `ParsedPage.structured` /
  `PageRecord.structured` (None unless parsed). Store: `structured_data`
  table (`StructuredRow`: `format`, `types` space-separated, `data_json`,
  `error`, `line`); `structured_from_rows()` uses the fingerprint to tell
  "parsed, nothing found" from "not parsed"; `missing_tables(path)` lists
  tables an older file lacks. Exports: `structured_data` sheet (last in
  `EXPORT_TABLES`), `structured_types` last in `PAGE_COLUMNS`. Vocabulary:
  `src/sitecrawler/data/schemaorg.json` (types to parents, properties to
  domains, ~100 kB), refreshed by `scripts/update_schemaorg.py`.
  `audit/structured.py`: `Vocabulary.bundled()` (`is_type`, `ancestors`
  BFS, `allows` with inheritance), `rich_result_for()`, `check_page()`,
  `StructuredIndex` (`CrawlView.structured`, `findings_for(url, kind)`),
  `Finding(kind, message, type, path)`, `KINDS`. `audit/richresults.py`:
  `RICH_RESULTS` (Product, Article, BreadcrumbList, Organization,
  LocalBusiness, Recipe, Event, VideoObject) of `Need(paths, when)`; a
  dotted path must hold on every node it reaches. Rules in
  `audit/rules/structured.py` (category `Structured data`, one issue per
  page, findings joined with `; `): `schema.invalid_json` (high),
  `schema.missing_required` (high), `schema.unknown_type` (medium),
  `schema.conflicting` (medium: same type and same `@id` or resolved `url`,
  different text), `schema.unknown_property` (low),
  `schema.missing_recommended` (low). `analysis/structured.py`:
  `structured_report()` (`StructuredReport`: `pages`, `with_items`,
  `formats`, `types` as `TypeCount`, `findings`, `summary()`). CLI:
  `sitecrawler schema report crawl.db [--kind KIND]` (Rich types table to
  stderr, `<kind>\t<url>\t<type>\t<path>\t<message>` to stdout); `audit`
  prints one `Structured data:` line. Web: a **Structured Data** tab
  (`structured_types`, `structured_items`, `structured_formats`,
  `schema_problems`) with a filter per rule plus `has_structured` /
  `no_structured`; `PageDetail.schema_findings` and
  `templates/detail/structured.html` (a `structured` entry in
  `DETAIL_SUBS`; items shown with the `pretty_json` Jinja filter in
  `web/app.py`). Fixture: `audit/schema-product` (complete, trips
  nothing), `schema-no-price`, `schema-invalid-json`, `schema-unknown`
  (microdata), `schema-article` (RDFa Lite), `schema-conflict`, under a
  *Structured data* heading on the hub; `tests/integration/test_structured.py`
  holds the roadmap acceptance test. User guide:
  `docs/user-guide/structured-data.md`.

- **Content.** `CrawlView.duplicates` is a `DuplicateIndex`
  (`audit/duplicates.py`): `pages` (parsed HTML pages with a non-empty
  fingerprint), `exact` (tuple of `Cluster(representative, members)` by
  content hash, any length) and `near` (clusters of pages with 200+ words
  within `NEAR_DUPLICATE_DISTANCE` = 10 bits, single linkage, candidate
  pairs by pigeonhole blocking over distinct SimHash values), with
  `exact_group(url)`, `near_cluster(url)`, `distance(a, b)` and
  `same_text(a, b)`; the representative is the best-linked member
  (highest Link Score, then first URL). `parse/fingerprint.py` holds
  `main_text()`, `fingerprint()`, `fingerprint_text()`, `simhash()` and
  `hamming()`; `parse_html` sets `ParsedPage.fingerprint` and the crawler
  copies it to `PageRecord.fingerprint` (`Fingerprint(content_hash,
  simhash, words)`, `.empty`, `.simhash_hex`; None on unparsed pages).
  Store: `page_html.content_hash`, `.simhash` (16 hex digits),
  `.content_words` (NULL when not parsed); `store.fingerprint_from_row()`;
  the `pages` dump ends with the three. Rules in `audit/rules/content.py`
  (category `Content`): `content.duplicate` (high), `content.near_duplicate`
  (medium: names the closest partner and the bit distance),
  `content.low_word_count` (low: indexable HTML pages under `MIN_WORDS`).
  `analysis/duplicates.py`: `duplicate_report(crawl, max_distance=None)`
  (`DuplicateReport`: `pages`, `compared`, `exact`, `near` (clusters with
  more than one distinct text), `low_content`, `summary()`) and
  `member_status()`. CLI: `sitecrawler duplicates report crawl.db
  [--max-distance N]` (one `<exact|near>`, representative, member, bits,
  indexability line per member, tab-separated); `audit` prints one
  `Duplicates:` line. Web: a **Content** tab (`content_words`,
  `word_count`, `exact_duplicates`, `near_duplicates`, `duplicate_of`,
  `content_hash`) with a filter per rule plus `no_text`;
  `AuditIndex.cells` and `NO_AUDIT` carry the three new cells;
  `PageDetail.duplicates` feeds `detail/content.html` (a new `content`
  entry in `DETAIL_SUBS`; `.detail-head` and `.subtabs` now wrap, because
  the eleventh sub-tab pushed *Open full page* under the sidebar). Fixture:
  `audit/dup-exact-1`, `dup-exact-2`, `dup-exact-canonical`,
  `dup-near-1`, `dup-near-2` (linked from the hub under *Content*);
  `TRIGGERS["content.low_word_count"]` is computed (every indexable page
  bar `DUPLICATE_CONTENT` and `many-outlinks`), and `h1-dup-1`/`-2`, which
  differ only in `<head>`, are exact duplicates too;
  `tests/integration/test_duplicates.py` holds the roadmap acceptance
  test, the CLI, the stored columns and the web cells. User guide:
  `docs/user-guide/duplicates.md`.

- **Links.** `CrawlView.link_graph` is a `LinkGraph` (`audit/graph.py`)
  with `metrics: dict[url, LinkMetrics(inlinks, follow_inlinks,
  link_depth, link_score)]`, `follow_sources(url)`, `landing(page)`,
  `highest()` / `lowest()`; `is_broken(target)` and
  `redirects_elsewhere(crawl, target)` are the shared target classifiers.
  `CrawlView.start_page` is the page with `found_on == "start"` (None in
  list mode, so no click depth there). `robots_directives` moved to
  `audit/directives.py` (with `page_nofollow`); `audit.engine` re-exports
  it. `AuditResult.links` carries the metrics; `Store.set_link_metrics()`
  writes them (`audit` and the session's final write both call it);
  `LinkRow.position` / `LinkRef.position` is the nearest
  `header`/`nav`/`footer`/`aside` ancestor or ARIA role, else `body`
  (`parse/html.py::link_position`). Rules in `audit/rules/links.py`
  (category `Links`): `link.to_error` (medium), `link.few_inlinks` (low:
  indexable, not the start page, at most `FEW_INLINKS` = 1 follow inlink;
  silent in list mode), `link.high_depth` (low: click depth over
  `MAX_DEPTH` = 3), `link.generic_anchor` (low: `GENERIC_ANCHORS`, compared
  without case or punctuation), `link.nofollow_internal` (low),
  `link.too_many_outlinks` (low: over `MAX_OUTLINKS` = 300 anchors);
  `link.to_redirect` stays in `redirects.py`. `analysis/links.py`:
  `link_report()` (`LinkReport`: broken and redirecting `ProblemLink`s with
  source, anchor and position, score extremes, unreachable count,
  `summary()`) and `anchor_texts()`. CLI: `sitecrawler links report
  crawl.db [--top 10]` (Rich table of the score extremes to stderr, then
  `error\t<src>\t<href>\t<status>\t<anchor>` and
  `redirect\t<src>\t<href>\t<final>\t<anchor>` lines to stdout) and
  `sitecrawler links anchors crawl.db [URL]`
  (`<target>\t<count>\t<text>`); `audit` prints one `Links:` line. Web:
  the Links tab shows `link_score`, `unique_inlinks`, `follow_inlinks`,
  `link_depth` with a filter per rule plus `unreachable`; Internal gained
  `link_depth` / `link_score`; `AuditIndex.cells` and `NO_AUDIT` carry the
  five new cells; `PageDetail.links` / `.anchors` feed `detail/inlinks.html`
  (metrics, anchor texts, position column) and `detail/outlinks.html`.
  Exports: `pages` ends with `inlinks`, `link_depth`, `link_score`; `links`
  ends with `position`. Fixture: `audit/link-deep-1..3` (a chain four
  clicks deep), `audit/generic-anchor`, `audit/nofollow-link`,
  `audit/many-outlinks` (301 self-fragment anchors), `Home` links on the
  hub (`<footer>`), blog index/posts and product pages (`<nav>` on the
  products index). `TRIGGERS["link.few_inlinks"]` is computed from the
  fixture HTML by `tests/conftest.py::follow_inlink_sources()`;
  `tests/integration/test_links.py` holds both roadmap acceptance tests
  (home 100, `/orphan` 0; every link to an error or redirect reported with
  source and anchor, derived from the fixture files), the CLI, the stored
  columns and the web cells. User guide: `docs/user-guide/links.md`.

- **Sitemaps.** `parse/sitemap.py` returns `SitemapDoc(kind, entries)`
  where each `SitemapEntry(sitemap_url, loc, lastmod, changefreq,
  priority)` knows its file; it gunzips on the gzip magic bytes and matches
  elements by local name (a missing or odd namespace still parses).
  `Crawler._seed_from_sitemaps` records every file it tries as a
  `SitemapFile(url, found_in, kind, status_code, error, url_count)`
  (`found_in` is `robots.txt`, `default` or the index URL), follows indexes
  to any depth, and hands `CrawlSink.seeded(items, sitemap_files,
  sitemap_entries)` everything (the old `(sitemap_url, loc)` pairs are
  gone; `_SessionSink`, `Store` and the test fakes all take the new
  signature). Store: new `sitemaps` table (`SitemapRow`), `lastmod` /
  `changefreq` / `priority` columns on `sitemap_urls`,
  `Store.sitemap_files()` / `.sitemap_entries()` (`.sitemap_urls()` still
  exists); both tables are export sheets (`sitemaps` before
  `sitemap_urls` in `EXPORT_TABLES`). `CrawlView` gained `sitemap_entries`,
  `sitemap_files`, `sitemap_listings` (normalised URL to its entries) and
  `sitemap_listings_for(url)`; `sitemap_urls` is derived from the entries
  and `from_records(sitemap_urls=...)` still works for membership-only
  tests. Rules in `audit/rules/sitemaps.py`: `sitemap.orphan` (medium:
  indexable, listed, no inlink from another page; self-links do not count
  and `found_on == "start"` is never an orphan), `sitemap.non_indexable`
  (medium: listed and verdict not indexable, message is the reason),
  `sitemap.missing` (low: indexable 200 page not listed, silent when
  `crawl.sitemap_entries` is empty), `sitemap.duplicate` (low: more than
  one listing, across files or two spellings). `robots.noindex_in_sitemap`
  stays. CLI: `sitecrawler sitemap report crawl.db` (files table + one
  tab-separated line per other-host / not-crawled / duplicate entry) and
  `sitecrawler sitemap generate crawl.db [-o sitemap.xml] [--lastmod]
  [--base-url URL]` (indexable 200 pages via `audit.indexability()`, so no
  audit run needed; `write_sitemap()` splits into `<stem>-N.xml` parts plus
  an index over `SITEMAP_MAX_URLS` = 50,000, which needs `base_url`);
  `audit` prints the report's one-line summary when the crawl tried any
  sitemap. Web: the Sitemaps tab's filters are rule filters plus
  `in_sitemap` / `not_in_sitemap` and the tab shows `inlinks`; the computed
  `non_indexable_in_sitemap` cell is gone; `PageDetail.sitemaps` lists the
  entries naming the page and `detail/details.html` shows them. Fixture:
  robots.txt names `/sitemap.xml` and `/sitemap-index.xml`; the index
  lists `/sitemap-extra.xml.gz` (served gzip-compressed by the conftest
  from `sitemap-extra.xml` via the `gzip` list in `routes.json`; it lists
  `/audit/sitemap-twice` with lastmod/changefreq/priority and
  `https://elsewhere.test/page`) and `/sitemap-missing.xml` (404);
  `audit/sitemap-twice.html` is linked from the audit hub and in
  `sitemap.xml` too. The sitemaps.org XSDs are vendored under
  `tests/fixtures/schemas/` and `tests/unit/test_sitemap_export.py` /
  `tests/integration/test_sitemaps.py` validate generated files against
  them. `TRIGGERS["sitemap.missing"]` is computed:
  `site_pages() - NON_INDEXABLE - IN_SITEMAP`. User guide:
  `docs/user-guide/sitemaps.md`.

- `sitecrawler crawl URL --extract NAME=KIND[MODS]:EXPR ... --search
  [NAME=]PATTERN ... --extract-file extract.toml` (and the same three
  options on `list`). Kinds `css`, `xpath`, `regex`; modifiers `text`,
  `html`, `attr=NAME`, `all`, `first` in brackets after the kind
  (`images=css[attr=src,all]:img`). Searches are case-insensitive regexes
  over the HTML source; unnamed ones are `search`, `search2`, ... Grammar,
  TOML loader (`[extract.NAME]` tables with `css`/`xpath`/`regex`, `mode`,
  `attr`, `all`; `[search]`; or a plain string in the CLI form) and the
  runner live in `parse/extract.py`; `compile_extractors()` returns an
  `ExtractorSet` the crawler builds in `__init__`, so a bad selector,
  expression or pattern, or a name used twice, fails before the first
  request (exit 2 from the CLI, 400 from the web UI). `CrawlConfig.extract`
  / `.search` hold `ExtractorSpec` / `SearchSpec` tuples;
  `session._config_from_json` rebuilds them from `config_json`.
  Results: `PageRecord.extractions`, a tuple of `Extraction(name, kind,
  values, count)` in config order, one per extractor and search on every
  parsable HTML page (redirect sources included, since they carry the
  target's content), none on non-HTML pages. Values are the first match or,
  with `all`, every match; `count` is always the total. Empty text, empty
  attributes and comment nodes are not matches. Stored in the
  `extractions` table (`ExtractionRow`: `name`, `kind`, `count`,
  `values_json`); `Store.extraction_names()` / `.extraction_columns()`
  give the names in first-seen order. Columns are `extract_<name>` and
  `search_<name>` (a search cell is True/False, None on non-HTML pages) so
  they can never shadow a built-in column: appended to the CSV
  (`write_csv(..., extra_columns=)`), to the `pages` dump, and a new
  `extractions` export table (`url, name, kind, count, value`) is last in
  `EXPORT_TABLES`. The crawl summary prints one line per search with the
  contain / do-not-contain counts.
  Web: a **Custom** tab whose columns and filter pairs (`has:<name>`,
  `not:<name>`) are built by `web/tabs.py::custom_tab()` from the names
  `RowStore` has seen (`RowStore.tabs()`, `with_custom()`); `TabSpec.titles`
  gives the grid header the bare extractor name; `/api/tabs` serves the
  specs and `app.js` re-reads them on every refresh so a live crawl's
  columns appear as its first page lands. `StartRequest.extract` /
  `.search` take lists of CLI-form strings (Settings has **Extract** and
  **Search** textareas, one per line); a **Custom** detail section
  (`templates/detail/custom.html`). Fixture: `tests/fixtures/site/products/`
  (hub linked from the home page, three products with `.price`, `data-sku`
  and, on widget and gadget only, a GA tag `G-7F3K9Q2M1X` loaded from a
  local `/gtag.js` so Chromium never leaves the fixture server);
  `tests/integration/test_extract.py` covers the library, the CLI (flags,
  TOML file, list mode, errors), exports, the web tab and, under the
  `browser` marker, extraction from the rendered DOM. User guide:
  `docs/user-guide/extract.md`.

- `sitecrawler crawl URL --render [--render-workers 2] [--render-wait
  networkidle|load|domcontentloaded] [--render-selector CSS]
  [--render-timeout 30]`: after the raw httpx fetch, every parsable HTML
  page is loaded in one headless Chromium (`crawl/renderer.py`, Playwright
  async API, `render_workers` tabs through a semaphore, images/fonts/media
  blocked, the fetcher's per-host throttle shared). `Crawler._render` hands
  the DOM to `parse_html` and `diff_rendered` (`parse/render_diff.py`).
  A failed render keeps the raw parse and sets `record.render_error`; an
  HTTP status of 400 or above on the browser's request, a download, a lost
  browser and a JavaScript redirect off-site all count as failures; a
  `net::ERR_*` navigation error (transient socket trouble, seen as
  `ERR_NO_BUFFER_SPACE` on the Windows CI runner) is retried once first.
  Redirect sources are not rendered (their fields are the target's, and
  the target is rendered when it is crawled). Fixture for `render.failed`:
  `/audit/render-download`, served with `Content-Disposition: attachment`
  from `routes.json`.
  Rules `render.differs` (medium) and `render.failed` (low) in
  `audit/rules/render.py`; `audit` prints a one-line rendering summary.
  Web: `StartRequest.render`, a **Render JavaScript** checkbox in Settings,
  a **JavaScript** tab in `web/tabs.py`, a **Rendering** detail section
  (`templates/detail/render.html`). Exports: `render_status`,
  `render_changes` on `pages`; the CSV gained `render_changes` last.
  Playwright is the optional extra `sitecrawler[render]` (`uv lock` was
  re-run); `--render` without it, or without Chromium, raises
  `RenderUnavailableError` (a `ValueError`) before the first request.
  Fixture: `tests/fixtures/site/js-injected.html`, linked from the index;
  `tests/integration/test_render.py` and `test_web_render.py` (marker
  `browser`) crawl it with and without `--render`. `list` mode has no
  `--render` flag yet (the config supports it; only the CLI option is
  missing).

- `sitecrawler serve [crawl.db] [--port] [--no-open] [--crawls-dir]`: the
  Screaming-Frog-style UI. With no file it opens empty: URL bar, Start /
  Pause / Resume / Stop / Clear, Settings, progress; each crawl is written
  to `crawls/<host>-<timestamp>.db` with its final audit. With a file it
  opens read-only (an unaudited file is audited in memory). Tabs are data
  in `web/tabs.py` (a rule-backed filter *is* the rule), rows are built in
  `web/rows.py` (base cells once, audit cells per audit revision), the
  browser polls `/api/crawl` and `/api/rows?since=&rev=` (ADR-0007).
  `session.py` (`CrawlSession`) runs the crawl on a worker thread with an
  audit thread; `crawl/control.py` is the pause/stop primitive.
- `sitecrawler crawl URL [-o pages.csv] [--db crawl.db [--resume]]`,
  `sitecrawler list urls.txt|- [--follow]`, `sitecrawler export crawl.db
  --format csv|xlsx|json`: see the Phase 1 notes in `docs/ROADMAP.md`.
- `sitecrawler audit crawl.db`: runs 72 rules over a stored crawl, writes the
  `issues` table, an indexability verdict and the link metrics per page, prints
  the fix list by severity. `sitecrawler issues crawl.db --rule ID` lists affected URLs.
- Rules live in `src/sitecrawler/audit/rules/<category>.py` as classes with
  `id`, `severity`, `category`, `summary`, `why`, `fix`; they are discovered
  automatically. `docs/user-guide/rules.md` is generated from them by
  `uv run python scripts/gen_rule_docs.py` and a unit test fails when it is
  stale. Each rule has a fixture page; `tests/integration/test_audit.py`
  maps every rule id to the exact paths it must flag.
- `CrawlView` (`audit/view.py`) is the index rules read: lookups by
  normalised URL, inlinks, groups, sitemap membership. Rules never fetch.
- CI enforces 100% branch coverage on `audit/` as a separate step.
- Web stack: FastAPI + Jinja2 + HTMX + Tabulator on 127.0.0.1; `web/app.py`
  has the routes, `web/static/app.js` the one Tabulator grid, polling and
  detail pane; vendored `htmx.min.js` (2.0.11), `tabulator.min.js`/`.css`
  (6.7.0). Rule explanations are rendered in-app at `/rules/<id>`, the
  full page per URL at `/page?url=`, built from `templates/detail/*`.
- 754 offline tests (20 of them headless Chromium, marker `browser`:
  the UI e2e tests plus the rendered crawls). ADRs 0001-0013.

Open:

- GitHub Actions: the repository is **public** since 2026-10-23, so
  Actions minutes are no longer a limit (the private repo ran out on
  2026-10-22). A full run is about 12 minutes on Ubuntu and 20 on Windows.
  There is still no branch protection, so check `gh pr checks N` before
  merging.
- `.claude/worktrees/` is empty (2026-10-23). A phase session's worktree
  folder stays locked while that session is unarchived; once its PR is
  merged, archive the session (ask Joe first), then the empty folder can
  be removed.
- Manual QA: `docs/DEVELOPMENT.md` section 5 now has a "Manual QA"
  checklist (a real-site crawl, the web UI walk-through, a spot check of
  issues against the live page, the exports). The xlsx step there is
  the still-open "opened in Excel by hand" item below.
- **mabelslabels.com row-for-row check (Phase 0 acceptance) passed on
  2026-10-22**: 300 pages at `--delay 1` against `mabelslabels_pages.csv`
  (the original script's full crawl, ignored by git). Every difference
  had a cause outside the crawler: the original CSV is Latin-1
  double-encoded (the site sends no charset header; `®`, curly quotes and
  non-breaking spaces are mojibake there and correct now), the site's
  content grew (product pages count about twice the words; the old
  BeautifulSoup method and the current lxml parser agree exactly on
  today's HTML), the sitemap gained entries (two pages moved to depth 0),
  one page's 500 became a 200, and two format changes since Phase 0:
  blocked rows write `0` where the original left blanks, and the CSV ends
  with `render_changes`. The 503 on 2026-10-21 was the site being taken
  down for emergency patching of a Magento vulnerability.
- The xlsx export has not been opened in Excel by hand.
- `redirect.http_to_https_missing` is deferred until the fixture server can
  serve HTTPS (see the note under Phase 2 in the roadmap).
- Dependabot's older uv can produce lockfile-downgrading PRs (#4 was closed
  for that); read the lock diff before merging.
- Next piece of work: **Phase 11, API integrations** (`docs/ROADMAP.md`,
  v1.x): each integration an `Enricher` that adds columns from Search
  Console, GA4, PageSpeed/CrUX or a backlink API; OAuth and keys via
  `.env`, all optional and off by default. It needs credentials Joe has to
  create, so start by asking which integration matters first. The release
  recipe is #46: bump `pyproject.toml`, `__init__.py` and `uv.lock` (`uv
  lock`), date the CHANGELOG Unreleased block, mark the roadmap row Done,
  PR, squash-merge once `gh pr checks N` is green, annotated tag on `main`,
  then a handoff PR.
- Phase 10 left for later: property values are not checked against their
  schema.org ranges; rich-result needs are checked on top-level items only
  (a Product under `WebPage.mainEntity` in JSON-LD is not checked as a
  Product); microdata `itemref`, full RDFa (`prefix`, `rel`/`rev`) and
  JSON-LD expansion are not supported; `parse/structured.py::_text`
  duplicates `parse/html.py::text_of` (importing it would be circular);
  the e2e tests do not open the Structured Data tab; the rich-result table
  is hand-kept and will drift as Google changes its docs (checked
  2026-10-22). 1.0 has no crawl-file compatibility: a missing table is
  refused by `require_crawl_db`, a missing column still fails with a SQL
  error.
- Phase 9 left for later: the thresholds (`NEAR_DUPLICATE_DISTANCE` = 10,
  `MIN_WORDS` = 200) are constants in the rules and only the report's
  distance is an option; the near-duplicate floor is the low-content
  floor, so templated pages under 200 words are reported as thin rather
  than as variants of each other; boilerplate is recognised by element
  and ARIA role only (a sidebar in a plain `<div>` counts as content);
  a change to the main-text rule or the shingle size changes every stored
  fingerprint, so it means a re-crawl (storing bodies behind a flag is
  still the obvious next step); the web Content tab has no cluster grid
  (the detail pane and `duplicates report` cover it); the e2e tests do
  not open the Content sub-tab. Crawl files written before 0.10 lack the
  `page_html` fingerprint columns and open with an error; re-crawl.
- Phase 8 left for later: canonicals are ignored by the link graph (a
  canonicalised page keeps its own node and score); no row-per-link grid in
  the web UI (the detail pane and `links report` cover it); the rule
  thresholds (`FEW_INLINKS`, `MAX_DEPTH`, `MAX_OUTLINKS`) are constants,
  not options; PageRank is pure Python (about 0.9 s per 10k pages with
  500k links, re-run on every live audit revision);
  `Store.set_link_metrics` and `set_indexability` both update rows one ORM
  object at a time (a shared cleanup); the Link Score says nothing about
  external links. Crawl files written before 0.9 lack the new `pages` and
  `links` columns and open with an error; re-crawl.
- Phase 7 left for later: the sitemap report is CLI-only (no grid of
  sitemap entries in the web UI; the Sitemaps tab is still per page);
  sitemap extensions (`<image:>`, `<video:>`, `<xhtml:link>` hreflang) are
  ignored; `generate` writes one flat sitemap (or an index of numbered
  parts), not per-section files; `lastmod` can only come from the
  `Last-Modified` header; the 50 MB-per-file limit is not checked (only the
  50,000-URL one); sitemap files over other hosts are fetched but never
  recorded as pages. Old crawl files have no `sitemaps` table and open with
  an error; re-crawl (there are no migrations during 0.x).
- PRs are merged by hand with `gh pr merge N --squash` once
  `gh pr checks N` is green. GitHub's auto-merge could not be enabled while
  the repository was private (the settings PATCH was accepted and
  ignored); it has not been tried since it went public.
- Phase 6 left for later: storing raw and rendered HTML bodies behind a
  flag so extractors can be re-run on a finished crawl (ADR-0009 names it
  as the obvious next step; today a changed extractor means crawling
  again, and `list` mode is the cheap way to redo a few pages); the UI's
  Extract and Search boxes are one spec per line with no editor or
  validation beyond the 400 on Start; the e2e Playwright tests do not open
  the Custom tab (the integration tests cover `/api/tabs`, rows and
  filters; `app.js` was checked by hand in the browser).
- Phase 5 left for later: blocking third-party hosts (analytics) in the
  renderer (only resource types are blocked now); a `--render` flag on
  `list`; the `rendered` fixture in `test_render.py` renders the whole site
  once per module, about 15 s.
- Phase 4 left for later: a "Links" row-per-link view (the detail pane's
  Inlinks/Outlinks cover it), collapsing the sidebar, dark mode, and
  resuming a stopped crawl from the UI (the CLI's `--resume` works on the
  file). Summary counts are recomputed per `(seq, audit_rev)` over every
  filter of every tab; fine at 10k pages, not profiled beyond.
- Merged branches are deleted from origin by hand after each merge
  (`git push origin --delete <branch>` from a terminal; Claude Code's
  sandbox refuses it); `git branch -r` should list only `origin/main`.
  The local checkout is clean of merged branches.
- Dependabot will now also see fastapi/uvicorn/jinja2/playwright; the
  vendored htmx/Tabulator files are upgraded by hand (replace the three files
  under `src/sitecrawler/web/static/`).

## Decisions already made (do not re-open)

| Decision | Choice |
| --- | --- |
| Interface | CLI first; local web UI (FastAPI + Jinja2 + HTMX + Tabulator) in Phase 3 |
| Storage | SQLite, one file per crawl, via SQLAlchemy 2.0 (ADR-0004) |
| HTTP | httpx + asyncio, redirects followed by hand, per-host throttle; hops that leave the crawl's hosts are not fetched (ADR-0003) |
| HTML | lxml + cssselect (since Phase 6; BeautifulSoup is gone). One `parse_document()` in `parse/html.py` serves the page fields and the extractors |
| JS rendering | Playwright async API inside the crawl loop, one Chromium, `render_workers` tabs; every parsable HTML page is rendered, rendered fields become the page, the diff is stored, the HTML bodies are not (ADR-0008) |
| Issues engine | Rule classes discovered from `audit/rules/`; docs generated from them; issues table rebuilt per run; verdict stored on pages (ADR-0005) |
| Rule overlap | One tag may appear under several rules when they ask for different actions; `page.non_indexable` and `canonical.not_self_referencing` are informational roll-ups |
| Commits | Conventional Commits, squash-merge PRs, `CHANGELOG.md` entry per change |
| List mode | URLs may span hosts; `--follow` stays within the listed hosts |
| Resume | `pages.state` is the frontier; `max_pages` counts across runs; `crawls.status` is `stopped` when capped |
| Web UI | One page, Screaming Frog layout; grids filter/export client-side; htmx and Tabulator vendored; rule pages rendered in-app (ADR-0006) |
| Live crawl | `CrawlSession` on a worker thread, audit thread with adaptive gap, file written as it goes and closed before `done`; browser polls, no websockets (ADR-0007) |
| Tabs and filters | Data in `web/tabs.py`; a filter with a rule id is that rule; presentational filters (URL flags, status class) are computed columns, not rules; the Custom tab is the one tab built per crawl, from the extraction names in the rows |
| Custom extraction | Runs in the crawl pass over the HTML in hand (rendered DOM under `--render`); bodies not stored; grammar `NAME=KIND[MODS]:EXPR` + TOML; columns `extract_<name>` / `search_<name>` (ADR-0009) |
| Sitemaps | Per-page findings are audit rules (`sitemap.*`) over normalised entries and the indexability verdict; file-level facts are `sitemap report`, not issues; `sitemap generate` is an export, `lastmod` only with `--lastmod`, never `changefreq`/`priority`; `/sitemap.xml` guessed only when robots.txt names none (ADR-0010) |
| Structured data | Parsed in-house (no extruct) over the crawl's tree into one normalised item shape, one `structured_data` row per item; checked against a bundled, reduced schema.org vocabulary and the hand-kept `RICH_RESULTS` table; FAQPage left out (retired by Google) (ADR-0013) |
| Crawl-file compatibility | None in 1.0: no migrations; a file missing a table is refused with a re-crawl message (Joe, 2026-10-23) |
| Links | The link graph is part of the audit index (`audit/graph.py`, `CrawlView.link_graph`), not `analysis/`, because rules read it; Link Score is PageRank over the follow graph (nofollow, page-wide nofollow and self-links excluded, redirects resolved to the landing page, d=0.85) on a log scale 0-100; click depth is a BFS from the start page over every internal link; `audit` stores `inlinks`, `link_depth`, `link_score` on `pages`; `links report` / `links anchors` are the report (ADR-0011) |

Full rationale in `docs/adr/`.

## Commands

```bash
uv sync                                  # install into .venv (dev deps included)
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler crawl https://example.com --db example.db --render   # headless Chromium per page
uv run sitecrawler crawl https://example.com --db example.db --extract "price=css:.price" --search "ga=G-[A-Z0-9]{6,}"
uv run sitecrawler audit example.db
uv run sitecrawler issues example.db --rule title.missing
uv run sitecrawler export example.db --format xlsx
uv run sitecrawler sitemap report example.db      # sitemap files read, other-host / uncrawled / duplicate entries
uv run sitecrawler sitemap generate example.db --lastmod   # sitemap.xml of indexable 200 pages next to the DB
uv run sitecrawler schema report example.db       # every structured data finding, with type and property
uv run python scripts/update_schemaorg.py         # refresh the bundled schema.org vocabulary
uv run sitecrawler serve                     # web UI on http://127.0.0.1:8765, crawl from the browser
uv run sitecrawler serve example.db          # browse a stored crawl read-only
uv run playwright install chromium           # once per machine, for tests/e2e/test_web_ui.py
uv run ruff format . && uv run ruff check .
uv run mypy
uv run pytest --cov                      # whole suite, offline, ~160 s (browser tests included)
uv run pytest tests/unit                 # fast loop
uv run pytest -m "not browser"           # without Chromium installed
uv run pytest --cov=sitecrawler.audit --cov-fail-under=100 tests/unit/audit tests/integration/test_audit.py
uv run python scripts/gen_rule_docs.py   # after adding or editing a rule
uv run pre-commit run --all-files
uv run mkdocs serve                      # docs at http://127.0.0.1:8000
gh pr list                               # open PRs
```

Commits must end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
PR descriptions end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

Per-PR workflow that worked well: branch from `main`, tests first, implement,
docs + CHANGELOG, run the gates, commit, push, `gh pr create`, run
`/code-review` and fix the cheap findings, squash-merge once CI is green.
When stacking the next PR on an unmerged branch, rebase with
`git rebase --onto origin/main <old-base-tip> <branch>` after the squash merge.

Adding a rule: a class in the right `audit/rules/<category>.py`, a fixture page
under `tests/fixtures/site/audit/` linked from `audit/index.html` (give it a
30-60 character title, a 70-155 character unique description, one H1, an H2
and a self canonical so it trips nothing else), a line in `TRIGGERS`, a unit
test, then regenerate `rules.md`.

## Gotchas learned the hard way

- **libxml2 differs between Windows and Linux.** Text after `</html>` is
  kept on Windows and dropped on the Ubuntu runner, so a test page must be
  well formed or it passes locally and fails in CI (#45).
- **`open_store` creates missing tables.** A crawl file from an older
  version opens cleanly with an empty new table; `missing_tables()` is
  the guard. New tables need no extra work; new *columns* still fail with
  a SQL error.
- Python 3.13's `json` reports a trailing comma as `Illegal trailing comma
  before end of object` at the comma's line, not the closing brace's.
- **Do not run two test suites at once on this machine.** Under the load,
  local fixture fetches fail now and then and integration tests that
  count issues go red (an orphan that is not, a missing duplicate title).
  Re-run alone before investigating.
- The full local suite takes 9-12 minutes now (the rendered-crawl tests
  dominate); run it in the background and read the result file.

- **The Claude Code Bash tool drops any command whose heredoc runs past
  about 100 lines** ("unexpected EOF while looking for matching quote");
  nothing in that command runs, so a multi-file patch silently does nothing.
  Keep inline heredocs short, or write the patch script to the scratchpad
  and run it with `python`.
- **Rich tables put `│` between cells.** A whitespace-squashed assertion on
  CLI output must allow `\W+` between the values of one row.
- **PageRank on the fixture needs the hubs to link home.** With the home
  page linked from `/about` alone, a tight cluster (the four product pages)
  outranks it. The `Home` links on the hub, blog and product pages are
  what make the roadmap's "home page highest" acceptance true; keep them
  when adding fixture pages.

- **`localhost` is IPv6-first on this machine.** The test server binds to
  `127.0.0.1` explicitly via `httpserver_listen_address` in
  `tests/conftest.py`. Keep it that way.
- **`.gitignore` patterns without a leading slash match at any depth.**
  `site/` (MkDocs output) silently swallowed `tests/fixtures/site/audit/` and
  the fixture pages never reached CI. It is now `/site/`.
- **The fixture page set is computed, not hard-coded.** `tests/conftest.py`
  `site_pages()` derives it from the HTML files plus the routes in
  `routes.json` that some page links to. Intermediate redirect hops are not
  pages.
- **Rich wraps console output to the terminal width**, narrower on Linux CI.
  Compare CLI output with whitespace collapsed.
- **Redirect targets are requested as hops.** A "not re-fetched" assertion
  must exclude pages other pages redirect to.
- **Never point a test at a real hostname.** Off-site redirects are now safe
  because the fetcher stops at the first out-of-scope hop, but a second local
  `HTTPServer` is still the way to test another host.
- **Windows holds SQLite files open until `engine.dispose()`.** Use
  `with open_store(...)` and close before re-opening or deleting.
- **Crawl `depth` is first-discovery depth.** Integration tests use `workers=1`.
- The Bash tool on this Windows machine mangles heredocs containing
  apostrophes; use the Write tool for files or a Python script file for edits.
- `-q` in `pytest` addopts plus `-q` on the command line gives `-qq`, which
  hides the pass/fail summary line.
- Dependabot's uv is older than ours: its grouped lockfile PRs can downgrade
  packages. Read the lock diff before merging.
- **Playwright's sync API keeps an asyncio loop running on the main thread**
  for as long as it is open. With the `pytest-playwright` plugin's
  session-scoped fixtures that loop outlived the browser tests and every
  `asyncio.run` in the rest of the suite failed (100 errors). The plugin is
  not installed; `tests/e2e/test_web_ui.py` opens `sync_playwright()` in a
  module-scoped fixture, and `crawled_db` runs its crawl in a worker thread.
- Starlette 1.9 warns that its test client wants `httpx2`; httpx 0.28 still
  works and the warning is filtered in `pyproject.toml`.
- Jinja's `tojson` leaves double quotes alone (it escapes `<`, `>`, `&`,
  `'`), so a `data-columns='{{ columns | tojson }}'` attribute is fine and a
  test should look for `"url"`, not `&#34;url&#34;`.
- Python scripts that rewrite files on this machine write CRLF; the repo is
  LF. Convert before committing or the diff is every line
  (`write_text(..., newline="\n")`).
- `tests/integration/test_session_live.py::test_live_crawl_matches_the_cli_audit`
  failed once on the Windows CI runner (#36, a docs-only change) with two
  `response.error` pages instead of one: a transient socket failure on the
  runner turned a second fixture page into an ERROR record. A re-run of
  the job passed. Treat a lone Windows failure of that test as a flake and
  re-run before investigating.
- **Playwright clicks and `<details>` menus**: an open Settings panel in
  the top bar covers the Start button; the e2e tests close it before
  clicking. The Tabulator search box matches every column, so select a
  row by its `url` cell (`.tabulator-cell[tabulator-field="url"]`), not
  by row text.
- Rich wraps long paths mid-word in CLI output; compare with every
  whitespace removed when asserting on a path.
- `pydantic.Field(5000, ge=1)` reads as "no default" to mypy without the
  plugin; write `Field(default=5000, ge=1)`.
- **Playwright's async API is fine inside `asyncio.run` on the main
  thread** (that is how `Crawler.run()` renders) as long as no sync
  Playwright is open in the same process; the sync API is the one that
  owns a loop. Keep the UI e2e module's `sync_playwright()` fixture
  module-scoped for that reason.
- Chromium requests `/favicon.ico` on every page; the fixture server
  answers 404 and nothing records it. A `pytest-httpserver` `HTTPServer`
  created by hand (`test_render.py::site_module`) is the way to keep one
  rendered crawl for a whole module without the function-scoped
  `httpserver` fixture clearing its handlers between tests.
- `networkidle` never fires on a page that keeps polling, and a
  `--render-selector` that never appears times out the same way; both are
  reported as `render.failed`, not raised. Keep `render_timeout_seconds`
  small in tests that exercise the failure path.
- Ruff's B009 rewrites `getattr(x, "name")` to `x.name`, so a fake that
  returns `object` must be typed as the real record or mypy fails after
  `ruff --fix`.
- lxml refuses a `str` that starts with an XML encoding declaration
  (XHTML pages); `parse_document()` encodes to UTF-8 bytes and parses with
  `HTMLParser(encoding="utf-8")`. An empty or blank document raises
  `ParserError`, caught there too. `lxml.html.fromstring` returns a
  different root for fragments than for documents; always use
  `document_fromstring`, which wraps fragments in `<html><body>`.
- lxml-stubs type `document_fromstring` as `_Element`, which has no
  `cssselect`/`text_content`; use `lxml.cssselect.CSSSelector(expr)(doc)`
  and `itertext()` instead, and `itertext()` is typed `str | bytes`.
- A fixture page must never load anything from a real host: Chromium
  follows `<script src>` under `--render`, so the product pages load their
  GA snippet from the fixture server's own `/gtag.js` (a 404, harmless).
- Attribute values extracted with `attr=` or `/@href` come back as written
  in the page (relative), not resolved against the URL.
- An `Issue` must name a crawled page: `Store.replace_issues` maps
  `issue.url` to `pages.id` and raises `KeyError` otherwise. Findings about
  things that are not pages (a sitemap file, an entry on another host) go in
  a report, not a rule (ADR-0010).
- The audit test helper `page()` defaults `found_on="start"`; a rule that
  treats the start page specially (`sitemap.orphan`) needs its test pages
  given another `found_on`.
- **Never `gh pr merge --delete-branch` on a PR that other PRs are based
  on.** Deleting the base branch closed #22 and GitHub refused to reopen
  it or change its base; #26 is the same branch re-filed against `main`.
  Merge stacked PRs with `gh pr merge N --squash`, rebase and retarget the
  next PR, and delete branches only at the end.

## Where to look next

- Phase 11 scope: `docs/ROADMAP.md` under "Phase 11". Enrichers add
  columns per URL, so they look like the extraction columns (Phase 6:
  `web/tabs.py::custom_tab`, `store/dump.py::_pages`); its acceptance
  ("thin title with 40k impressions" as one Issues filter) means an audit
  rule that reads enricher data. `Crawler.arun()` is the entry point for
  callers that already have an event loop; `CrawlSession` is how the UI
  drives it.
- Structured data: `parse/structured.py` (the reader), `audit/structured.py`
  (vocabulary, index, findings), `audit/richresults.py` (Google's needs,
  one entry per type, each naming its source page),
  `audit/rules/structured.py`, `analysis/structured.py`,
  `cli/schema_cmd.py`. `tests/unit/test_structured.py` is the parser's
  spec; `tests/unit/audit/test_structured.py` the checker's.
- Links: `audit/graph.py` (`LinkGraph`, PageRank, click depth,
  `is_broken`, `redirects_elsewhere`), `audit/directives.py`,
  `audit/rules/links.py` (the six rules and their thresholds),
  `analysis/links.py` (`LinkReport`, `anchor_texts`), `cli/links_cmd.py`,
  `parse/html.py::link_position`. `tests/unit/audit/test_graph.py` is the
  graph's spec in small examples; `tests/integration/test_links.py` the
  acceptance against the fixture site.
- Sitemaps: `parse/sitemap.py` (entries, gzip), `Crawler._seed_from_sitemaps`
  (files and entries), `audit/rules/sitemaps.py` (the four rules),
  `analysis/sitemaps.py` (`SitemapReport`), `export/sitemap.py`
  (`write_sitemap`, index splitting), `cli/sitemap_cmd.py`. The conftest
  serves any fixture file gzip-compressed at `<path>.gz` when `routes.json`
  lists it under `gzip`.
- Custom extraction: `parse/extract.py` (grammar, TOML, `ExtractorSet`),
  `Crawler._fetch_and_parse` (where it runs), `store/dump.py::_pages` and
  `web/tabs.py::custom_tab` (where the per-crawl columns come from).
- The web UI's read side: `web/rows.py` (`base_row`, `AuditIndex`,
  `RowStore`), `web/tabs.py` (`TABS`). A new tab or filter is a spec; a new
  column is a key in `base_row` (and `tests/unit/web/test_tabs.py` checks
  every filter column is produced). `static/app.js` has the grid, polling
  and detail pane in one file.
- The fixture site is the contract for every feature; `tests/e2e/test_web_ui.py`
  and `tests/integration/test_web_tabs.py` assert the numbers
  `tests/integration/test_audit.py` already knows.

## Claude memory

Two memory files exist under
`C:\Users\joema\.claude\projects\D--Projects-scraper\memory\`:
`user-joe-profile.md`, `project-sitecrawler-roadmap.md` and
`feedback-bash-heredoc-limit.md`. They repeat the owner, roadmap and
heredoc facts above.
