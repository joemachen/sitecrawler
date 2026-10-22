# Architecture

How sitecrawler is put together, and the rules that keep it that way. This is
the design we are building towards; the "Status" notes say what exists today.

---

## 1. Shape of the system

A crawl is a pipeline. Each stage is its own subpackage, and the only things
that pass between stages are typed records from `sitecrawler.models`.

```
                 ┌──────────────────────────────────────────────────────┐
                 │                      crawl/                          │
  start URL ──▶  │  Frontier ──▶ RobotsPolicy ──▶ Fetcher ──▶ Renderer │
  URL list  ──▶  │   (queue,       (allow?)       (httpx)    (Playwright,│
  sitemap   ──▶  │    seen)                                   optional) │
                 └───────────────────────┬──────────────────────────────┘
                                         │ FetchResult (bytes, status, headers, redirect hops)
                                         ▼
                 ┌──────────────────────────────────────────────────────┐
                 │                      parse/                          │
                 │  html ─ sitemap ─ structured_data ─ extraction        │
                 └───────────────────────┬──────────────────────────────┘
                                         │ ParsedPage (title, metas, headings, links, hreflang, ...)
                                         ▼
                 ┌──────────────────────────────────────────────────────┐
                 │                      store/                          │
                 │  SQLite, one file per crawl. Everything below reads  │
                 │  from here, never from the live site.                │
                 └──────┬──────────────────┬──────────────────┬─────────┘
                        ▼                  ▼                  ▼
                   analysis/           audit/             export/  web/
               link graph, Link    rules ──▶ issues      CSV, XLSX, JSON,
               Score, duplicates,                        browser tabs
               sitemap diff
```

**Status (after Phase 5):** `crawl/` (with the Playwright `Renderer`,
ADR-0008), `parse/`, `store/`, `export/`, `audit/` (53 rules), `cli/`,
`session.py` and `web/` exist. `session.py`
(`CrawlSession`, ADR-0007) runs a crawl on a worker thread with pause and
stop, audits it as pages arrive and writes the result to the file at the
end, or opens a finished file read-only into the same shape. `web/` is a
FastAPI app over a session: `tabs.py` declares the tab strip and each tab's
filters as data, `rows.py` turns page records into grid rows (base cells
once, audit cells per audit revision) and computes the summary counts,
`app.py` holds the routes; the one-page shell, templates and vendored
htmx/Tabulator sit beside them (ADR-0006 for the client-side grids).
`analysis/` is still an empty package.

---

## 2. Packages and their contracts

| Package | Owns | Must never |
| --- | --- | --- |
| `models` | Every dataclass that crosses a boundary (`CrawlConfig`, `QueueItem`, `FetchResult`, `ParsedPage`, `PageRecord`, later `Issue`, `Link`, ...). | Import from any other package. Do I/O. |
| `crawl` | Deciding what to fetch next, politeness (robots, delay, concurrency), fetching, JS rendering. | Parse HTML beyond handing text to `parse`. Know what an SEO issue is. |
| `parse` | Turning bytes into records: HTML, XML sitemaps, JSON-LD/microdata, custom extraction (XPath/CSS/regex). | Do network I/O. Decide whether something is a problem. |
| `store` | Persisting records to SQLite and querying them back. | Contain business rules. |
| `audit` | Rules: each takes records (or the store) and yields `Issue`s with severity, explanation and fix. | Fetch anything. |
| `analysis` | Whole-crawl computations: link graph and PageRank, duplicate clusters, sitemap-vs-crawl diff. | Fetch anything. |
| `export` | Writers: CSV, XLSX, JSON. | Compute anything new. |
| `integrations` | Enrichers that pull external data (GSC, GA4, PSI, backlink APIs) keyed by URL. | Be required for a crawl to work. |
| `session` | One crawl from Start to an audited file: runs `crawl` on a worker thread, feeds `store`, re-runs `audit`, serves the result to any thread (ADR-0007). | Render anything. Know about HTTP routes. |
| `web` | FastAPI app serving the local UI over a session. | Hold logic that the CLI can't also reach. |
| `cli` | Typer commands: parse args, build config, call library, print. | Contain logic. |

The dependency direction is strictly downward in this list: `cli` and `web`
may import anything; `models` imports nothing. Ruff's import rules plus code
review enforce this; if it ever becomes a problem, we add `import-linter`.

---

## 3. Core records

Today (`models.py`):

- `CrawlConfig`: immutable; every knob the CLI exposes.
- `QueueItem`: URL + depth + the page it was found on.
- `FetchResult`: status, final URL, content type, body text, timing, error.
- `ParsedPage`: title, meta description, first H1, canonical, links, word count.
- `PageRecord`: the CSV row; FetchResult + ParsedPage + provenance.

Planned additions (Phase 1-2) replace the flat `PageRecord` with a normalised
set of tables in SQLite:

