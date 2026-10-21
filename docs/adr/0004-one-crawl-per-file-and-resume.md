# ADR-0004: One crawl per SQLite file, resumed from pending rows

**Status:** Accepted
**Date:** 2026-10-21

## Context

ADR-0001 chose SQLite via SQLAlchemy. Phase 1 adds the store, and two
questions shape its API: does a file hold one crawl or many, and how does a
crawl resume after a crash. The crawler must also stay ignorant of the store
(ARCHITECTURE section 2: `crawl` never imports `store`).

## Decision

- **One crawl per file.** `Store.begin()` refuses a file that already holds a
  crawl unless `resume=True`, and refuses to resume a crawl whose start URL
  differs. No table carries a crawl id in its public query surface and no
  method takes one. The file *is* the crawl.
- **The `pages` table is the frontier.** Every URL the frontier accepts is
  inserted as `state='pending'` in the same transaction as the page that
  discovered it; fetching it flips the row to `done`. Resume reloads the
  `pending` rows as the queue and every URL as the seen set, skips sitemap
  seeding, reloads robots.txt and keeps counting `max_pages` from
  `crawls.pages_done`. A page in flight at the crash stays `pending` and is
  fetched again, which is the correct outcome.
- **A sink protocol, not a store import.** `crawl/sink.py` declares
  `CrawlSink` with `begin`, `seeded`, `page_done` and `finish`; `Store`
  satisfies it structurally. Each `page_done` call is one transaction
  holding the page, its hops, HTML fields, links and the newly queued URLs.
- **Synchronous SQLAlchemy inside the event loop.** A per-page commit on
  SQLite takes about a millisecond, far below any fetch, so an async driver
  would add a dependency for nothing.
- **No migrations during `0.x`.** `crawls.version` records the writer; an
  old file is re-crawled rather than upgraded.
- **Raw HTML is not stored yet.** It arrives with rendering in Phase 4, when
  raw and rendered documents are stored side by side.

## Consequences

- Easier: no `crawl_id` plumbing anywhere; a crash loses at most the page in
  flight; "email me the crawl" is one file; the CSV export after a resume is
  correct because it reads from the store, not from memory.
- Harder: comparing two crawls of the same site means two files and a join
  across attached databases (Phase "crawl diff", parked). WAL leaves side
  files while the database is open, which surprises people on first sight.
- Alternatives considered: many crawls per file with a `crawl_id` everywhere
  (more flexible, but every query and every export needs the filter, and the
  roadmap's crawl-to-crawl diff is easier with two files); a separate
  `frontier` table (duplicates `pages`); writing records only at the end
  (loses everything on a crash, which is the case resume exists for).
