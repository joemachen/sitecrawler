# ADR-0006: Serve a crawl from an in-memory snapshot with client-side grids

**Status:** Accepted
**Date:** 2026-10-21

## Context

ADR-0002 fixed the stack for the Phase 3 web UI (FastAPI, Jinja2, HTMX,
Tabulator on 127.0.0.1). It left open how the app reads the crawl, where
sorting and filtering happen, and where the JavaScript comes from. The UI
serves a crawl that has already finished, on one developer's machine, with
no network guarantee, and must open in under a second (ARCHITECTURE §8).

## Decision

- `sitecrawler serve crawl.db` reads the whole crawl once into a
  `CrawlSnapshot` (the export tables from `store/dump.py`, a `CrawlView`
  for lookups, the rule metadata) and closes the SQLite file before the
  server starts. A new crawl or audit means restarting `serve`.
- Each grid is a Tabulator table fed from one JSON endpoint per table
  (`/api/pages`, ...). Sorting, filtering, searching and "Download CSV"
  happen in the browser on the full table; there is no server-side query
  layer.
- `htmx.min.js`, `tabulator.min.js` and `tabulator.min.css` are vendored
  under `src/sitecrawler/web/static/`, pinned by version, so the UI and its
  tests work offline. Upgrades are a commit that replaces the three files.
- Rule explanations are rendered in the app from the `Rule` classes
  (`/rules/<id>`), not linked into the generated MkDocs page, so the UI and
  the CLI show the same text from the same source.

## Consequences

- Easier: the web layer is a few hundred lines; the read side stays in the
  store module where exports already live; Windows never sees a locked
  file; a CSV export is exactly what the user filtered.
- Harder: memory grows with crawl size (a 10k-page crawl with 300k links is
  tens of MB, fine; a 100k-page crawl is not this tool's target); live
  refresh needs a restart; vendored files are large diffs when upgraded
  (`check-added-large-files` stays at 500 KB, Tabulator is 455 KB).
- Alternatives considered: server-side paging and filtering over SQLAlchemy
  (more code, slower to open, no gain at this scale); loading the libraries
  from a CDN (breaks offline and in CI); keeping the store open per request
  (locks the file on Windows, invites stale reads mid-audit).
