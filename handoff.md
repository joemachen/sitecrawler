# Handoff: sitecrawler

Read this first in a new session. It is the state of the project as of
2026-10-21 (late evening) and everything that is not obvious from the code.

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

Phases 0, 1 and 2 are complete and on `main`, released as v0.3.0. CI is green
on Ubuntu, Windows and the docs build. Phase 2 landed as four squash-merged
PRs (#10 framework, #11 content rules, #12 canonical/robots rules, #13
hreflang/pagination rules) plus a release PR.

What exists now:

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
- 252 offline tests, ~99% coverage. ADRs 0001-0005.

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
- Next piece of work: **Phase 3, the local web UI** (FastAPI + Jinja2 + HTMX
  + Tabulator over a stored crawl, ADR-0002). The Issues tab reads the
  `issues` table and the rules' `summary`/`why`/`fix`; `store/dump.py` and
  `Store.iter_issues()` are the read side to build on.

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

Full rationale in `docs/adr/`.

## Commands

```bash
uv sync                                  # install into .venv (dev deps included)
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler audit example.db
uv run sitecrawler issues example.db --rule title.missing
uv run sitecrawler export example.db --format xlsx
uv run ruff format . && uv run ruff check .
uv run mypy
uv run pytest --cov                      # whole suite, offline, ~80 s
uv run pytest tests/unit                 # fast loop
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

## Where to look next

- Phase 3 scope and acceptance: `docs/ROADMAP.md` under "Phase 3".
- Read side for the UI: `Store.iter_pages()`, `Store.iter_issues()`,
  `Store.issue_counts()`, `store/dump.py`; rule metadata via
  `sitecrawler.audit.load_rules()`.
- The fixture site is the contract for every feature; the Playwright e2e
  test in Phase 3 should assert the numbers `tests/integration/test_audit.py`
  already knows.

## Claude memory

Two memory files exist under
`C:\Users\joema\.claude\projects\D--Projects-scraper\memory\`:
`user-joe-profile.md` and `project-sitecrawler-roadmap.md`. They repeat the
owner and roadmap facts above.
