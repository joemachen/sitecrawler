# ADR-0007: Run the crawl inside `serve` as a session that the browser polls

**Status:** Accepted
**Date:** 2026-10-21

## Context

Phase 4 turns the web UI into a Screaming-Frog-style app: a URL bar, Start,
Pause and Stop, and rows that appear while the crawl runs. ADR-0006 built the
UI over a snapshot of a finished file, read once and closed; a new crawl
meant restarting `serve`. The crawler had no way to be paused or stopped,
the audit runs over a whole crawl, and on Windows an open SQLite file cannot
be read by a second connection without care.

## Decision

- **`CrawlControl`** (`crawl/control.py`): two `threading.Event`s, pause and
  stop, that the crawl loop checks between fetches. The loop wakes every
  250 ms while waiting on fetches so a request is seen promptly. A stopped
  crawl cancels its in-flight fetches and tells the sink it is incomplete,
  so `crawls.status` is `stopped` and the file can be resumed by the CLI.
- **`CrawlSession`** (`session.py`, a top-level module because it joins
  `crawl`, `store` and `audit`) owns one crawl: it runs the `Crawler` in a
  worker thread with its own event loop, wraps the `Store` in a sink that
  also appends each record to an in-memory list, and keeps the file open
  only on that thread. An audit thread re-runs every rule over a copy of the
  records whenever pages have arrived and at least `max(2 s, 3 × last run)`
  has passed, publishing a numbered revision. When the loop ends the session
  runs the audit once more, writes issues and verdicts to the file, closes
  it, and only then reports `done`, `stopped` or `error`.
- The session can also **open a finished file read-only**, producing the
  same in-memory shape, so the UI has one read path for a stored crawl and
  a live one. New crawls go to `crawls/<host>-<timestamp>.db`.
- The browser **polls** JSON endpoints (status every second, then only the
  rows and audit cells that changed) instead of a websocket or server-sent
  events. No new dependency, works through FastAPI's test client, and a
  local tool never has more than one viewer.

## Consequences

- Easier: `serve` with no file is an empty session ready to crawl; the CLI
  keeps the same `Crawler` and `Store` and gains pause/stop for free; tests
  drive a session with a fake runner and no network.
- Harder: three threads touch one object (server, crawl, audit); one lock
  and copy-on-read keep it simple but every new field must go under it. The
  mid-crawl audit costs CPU on big crawls, bounded by the adaptive gap. A
  crawl stopped by the user and one capped by `max_pages` both read
  `stopped` in the file.
- Superseded from ADR-0006: "a new crawl or audit means restarting `serve`".
  The rest of ADR-0006 (client-side grids, vendored assets, rule pages in
  the app) stands.
- Alternatives considered: running the crawl on uvicorn's own loop (a slow
  SQLite write would stall every request, and `Crawler.run` could not be
  reused); websockets or SSE (a dependency and harder to test, for one
  viewer); reading the live file from the server thread (Windows locking,
  and audit rules want the whole crawl in memory anyway); auditing only at
  the end (filters and counts would stay empty during a long crawl).
