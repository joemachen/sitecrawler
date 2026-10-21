# ADR-0001: Python, uv and SQLite as the core stack

**Status:** Accepted
**Date:** 2026-10-21

## Context

The project started as a 300-line Python script and is growing into an SEO
audit tool with crawling, parsing, rule evaluation, analysis and a local UI.
It is developed by one person on Windows, must run on Linux in CI, and should
be installable by non-developers later.

## Decision

- **Python 3.13** for everything. The crawling/parsing ecosystem (httpx, lxml,
  Playwright, extruct) is strongest here and the existing code is Python.
- **uv** manages the virtualenv, dependencies, lockfile and tool execution.
  One tool instead of pip + venv + pip-tools + pipx.
- **SQLite**, one file per crawl, as the only storage. Accessed through
  SQLAlchemy 2.0 so the schema is declared in code and migrations are possible.
- **ruff + mypy strict + pytest** as non-negotiable quality gates from day one.

## Consequences

- Easier: a single `uv sync` sets up any machine identically; crawls are
  re-queryable files that can be emailed or diffed; no services to run.
- Harder: Python concurrency is bounded; very large crawls (millions of URLs)
  would need a different design. That is out of scope.
- Alternatives considered: Go or Rust for speed (rejected: ecosystem and
  rewrite cost); Postgres (rejected: needs a server; no multi-user need);
  Scrapy framework (rejected: heavy, opinionated, hard to type strictly, and
  we need tight control over politeness and rendering).
