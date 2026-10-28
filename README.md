# sitecrawler

SEO site-audit crawler. Point it at a site, get every page, and (soon) every
problem ranked with a fix.

```bash
uv sync
uv run sitecrawler crawl https://example.com -o pages.csv
```

On Windows there is also a standalone desktop app with nothing to install:
download `sitecrawler.exe` from the [latest release](https://github.com/joemachen/sitecrawler/releases/latest), or build it
with `uv run pyinstaller --noconfirm packaging/sitecrawler.spec` (see
[Desktop app](docs/user-guide/desktop.md)).

## Status

Phase 0 of the [roadmap](docs/ROADMAP.md): the crawler inventories a site to
CSV with status codes, titles, meta descriptions, H1s, canonicals, depth and
link counts. Audit rules, storage, JS rendering and the web UI follow in later
phases.

## Documentation

- [Crawling a site](docs/user-guide/crawl.md): command, flags, CSV columns.
- [Desktop app](docs/user-guide/desktop.md): the standalone exe and how to build it.
- [Development process](docs/DEVELOPMENT.md): setup, tooling, workflow, definition of done.
- [Architecture](docs/ARCHITECTURE.md): how the pieces fit and the rules that keep them apart.
- [Roadmap](docs/ROADMAP.md): phases, deliverables, acceptance criteria.
- [Decisions](docs/adr/README.md): why things are the way they are.

Render the docs site locally with `uv run mkdocs serve`.

## Development

```bash
uv sync                      # install everything
uv run pre-commit install    # hooks: ruff, mypy, unit tests on every commit
uv run pytest                # full suite, fully offline
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
