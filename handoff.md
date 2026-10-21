# Handoff: sitecrawler

Read this first in a new session. It is the state of the project as of
2026-10-21 and everything that is not obvious from the code.

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

Phase 0 (foundation) is complete and on `main` with CI green on Ubuntu,
Windows and the docs build. Nothing is uncommitted except this file.

Done:

- `sitecrawler crawl URL -o pages.csv` reproduces the original script: sitemap
  seeding, robots.txt, breadth-first link following, CSV with status, title,
  meta description, H1, canonical, depth, found-on, link count, word count.
- Package layout: `crawl/` (Frontier, RobotsPolicy, Fetcher, Crawler), `parse/`
  (html, sitemap), `export/` (csv), `cli/` (Typer). `store/`, `audit/`,
  `analysis/` are empty placeholders. All cross-module records are dataclasses
  in `src/sitecrawler/models.py`.
- 48 offline tests (unit / integration / e2e) at 95% coverage, against a
  fixture site in `tests/fixtures/site/` served by pytest-httpserver.
- Tooling: ruff, mypy `--strict`, pytest + 85% coverage gate, pre-commit hooks
  installed, GitHub Actions CI, Dependabot, issue and PR templates, MkDocs site.
- Docs: `docs/DEVELOPMENT.md` (process), `docs/ARCHITECTURE.md` (design and
  planned SQLite schema), `docs/ROADMAP.md` (10 phases with acceptance
  criteria), `docs/adr/` (two ADRs), `docs/user-guide/crawl.md`.
- `CLAUDE.md` at the root gives Claude the commands and conventions.

Open:

- Phase 0 acceptance item still unchecked: a capped live crawl of
  mabelslabels.com compared row-for-row with `mabelslabels_pages.csv` (local,
  git-ignored, 1,691 rows from the original script). Blocked: see gotchas.
- Four Dependabot PRs (#1-#4) are open: three GitHub Actions version bumps and
  one grouped dev-dependency bump. Joe has not yet said whether to merge them.
- A proposed session card "Phase 1: async crawler, SQLite store, list mode"
  exists in the Claude desktop app. If it was not started, Phase 1 is the next
  piece of work.

## Decisions already made (do not re-open)

| Decision | Choice |
| --- | --- |
| Interface | CLI first; local web UI (FastAPI + Jinja2 + HTMX + Tabulator) arrives in Phase 3 |
| Storage | SQLite, one file per crawl, via SQLAlchemy 2.0 (Phase 1) |
| HTTP | Switch from requests + threads to httpx + asyncio in Phase 1; interfaces stay |
| HTML | lxml (+ cssselect) once custom extraction lands; BeautifulSoup today |
| JS rendering | Playwright headless Chromium, Phase 4 |
| Issues engine | Rule classes with id, severity, category, summary, why, fix; docs generated from them |
| Commits | Conventional Commits, squash-merge PRs, `CHANGELOG.md` entry per change |
| Package name | `sitecrawler` |

Full rationale: `docs/adr/0001-python-uv-sqlite-stack.md`,
`docs/adr/0002-cli-first-web-ui-later.md`.

## Commands

```bash
uv sync                                  # install into .venv (dev deps included)
uv run sitecrawler crawl https://example.com -o pages.csv
uv run ruff format . && uv run ruff check .
uv run mypy
uv run pytest --cov                      # whole suite, offline, ~3 s
uv run pytest tests/unit                 # fast loop
uv run pre-commit run --all-files
uv run mkdocs serve                      # docs at http://127.0.0.1:8000
gh pr list                               # see Dependabot PRs
gh run list --workflow CI                # CI history
```

Commits must end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
PR descriptions end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

## Gotchas learned the hard way

- **`localhost` is IPv6-first on this machine.** Every connection to
  `localhost` stalls ~2 s before falling back to 127.0.0.1, which made the test
  suite look hung (a 30-hop redirect loop took a minute). The test server binds
  to `127.0.0.1` explicitly via `httpserver_listen_address` in
  `tests/conftest.py`. Keep it that way.
- **mabelslabels.com blocks after a full crawl.** After the 1,691-page crawl on
  2026-10-21 the site returned 503 from its AWS load balancer with
  `Retry-After: 3600`, even to a browser User-Agent. Use a longer `--delay`
  (1 s or more) there and verify it answers 200 before relying on it.
- **Crawl `depth` is first-discovery depth, not shortest path.** With more
  than one worker it varies run to run. Integration tests use `workers=1`.
  Shortest-path depth comes from the link graph in Phase 7.
- **gitignore does not allow trailing comments on a pattern line.** A
  `site/  # comment` line silently matches nothing; the MkDocs build output
  got staged once because of this. Comments go on their own line.
- **Run interpreters on downloaded content with `python -I`** and keep
  crawl output out of git (`*.csv`, `*.db`, `*.log` are ignored).
- `gh repo create --push` printed "Name already exists" after succeeding; it
  was a spurious internal retry. Check `git ls-remote` before reacting.
- The Bash tool on this Windows machine mangles heredocs containing
  apostrophes; use the Write tool for files.
- `-q` in `pytest` addopts plus `-q` on the command line gives `-qq`, which
  hides the pass/fail summary line.

## Where to look next

- Phase 1 scope and acceptance: `docs/ROADMAP.md` under "Phase 1".
- Planned schema and the fetcher switch: `docs/ARCHITECTURE.md` sections 3-4.
- Process and definition of done: `docs/DEVELOPMENT.md` section 4.
- The fixture site is the contract for every feature: add a page that triggers
  a behaviour before implementing it.

## Claude memory

Two memory files exist under
`C:\Users\joema\.claude\projects\D--Projects-scraper\memory\`:
`user-joe-profile.md` and `project-sitecrawler-roadmap.md`. They repeat the
owner and roadmap facts above.
