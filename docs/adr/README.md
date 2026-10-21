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

Statuses: Proposed, Accepted, Superseded by ####, Deprecated.
