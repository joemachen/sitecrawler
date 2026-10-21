# Development environment and process

This document describes how the project is set up locally, the tools we use, and
the process every change goes through. If you only read one doc, read this one.

The guiding idea: **automate every quality check so that a human never has to
remember to run it.** Formatting, linting, type checking, and tests run on every
commit (locally via pre-commit) and on every push (in CI). If it is green, it is
mergeable.

---

## 1. Toolchain

| Concern | Tool | Why |
| --- | --- | --- |
| Python version | 3.13 (pinned in `.python-version`) | Already installed; modern typing features. |
| Package and env manager | [uv](https://docs.astral.sh/uv/) | One tool for venvs, dependency resolution, lockfile, and running scripts. Replaces pip, venv, pip-tools, pipx. Very fast. |
| Project metadata | `pyproject.toml` (PEP 621) | Single source of truth for deps, scripts, tool config. |
| Formatting and linting | [ruff](https://docs.astral.sh/ruff/) | Replaces black, isort, flake8, pyupgrade and more. One config, sub-second runs. |
| Type checking | mypy in `--strict` mode | Catches whole classes of bugs before tests run. Strict from day one is far easier than retrofitting. |
| Tests | pytest + pytest-cov + pytest-asyncio | Standard. Coverage gate enforced in CI. |
| HTTP mocking in tests | respx (for httpx) + pytest-httpserver (real local server for integration tests) | Unit tests never touch the network. |
| Git hooks | pre-commit | Runs ruff, mypy, and quick tests before every commit. |
| CI | GitHub Actions | Free for public and small private repos; matrix on Windows and Linux. |
| Dependency updates | Dependabot (or Renovate) | Weekly PRs for outdated deps; security alerts. |
| Docs site | MkDocs + Material theme + mkdocstrings | Renders `docs/` and API reference from docstrings. |
| CLI framework | Typer | Type-hint driven CLI, auto help, shell completion. |
| Terminal output | Rich | Progress bars, tables, tracebacks. |
| Config | pydantic-settings | Typed config from `.env`, env vars, and CLI flags with validation. |
| Logging | structlog | Structured, machine-readable logs; essential for debugging a long crawl. |

Everything above is pinned in `uv.lock`, so every machine resolves identical
versions.

---

## 2. Repository layout

```
scraper/                      # repo root (rename to the project name later)
├── .github/
│   ├── workflows/ci.yml      # lint + type + test on every push/PR
│   ├── dependabot.yml
│   ├── ISSUE_TEMPLATE/       # bug report, feature request
│   └── PULL_REQUEST_TEMPLATE.md
├── docs/
│   ├── DEVELOPMENT.md        # this file
│   ├── ARCHITECTURE.md       # how the system is built
│   ├── ROADMAP.md            # what we are building, in what order
│   ├── adr/                  # Architecture Decision Records
│   └── user-guide/           # end-user docs rendered by MkDocs
├── src/
│   └── sitecrawler/          # the package (src layout: tests import the installed package, not the folder)
│       ├── __init__.py
│       ├── cli/              # Typer commands only; no business logic here
│       ├── crawl/            # fetching, scheduling, robots, rendering
│       ├── parse/            # HTML/XML parsing into typed page records
│       ├── audit/            # rules that turn page records into issues
│       ├── analysis/         # link graph, duplicates, sitemaps
│       ├── store/            # SQLite persistence
│       ├── export/           # CSV, XLSX, JSON writers
│       ├── integrations/     # GA4, GSC, PSI, etc. (later)
│       └── web/              # local web UI (later)
├── tests/
│   ├── unit/                 # fast, no I/O
│   ├── integration/          # local fixture site served over HTTP
│   ├── e2e/                  # full CLI runs against the fixture site
│   └── fixtures/site/        # a small static site that exhibits every issue we detect
├── pyproject.toml
├── uv.lock
├── .pre-commit-config.yaml
├── .python-version
├── .env.example              # documented env vars; real .env is git-ignored
├── CHANGELOG.md
├── CONTRIBUTING.md           # short; points here
├── LICENSE
└── README.md
```

Rules of the layout:

- **`src/` layout.** Tests run against the installed package, which catches
  packaging mistakes. Nothing imports from the repo root.
- **One responsibility per subpackage.** `crawl` does not parse HTML; `audit`
  does not fetch URLs. This keeps each piece testable in isolation.
- **CLI is a thin shell.** Every command calls into library code that could be
  used from Python directly or from the future web UI.

---

## 3. One-time setup

```bash
# 1. Install uv (Windows PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 2. Clone, then from the repo root:
uv sync                       # creates .venv, installs runtime + dev deps from uv.lock
uv run pre-commit install     # installs git hooks
uv run playwright install chromium   # only needed once JS rendering lands (Phase 4)

# 3. Verify
uv run ruff check .
uv run mypy
uv run pytest
```

`uv run <cmd>` runs a command inside the project venv without activating it.

---

## 4. Daily workflow

1. **Pick an issue.** All work starts as a GitHub issue, even for a solo
   developer. The issue states the problem, the acceptance criteria, and links
   to the roadmap milestone. Small fixes can be opened and closed in the same PR.
2. **Branch from `main`.** Naming: `feat/short-description`, `fix/...`,
   `docs/...`, `chore/...`. Branches live for days, not weeks.
3. **Write a failing test first** where practical. For audit rules this is
   mandatory: add a page to `tests/fixtures/site/` that triggers the rule, then
   make the rule pass.
4. **Commit small, commit often.** Pre-commit runs ruff format, ruff check,
   mypy, and the unit test suite. Commit messages follow
   [Conventional Commits](https://www.conventionalcommits.org/):
   `feat(audit): flag missing canonical`, `fix(crawl): stop on redirect loop`.
5. **Open a PR**, even if you will merge it yourself. The PR template asks for:
   what changed, why, how it was tested, and any docs updated. Run
   `/code-review` on it. CI must be green.
6. **Squash-merge to `main`.** `main` is always releasable.
7. **Update `CHANGELOG.md`** under "Unreleased" as part of the PR.

### Definition of done

A change is done when all of the following are true:

- [ ] Tests cover the new behaviour and the whole suite passes.
- [ ] `ruff`, `mypy --strict` pass with no new ignores.
- [ ] Public functions and classes have Google-style docstrings.
- [ ] User-facing behaviour is documented in `docs/user-guide/`.
- [ ] `CHANGELOG.md` has an entry.
- [ ] No secrets, no hard-coded site-specific values.

---

## 5. Quality standards

### Code style

- Ruff enforces formatting, import order, and a broad rule set (`E, F, W, I, N,
  UP, B, SIM, RUF, PT, D`). Docstring rules (`D`) apply to public API only.
- Line length 100.
- Prefer small pure functions. Fetching, parsing, and judging are separate steps
  so each can be tested without the others.
- Dataclasses or pydantic models for every record that crosses a module
  boundary. No passing dicts around.
- Type hints everywhere. `Any` requires a comment explaining why.

### Testing strategy

| Layer | What it tests | Speed | Network |
| --- | --- | --- | --- |
| Unit | A parser given HTML returns the right record; a rule given a record returns the right issue | ms | None (respx mocks) |
| Integration | Crawler against `tests/fixtures/site/` served by pytest-httpserver | seconds | localhost only |
| End to end | `sitecrawler crawl http://localhost:PORT` then assert on the CSV/DB | seconds | localhost only |
| Live smoke (manual, optional) | A capped crawl of a real site | minutes | Yes; never in CI |

The fixture site is the heart of the test suite. Every audit rule we ship has a
page in it that triggers the rule and a page that does not. When a bug is found
on a real site, we add a minimal reproduction to the fixture site first.

Coverage gate: 85% overall, 100% for `audit/` rules.

### Documentation

- `docs/user-guide/` explains features for someone who will never read the
  code: what each check means, why it matters, how to fix it.
- Docstrings explain intent and edge cases, not what the code obviously does.
- Every non-obvious design choice gets an ADR (see `docs/adr/`). An ADR is one
  page: context, decision, consequences. Writing it takes ten minutes and saves
  hours of "why did we do it this way?" later.

### Security and politeness

- Secrets (API keys, OAuth tokens) live in `.env`, which is git-ignored.
  `.env.example` documents every variable with a placeholder value.
- The crawler identifies itself with a descriptive User-Agent, honours
  `robots.txt` by default, and rate-limits per host. Overriding these is an
  explicit flag and is logged.
- Dependabot security alerts are addressed within a week.
- Never log full response bodies at INFO level; they may contain personal data.

---

## 6. Versioning and releases

- Semantic versioning. `0.x` until the core crawl and issues engine are stable.
- `CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/).
- A release is a git tag `vX.Y.Z` on `main`. CI builds a wheel and attaches it
  to a GitHub Release. Installable with `uv tool install` or `pipx`.

---

## 7. Project tracking

- **GitHub Issues** for everything actionable. Labels: `bug`, `feat`, `docs`,
  `chore`, plus one per area (`area:crawl`, `area:audit`, ...).
- **GitHub Milestones** map one-to-one to roadmap phases.
- **GitHub Projects** board with columns Backlog, Ready, In progress, Review,
  Done. Keep "In progress" to one or two items.
- The roadmap in `docs/ROADMAP.md` is the long-term view; the board is the
  two-week view. When they disagree, update the roadmap.

---

## 8. Working with Claude Code on this project

- `CLAUDE.md` at the repo root tells Claude the commands to run, the layout, and
  the conventions above, so every session starts with the same context.
- Use `/code-review` before merging and `/simplify` after a feature lands.
- Ask for an ADR whenever a non-trivial design decision is made in a session.
