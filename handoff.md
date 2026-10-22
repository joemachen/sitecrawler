# Handoff: sitecrawler

Read this first in a new session. It is the state of the project as of
2026-10-22 (v0.6.0 released; Phase 6 implemented on PR #PRNUM, awaiting
merge and the v0.7.0 release) and everything that is not obvious from the
code.

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

**Phase 6 (custom extraction and custom search) is implemented** on one
PR, `feat/extract` (#PRNUM), branched from `main` after v0.6.0. It is not
released: v0.7.0 waits for Joe's go-ahead. ADR-0009 records the design
call: extractors run inside `Crawler._fetch_and_parse` over the text the
page was parsed from (the rendered DOM under `--render`), the HTML bodies
are still not stored, and lxml + cssselect replaced BeautifulSoup (every
existing parser test stayed green; `tests/unit/test_html.py` gained edge
cases for `<br>`, comments, empty documents and XHTML prologues).

What exists now:

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
- `sitecrawler audit crawl.db`: runs 53 rules over a stored crawl, writes the
  `issues` table and an indexability verdict per page, prints the fix list by
  severity. `sitecrawler issues crawl.db --rule ID` lists affected URLs.
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
- ~560 offline tests (19 of them headless Chromium, marker `browser`:
  the UI e2e tests plus the rendered crawls). ADRs 0001-0009.

Open:

- **mabelslabels.com row-for-row check (Phase 0 acceptance) is still
  parked.** The 503 on 2026-10-21 was the site being taken down for emergency
  patching of a worldwide Magento vulnerability, not the crawler being
  blocked. Retry once the site is back; use `--delay 1`.
- The xlsx export has not been opened in Excel by hand.
- `redirect.http_to_https_missing` is deferred until the fixture server can
  serve HTTPS (see the note under Phase 2 in the roadmap).
- Dependabot's older uv can produce lockfile-downgrading PRs (#4 was closed
  for that); read the lock diff before merging.
- Next: merge #PRNUM once CI is green (squash, like #28), then ask Joe
  before releasing **v0.7.0** (the release recipe is #29: bump
  `pyproject.toml` and `__init__.py`, move the CHANGELOG Unreleased block
  under the version, PR, merge, annotated tag). After that, **Phase 7, XML
  sitemap audit and generation** in `docs/ROADMAP.md`.
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
- Merged branches `feat/render`, `chore/release-v0.6.0`,
  `docs/handoff-v0.6.0` and (once merged) `feat/extract` may still exist on origin (Claude Code's sandbox
  refuses `git push --delete`); delete them by hand if `git branch -r`
  still lists them. The local checkout also carries every merged Phase 3
  and 4 branch plus a `.claude/worktrees/` entry for the Phase 5 session;
  `git worktree prune` and `git branch -d` clean those up.
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

Commits must end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
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
- **Never `gh pr merge --delete-branch` on a PR that other PRs are based
  on.** Deleting the base branch closed #22 and GitHub refused to reopen
  it or change its base; #26 is the same branch re-filed against `main`.
  Merge stacked PRs with `gh pr merge N --squash`, rebase and retarget the
  next PR, and delete branches only at the end.

## Where to look next

- Phase 7 scope and acceptance: `docs/ROADMAP.md` under "Phase 7". Sitemap
  parsing is `parse/sitemap.py` (locs only today), sitemap membership is
  `CrawlView.in_sitemap`, and the stored URLs are `sitemap_urls`.
  `Crawler.arun()` is the entry point for callers that already have an
  event loop; `CrawlSession` is how the UI drives it.
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
`user-joe-profile.md` and `project-sitecrawler-roadmap.md`. They repeat the
owner and roadmap facts above.
