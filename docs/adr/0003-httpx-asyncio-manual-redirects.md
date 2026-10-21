# ADR-0003: httpx + asyncio, with redirects followed by hand

**Status:** Accepted
**Date:** 2026-10-21

## Context

Phase 0 fetched with `requests` in a thread pool and let the library follow
redirects. That lost the information Phase 2's redirect rules need (chain
length, each hop's status, loops), turned a redirect loop into a 30-request
timeout, and throttled globally rather than per host. ADR-0001 already named
httpx as the HTTP library; this records how it is used.

## Decision

- **`httpx.AsyncClient` on `asyncio`**, with `http2=True` (the `h2` extra is a
  hard dependency). One event loop per crawl; `workers` is the number of
  in-flight requests, not threads. `Crawler.run()` owns the loop and
  `Crawler.arun()` exists for callers that already have one.
- **Redirects are followed by the fetcher, not the client**
  (`follow_redirects=False`). Each 301/302/303/307/308 with a `Location`
  becomes a `RedirectHop(hop_no, from_url, to_url, status_code)` on the
  `FetchResult`. The walk stops with `Outcome.REDIRECT_LOOP` as soon as a URL
  repeats, or once the chain exceeds `max_redirects` (default 10). One outcome
  covers both cases; the `error` text and the hop list tell them apart.
- **Per-host throttle.** `HostThrottle.acquire(host)` is awaited before every
  request, including each redirect hop, robots.txt and sitemaps. Different
  hosts never wait on each other (list mode will crawl several).
- **`redirect_loop` is a new value in the CSV `status` column.** `error`
  keeps meaning "network or protocol failure".

## Consequences

- Easier: redirect audits are a query over `redirect_hops`; loops cost two
  requests; per-host politeness is correct for multi-host lists; HTTP/2
  multiplexing on sites that support it; `respx` makes fetcher unit tests
  cheap and offline.
- Harder: everything in `crawl/` is `async`, so library callers use `run()`
  or must already have a loop; `requests`-style sync hooks are gone. Bodies
  are decoded as UTF-8 when no charset is declared (httpx default) where
  `requests` assumed ISO-8859-1; this is the better default for modern sites.
- Alternatives considered: `follow_redirects=True` and reading
  `response.history` (loses the loop and over-length cases, which raise
  instead of returning data); `aiohttp` (no HTTP/2, weaker typing); keeping
  threads (works, but per-host throttling and thousands of in-flight URLs are
  awkward, and Playwright in Phase 4 is async anyway).