| Table | Purpose |
| --- | --- |
| `crawls` | One row per run: start URL, config snapshot, timestamps, version. |
| `pages` | One row per requested URL: outcome, status, final URL, content type, size, timing, render mode, content hash, indexability verdict. |
| `redirect_hops` | Every hop in a chain: page_id, hop_no, from, to, status. Loops and chain length come from here. |
| `page_html` | Title, meta description, meta robots, X-Robots-Tag, canonical, all H1s/H2s (JSON), lang, word count. |
| `links` | Every anchor: src page, dst URL, anchor text, rel, nofollow, position (nav/body/footer), is_internal. |
| `hreflang` | page_id, lang, href. |
| `pagination` | page_id, rel (prev/next), href. |
| `structured_data` | page_id, format (jsonld/microdata/rdfa), type, raw JSON. |
| `extractions` | page_id, extractor name, value(s). Custom extraction output. |
| `sitemap_urls` | Every URL from every sitemap, with which sitemap it came from. |
| `issues` | page_id, rule_id, severity, message. Rebuilt whenever rules run. |

Exports and the web UI are views over these tables. Re-running `audit` on an
old crawl file is cheap and never re-fetches.

---

## 4. Concurrency and politeness

- One crawl = one process, one `asyncio` event loop. `workers` is the number
  of in-flight requests; `HostThrottle` (`crawl/throttle.py`) spaces requests
  to each host `delay_seconds` apart, so concurrency never raises the request
  rate above `1 / delay_seconds` per host.
- The fetcher is `httpx.AsyncClient` with HTTP/2 enabled and redirect
  following turned off: `Fetcher.fetch` walks the chain itself so every hop
  becomes data, and a revisited URL or a chain longer than `max_redirects`
  ends in `Outcome.REDIRECT_LOOP` after at most `max_redirects + 1` requests
  (ADR-0003). robots.txt and sitemaps go through the same fetcher and throttle.
- `Crawler.run()` is synchronous (it owns the loop); `Crawler.arun()` is the
  same crawl for callers that already have one. A `CrawlControl` carries
  pause and stop requests from any thread; the loop checks it between
  fetches and wakes every 250 ms while waiting, so a request is honoured
  promptly without the control needing a handle on the loop.
- JS rendering is a separate `Renderer` (`crawl/renderer.py`, Playwright's
  async API, one Chromium) with its own, lower concurrency (`render_workers`
  tabs; browser tabs are expensive). Pages are rendered only when `--render`
  is on; the raw HTML fetch still happens first so both versions can be
  compared, and the renderer shares the fetcher's per-host throttle
  (ADR-0008).
- robots.txt is honoured by default. `--ignore-robots` exists for auditing your
  own site and is logged loudly.

---

## 5. The issues engine (Phase 2)

```python
class Rule(Protocol):
    id: str  # "title.missing"
    severity: Severity  # CRITICAL / HIGH / MEDIUM / LOW / INFO
    category: str  # "Titles", "Redirects", "Canonicals", ...
    summary: str  # one line, shown in the Issues tab
    why: str  # a paragraph: why Google/users care
    fix: str  # what to do about it

    def check(self, page: PageView, crawl: CrawlView) -> Iterable[Issue]: ...
```

- Rules are discovered automatically from `audit/rules/` and run over the
  store. Site-wide rules (duplicate titles, orphan pages) get the whole
  `CrawlView`; page rules get one page at a time.
- Every rule has a fixture page that triggers it and one that doesn't.
- The user guide page for each rule is generated from the rule's own
  `summary`/`why`/`fix`, so docs cannot drift from behaviour.
- Severity ordering is what sorts the Issues tab. Counts per rule give the
  "fix list".

---

## 6. Extension points

| Want to add... | Do this | Nothing else changes |
| --- | --- | --- |
| A new audit check | Drop a `Rule` class in `audit/rules/`, add fixture page + test | ✔ |
| A new custom extractor syntax | Implement `Extractor` in `parse/extraction/` | ✔ |
| A new export format | Implement `Writer` in `export/` | ✔ |
| An external data source | Implement `Enricher` in `integrations/`; it receives URLs, returns columns | ✔ |
| A new UI tab or filter | Add a `TabSpec` / `FilterSpec` in `web/tabs.py`; a new column is one key in `rows.base_row` | ✔ |

---

## 7. Error handling philosophy

- A crawl never dies because one page is weird. Every per-URL failure becomes
  a row with an `outcome` and `error` text.
- Parsers are total functions: garbage in, empty record out, never an exception
  past the package boundary.
- Only configuration mistakes (bad URL, unwritable output path) raise, and they
  raise before any request is made.

---

## 8. Performance targets

| Metric | Target |
| --- | --- |
| Raw crawl throughput | Bounded by `delay`, not by CPU; 10k pages at 0.2 s delay ≈ 35 min |
| Memory | O(pages) for the seen-set only; bodies are not kept in memory once stored |
| Re-running audit rules on a stored 10k-page crawl | < 10 s |
| Opening the web UI on a stored crawl | < 1 s |

---

## 9. Things we deliberately don't do

- No distributed crawling, no queues, no database server. One machine, one
  SQLite file. If that ever limits us, that is a good problem to have.
- No scraping of content behind logins.
- No bypassing of bot protection. If a site blocks us, we report it.
