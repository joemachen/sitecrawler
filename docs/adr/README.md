# Architecture Decision Records

One short file per decision that would be hard to reverse or surprising to a
newcomer. Copy `0000-template.md`, number it, fill it in, link it from the PR.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-python-uv-sqlite-stack.md) | Python, uv, SQLite as the core stack | Accepted |
| [0002](0002-cli-first-web-ui-later.md) | CLI first, local web UI from Phase 3 | Accepted |
| [0003](0003-httpx-asyncio-manual-redirects.md) | httpx + asyncio, redirects followed by hand | Accepted |
| [0004](0004-one-crawl-per-file-and-resume.md) | One crawl per SQLite file, resumed from pending rows | Accepted |
| [0005](0005-rules-as-code-and-docs.md) | Audit rules as discovered classes; docs generated from them | Accepted |
| [0006](0006-web-ui-snapshot-and-client-grids.md) | Web UI serves an in-memory snapshot; grids filter client-side; assets vendored | Accepted |
| [0007](0007-live-crawl-session.md) | The crawl runs inside `serve` as a session on its own thread; the browser polls | Accepted |
| [0008](0008-render-every-page-and-keep-the-diff.md) | `--render` renders every HTML page in one Chromium; rendered fields become the page, the diff is stored, not the DOM | Accepted |
| [0009](0009-extract-in-the-crawl-pass.md) | Custom extractors and searches run in the crawl pass over the HTML in hand; bodies stay unstored; lxml + cssselect replace BeautifulSoup | Accepted |
| [0010](0010-sitemap-audit-as-page-rules.md) | Sitemap findings are page rules over the normalised entries and the indexability verdict; file-level facts are a report; generation is an export with `lastmod` only on request | Accepted |
| [0011](0011-link-graph-in-the-audit-index.md) | The link graph is part of the audit index (`audit/graph.py`); Link Score is log-scaled PageRank over the follow graph with redirects resolved; `audit` stores inlinks, click depth and score on `pages` | Accepted |
| [0012](0012-content-fingerprints-in-the-crawl-pass.md) | Content hash and SimHash are computed in the crawl pass over the main text (boilerplate stripped) and stored on `page_html`; clustering is an audit index (`audit/duplicates.py`); the content rules flag indexable members only | Accepted |

Statuses: Proposed, Accepted, Superseded by ####, Deprecated.
