# JavaScript rendering

```bash
uv run sitecrawler crawl https://example.com --db example.db --render
uv run sitecrawler audit example.db
uv run sitecrawler issues example.db --rule render.differs
```

By default the crawler reads the HTML the server sends. Sites built with
React, Vue, Angular or a tag manager often inject the title, the canonical,
meta tags or whole navigation menus from JavaScript, so that HTML is not
what a browser (or Google's renderer) ends up with. `--render` loads every
HTML page in headless Chromium as well, after the normal fetch, and parses
the rendered DOM.

With `--render` on:

- The page's title, meta tags, headings, canonical, links and word count
  come from the rendered DOM, so audit rules, exports and the web UI see
  what a browser sees. Links that only exist after rendering are crawled.
- Each page also keeps a **rendered-vs-raw diff**: title, meta description,
  meta robots, canonical, H1, word count and link count on both sides, plus
  the links that exist only after rendering (or only before). Word counts
  are reported but never counted as a change; scripts add and remove a few
  words on almost every page.
- Two audit rules read the diff: `render.differs` (medium) lists pages
  where JavaScript changes the title, canonical, meta or links, with the
  changed fields in the message, and `render.failed` (low) lists pages the
  browser could not deliver: a timeout, an HTTP error on the browser's
  request (a site that throttles repeat visits), a response the browser
  treats as a download, or a script that sends the browser to another site.
  A failed page keeps its raw HTML fields. `sitecrawler audit` also prints
  one line with how many pages rendered, differed and failed.
- Pages that are not parsable HTML (errors, 4xx and 5xx, redirects to other
  pages, non-HTML files) are never rendered.

The web UI has the same switch under **Settings → Render JavaScript**, a
**JavaScript** tab (Rendered, Same as raw HTML, Changed by JavaScript,
Render failed) and a **Rendering** section in the detail pane showing the
raw and rendered values side by side. Exports carry `render_status`
(`rendered`, `failed` or empty) and `render_changes` on every page row.

## Installing the browser

Rendering needs Playwright and its Chromium build, which are not part of a
plain install:

```bash
uv sync --extra render            # or: pip install "sitecrawler[render]"
uv run playwright install chromium
```

Without them `--render` exits with status 2 and this hint before any
request is made. Developers get Playwright through the dev dependencies
already.

## Options

| Flag | Default | Purpose |
| --- | --- | --- |
| `--render` | off | Render every HTML page in headless Chromium after the raw fetch |
| `--render-workers` | 2 | Browser tabs open at once. Separate from `--workers`; tabs cost far more than requests |
| `--render-wait` | `networkidle` | When a page counts as loaded: `load` (the load event), `domcontentloaded`, or `networkidle` (no network traffic for 500 ms). Pages that never stop polling need `load` |
| `--render-selector` | none | CSS selector to wait for after the page loads, for apps that fetch their content and then render it, e.g. `--render-selector "#app h1"` |
| `--render-timeout` | 30 | Seconds before a render is given up. The page keeps its raw HTML fields and is listed under `render.failed` |

Images, fonts and media are never requested by the browser, which keeps a
render to a fraction of a second on most pages. Per-host politeness is
shared with the HTTP fetcher: a navigation waits for the same `--delay` as
a request would.

## Reading the diff

The sites that matter are the ones where the two columns disagree on
something a search engine uses:

| Change | What it usually means |
| --- | --- |
| Title or meta description only after rendering | A framework sets `document.title` at runtime. Google may index the page before its renderer runs, with no title |
| Canonical only after rendering | A canonical injected by a tag manager or an SPA router; treated as absent by anything that does not run JavaScript, and often wrong when it is read |
| Meta robots changes | A script adds or removes `noindex`; the raw and rendered pages disagree on whether the page should be indexed at all |
| Links only after rendering | Navigation, pagination or product grids built client-side. Crawlers that do not render never find those pages, and the ones that do spend crawl budget on rendering |
| Links only before rendering | A script removed or rewrote links, for example a menu replaced by a JavaScript widget without `href`s |

A page that renders the same as its raw HTML is the healthy case: the
JavaScript may still do plenty, but nothing a crawler needs depends on it.
