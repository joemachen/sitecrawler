# Handoff: sitecrawler

Read this first in a new session. It is the state of the project as of
2026-10-21 (v0.5.0 released, Phase 5 not started) and everything that is
not obvious from the code.

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

What exists now:

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
- `sitecrawler audit crawl.db`: runs 51 rules over a stored crawl, writes the
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
- ~450 offline tests (8 of them headless Chromium, marker `browser`).
  ADRs 0001-0007.

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
- Next piece of work: **Phase 5, JavaScript rendering**
  (`docs/ROADMAP.md`). Playwright is already a dev dependency
  and Chromium is installed in CI. The UI needs no new tab for it until
  the rendered-vs-raw diff exists; `--render` can go into the Settings
  panel (`StartRequest` in `web/app.py`).
- Phase 4 left for later: a "Links" row-per-link view (the detail pane's
  Inlinks/Outlinks cover it), collapsing the sidebar, dark mode, and
  resuming a stopped crawl from the UI (the CLI's `--resume` works on the
  file). Summary counts are recomputed per `(seq, audit_rev)` over every
  filter of every tab; fine at 10k pages, not profiled beyond.
- Merged Phase 4 branches `feat/web-shell`, `feat/web-live`,
  `feat/web-detail`, `chore/release-v0.5.0` and the older
  `docs/handoff-timing` may still exist on origin (Claude Code's sandbox
  refuses `git push --delete`); delete them by hand if `git branch -r`
  still lists them. The other pre-v0.5.0 branches are gone.
- Dependabot will now also see fastapi/uvicorn/jinja2/playwright; the
  vendored htmx/Tabulator files are upgraded by hand (replace the three files
  under `src/sitecrawler/web/static/`).

## Decisions already made (do not re-open)

| Decision | Choice |
| --- | --- |
| Interface | CLI first; local web UI (FastAPI + Jinja2 + HTMX + Tabulator) in Phase 3 |
| Storage | SQLite, one file per crawl, via SQLAlchemy 2.0 (ADR-0004) |
| HTTP | httpx + asyncio, redirects followed by hand, per-host throttle; hops that leave the crawl's hosts are not fetched (ADR-0003) |
| HTML | lxml (+ cssselect) once custom extraction lands; BeautifulSoup today |
| JS rendering | Playwright headless Chromium, Phase 4 |
| Issues engine | Rule classes discovered from `audit/rules/`; docs generated from them; issues table rebuilt per run; verdict stored on pages (ADR-0005) |
| Rule overlap | One tag may appear under several rules when they ask for different actions; `page.non_indexable` and `canonical.not_self_referencing` are informational roll-ups |
| Commits | Conventional Commits, squash-merge PRs, `CHANGELOG.md` entry per change |
| List mode | URLs may span hosts; `--follow` stays within the listed hosts |
| Resume | `pages.state` is the frontier; `max_pages` counts across runs; `crawls.status` is `stopped` when capped |
| Web UI | One page, Screaming Frog layout; grids filter/export client-side; htmx and Tabulator vendored; rule pages rendered in-app (ADR-0006) |
| Live crawl | `CrawlSession` on a worker thread, audit thread with adaptive gap, file written as it goes and closed before `done`; browser polls, no websockets (ADR-0007) |
| Tabs and filters | Data in `web/tabs.py`; a filter with a rule id is that rule; presentational filters (URL flags, status class) are computed columns, not rules |

Full rationale in `docs/adr/`.

## Commands

```bash
uv sync                                  # install into .venv (dev deps included)
uv run sitecrawler crawl https://example.com --db example.db
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
- **Never `gh pr merge --delete-branch` on a PR that other PRs are based
  on.** Deleting the base branch closed #22 and GitHub refused to reopen
  it or change its base; #26 is the same branch re-filed against `main`.
  Merge stacked PRs with `gh pr merge N --squash`, rebase and retarget the
  next PR, and delete branches only at the end.

## Where to look next

- Phase 5 scope and acceptance: `docs/ROADMAP.md` under "Phase 5". It needs
  a fixture page that injects its title, canonical and three links via JS,
  a `--render` flag on `crawl`, and a rendered-vs-raw diff. `Crawler.arun()`
  is the entry point for callers that already have an event loop;
  `CrawlSession` is how the UI drives it.
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
