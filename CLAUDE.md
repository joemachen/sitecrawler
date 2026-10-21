# sitecrawler

SEO site-audit crawler. Python 3.13, `src/` layout, managed with uv.

## Commands

```bash
uv sync                              # install everything into .venv
uv run playwright install chromium   # once; headless browser for tests/e2e/test_web_ui.py
uv run sitecrawler crawl URL -o out.csv
uv run sitecrawler crawl URL --db crawl.db && uv run sitecrawler audit crawl.db
uv run sitecrawler serve crawl.db    # local web UI on http://127.0.0.1:8765
uv run ruff format . && uv run ruff check --fix .
uv run mypy
uv run pytest                        # unit + integration + e2e, all offline
uv run pytest tests/unit             # fast loop
uv run mkdocs serve                  # docs at http://127.0.0.1:8000
uv run pre-commit run --all-files
```

## Layout

- `src/sitecrawler/cli/` thin Typer commands; no logic.
- `src/sitecrawler/crawl/` frontier, robots, fetcher. Never parses HTML.
- `src/sitecrawler/parse/` HTML/XML to typed records. Never does I/O.
- `src/sitecrawler/audit/` rules turning records into issues.
- `src/sitecrawler/analysis/` link graph, duplicates, sitemap diff.
- `src/sitecrawler/store/` SQLite persistence.
- `src/sitecrawler/export/` CSV/XLSX/JSON writers.
- `src/sitecrawler/web/` FastAPI app, Jinja2 templates and vendored htmx/Tabulator over one stored crawl (`serve`). Never holds logic the CLI cannot reach.
- `tests/fixtures/site/` static site every rule must have a trigger page in.

## Conventions

- mypy strict; no untyped defs, no bare `Any` without a comment.
- Dataclasses/pydantic for anything crossing a module boundary.
- Google-style docstrings on public API.
- Conventional Commits: `feat(scope): ...`, `fix(scope): ...`.
- New audit rule = fixture page that triggers it + unit test + user-guide entry.
- Never commit crawl output, `.env`, or `*.db`.
- Non-trivial design choices get an ADR in `docs/adr/`.

Process details: `docs/DEVELOPMENT.md`. Design: `docs/ARCHITECTURE.md`. Plan: `docs/ROADMAP.md`.
