# ADR-0008: Render every HTML page in one headless Chromium, keep the diff, not the DOM

**Status:** Accepted
**Date:** 2026-10-21

## Context

Phase 5 adds `--render`: load pages in headless Chromium so the audit sees
what a browser builds, and report how that differs from the HTML the
server sent. Three questions had no obvious answer: which pages to render,
what the stored page should be once two versions exist, and how much to
keep. Playwright was already a dev dependency for the UI tests, with the
known gotcha that its sync API owns an asyncio loop and cannot run inside
the crawl loop.

## Decision

- **Render every parsable HTML page**, not only pages that look
  JavaScript-dependent. The point of the feature is the comparison, and
  "looks JS-dependent" (a `<script>` tag, a framework root element, a thin
  body) is a heuristic that would hide exactly the pages worth seeing: a
  normal-looking page whose canonical a tag manager rewrites. The raw fetch
  still happens first, through httpx, so robots, redirects, headers and
  status codes are unchanged and non-HTML or failed pages are never
  rendered.
- **The rendered fields become the page's fields.** When a render succeeds
  the record's title, metas, canonical, links and word count are the
  rendered ones (what Google indexes), rendered-only links feed the
  frontier, and a `RenderDiff` keeps the raw values beside them. When a
  render fails the raw parse is kept and the error recorded, so a crawl
  never loses a page to a slow script. Rules, exports and the UI therefore
  need no second code path; two new rules (`render.differs`,
  `render.failed`) read the diff and the error.
- **Store the diff, not the two documents.** `page_render` holds both
  values of each compared field and the link sets that differ. Storing raw
  and rendered HTML for every page would multiply file size by the page
  weight for a comparison that is already computed; it can be added later
  behind a flag if custom extraction (Phase 6) wants the rendered DOM back.
- **One browser, `render_workers` tabs, Playwright's async API.** The
  `Renderer` lives in `crawl/`, is entered with the fetcher in
  `Crawler.arun`, launches one Chromium, opens at most `render_workers`
  (default 2) tabs through a semaphore, blocks images, fonts and media, and
  shares the fetcher's per-host throttle. It uses the async API because the
  crawl loop is an asyncio loop; the sync API would try to start another.
- **Playwright is an optional extra** (`sitecrawler[render]`) and imported
  lazily. A plain crawl never needs a browser; `--render` without Playwright
  or Chromium fails before the first request with the install commands.

## Consequences

- Easier: one page record shape everywhere; the fixture site's JS page
  tests the whole path (crawl, store, audit, UI) with one flag; a rendered
  crawl is just a slower crawl, with the same resume, pause and stop.
- Harder: `--render` costs a browser load per page (roughly 10× the time of
  a fetch, bounded by `render_workers`); `networkidle` never fires on pages
  that poll, so `--render-wait` and `--render-timeout` exist and a timeout is
  a reported failure, not a crash. The raw HTML of a rendered page is not in
  the file, only what the parser extracted from it.
- Alternatives considered: render only pages with a framework marker
  (misses the interesting cases, see above); keep raw as the page and store
  rendered as a sidecar (every rule would need to choose a side, and the
  default would be the one Google does not use); one browser context per
  page (slow to start, nothing shared); storing both HTML bodies (file size,
  and nothing reads them yet); a separate `render` command over a stored
  crawl (would re-fetch what the crawl already fetched, and the frontier
  could not follow rendered-only links).
