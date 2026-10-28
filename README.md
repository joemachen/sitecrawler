# sitecrawler

SEO site-audit crawler. Point it at a site, get every page, and every problem
ranked with what to do about it. It runs on your own machine; nothing is sent
anywhere but the site you crawl.

## Download (Windows)

**[Download sitecrawler.exe](https://github.com/joemachen/sitecrawler/releases/latest/download/sitecrawler.exe)**
from the [latest release](https://github.com/joemachen/sitecrawler/releases/latest).
It is one file with nothing to install: put it in a folder of its own,
double-click it, enter a URL and press **Start**. **Render JavaScript** uses
the Microsoft Edge that comes with Windows.

The exe is not code-signed, so the first time Windows SmartScreen may warn:
choose *More info*, then *Run anyway*. See [Desktop app](docs/user-guide/desktop.md).

## What it does

- **Crawls** a site from a start URL or a list of URLs, seeded from its XML
  sitemaps, respecting robots.txt, over HTTP/2. Every page goes into one
  SQLite file per crawl, and a stopped crawl can be resumed.
- **Renders JavaScript** in headless Chromium or Edge, and shows what
  scripts changed: title, canonical, meta tags, links.
- **Audits** with 72 rules across titles, meta descriptions, headings,
  canonicals, robots directives, indexability, hreflang, pagination,
  redirects, response codes, sitemaps, internal links, duplicate content,
  structured data and rendering. Each issue has a severity and a fix.
- **Analyses** internal linking (Link Score, click depth, anchor text),
  exact and near-duplicate content, structured data (JSON-LD, microdata,
  RDFa) against schema.org and Google's rich-result requirements, and the
  sitemaps against what was crawled.
- **Extracts** custom fields by CSS selector, XPath or regex, and searches
  pages for patterns.
- **Exports** to CSV, Excel or JSON, and writes XML sitemaps.
- **Shows it all** in a local web UI or the desktop app: one grid per tab,
  filters per issue, and a detail pane for each URL.

## Command line

With [uv](https://docs.astral.sh/uv/) and a checkout of this repository:

```bash
uv sync
uv run sitecrawler crawl https://example.com --db example.db   # crawl into a file
uv run sitecrawler audit example.db                            # run the rules, print the fix list
uv run sitecrawler issues example.db --rule title.missing      # the URLs behind one rule
uv run sitecrawler export example.db --format xlsx             # one sheet per table
uv run sitecrawler serve example.db                            # browse it at http://127.0.0.1:8765
```

`crawl --render` renders every page; `sitecrawler --help` lists every command.

## Documentation

User guide:
[crawling](docs/user-guide/crawl.md),
[JavaScript rendering](docs/user-guide/render.md),
[custom extraction](docs/user-guide/extract.md),
[storage](docs/user-guide/storage.md),
[list mode](docs/user-guide/list-mode.md),
[exporting](docs/user-guide/export.md),
[auditing](docs/user-guide/audit.md),
[every audit rule](docs/user-guide/rules.md),
[sitemaps](docs/user-guide/sitemaps.md),
[internal linking](docs/user-guide/links.md),
[duplicate content](docs/user-guide/duplicates.md),
[structured data](docs/user-guide/structured-data.md),
[the web UI](docs/user-guide/serve.md) and
[the desktop app](docs/user-guide/desktop.md).

Project:
[development process](docs/DEVELOPMENT.md),
[architecture](docs/ARCHITECTURE.md),
[roadmap](docs/ROADMAP.md),
[decisions](docs/adr/README.md) and
[changelog](CHANGELOG.md).

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
