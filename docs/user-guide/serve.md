# The web UI

```bash
uv run sitecrawler serve
```

`serve` opens the local web UI at `http://127.0.0.1:8765` in your browser.
It only ever listens on loopback and has no login: it is a tool for your
own machine, not a service. Stop it with Ctrl+C. To use the same UI in its
own window instead of a browser, see the [desktop app](desktop.md).

| Option | Meaning |
| --- | --- |
| `serve crawl.db` | Open a stored crawl read-only instead of starting empty |
| `--port 8765` | Listen on another port, still on 127.0.0.1 |
| `--no-open` | Print the URL instead of opening a browser |
| `--crawls-dir crawls` | Where crawls started from the UI are written |

## Crawling from the UI

Type a URL in the bar and press **Start**. Pages appear in the grid as they
are fetched, the counts in the tree and the filter dropdowns update, and
the audit re-runs every couple of seconds so the Issues tab and the
rule-backed filters fill while the crawl runs. **Pause** holds the crawl
after the fetches in flight; **Resume** continues it; **Stop** ends it
early; **Clear** forgets it and returns to an empty screen. **Settings**
holds the same options as the `crawl` command: max pages, delay, workers,
timeout, sitemaps, robots.txt, query strings, and **Render JavaScript**
(see [JavaScript rendering](render.md); greyed out when Playwright is not
installed). Its
**Save crawls to** field changes `--crawls-dir` for crawls started after
it: type a path and press Enter. Under `serve` the change lasts until the
server stops; the [desktop app](desktop.md) remembers it and adds a
**Browse…** button.

Each crawl is written to its own file, `crawls/<host>-<timestamp>.db`
under `--crawls-dir`, as it runs. When the crawl ends the final audit is
written there too, so the file is exactly what `sitecrawler crawl` plus
`sitecrawler audit` would have produced, and `export` works on it. A crawl
you stopped reads `stopped` in the file and can be continued from the
command line with `sitecrawler crawl URL --db FILE --resume`.

Starting a crawl while a stored file is open leaves that file untouched
and writes the new crawl to a new file.

## Browsing a stored crawl

```bash
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler serve example.db
```

A file that has not been audited is audited in memory when it opens, so
the Issues tab and the filters are always filled. Nothing is written back;
run `sitecrawler audit` to store the result in the file.

## The screen

One page, three panes:

- **Tabs and grid** in the middle. Each tab is a column set over the crawled
  pages; the dropdown beside it narrows the grid to one filter, and the
  search box matches any column. Click a URL to open its detail page.
  **Export CSV** writes the rows currently shown, filters applied. The
  **Custom** tab has one column per `--extract` and `--search` of the crawl
  (see [Custom extraction and search](extract.md)); Settings has **Extract**
  and **Search** boxes, one entry per line, for crawls started here.
- **Overview tree** on the right: every tab and filter with its count.
  Clicking a node selects that tab and filter. The summary above it shows
  pages, indexable, non-indexable and issue totals.
- **Detail pane** at the bottom. Click a row and the pane shows that URL:
  **URL Details** (response, timing, depth), **HTML** (title, metas,
  headings, canonical, robots), **Rendering** (raw HTML next to the
  rendered DOM, for a crawl run with Render JavaScript on), **Inlinks**,
  **Outlinks**, **Redirects**, **HTTP Headers**, **Hreflang** and **Issues**. A link in Inlinks or
  Outlinks selects that URL in turn; **Open full page** shows everything
  on one page you can bookmark.

The address bar keeps `#tab/filter`, so a view can be bookmarked.

## Tabs and filters

Filters that correspond to an [audit rule](rules.md) show exactly the URLs
that rule flagged, so their counts match `sitecrawler audit`. The others
are computed from the page itself.

| Tab | Filters |
| --- | --- |
| Internal | HTML, Other content, Indexable, Non-indexable |
| JavaScript | Rendered, Same as raw HTML, Changed by JavaScript, Render failed (crawls run with Render JavaScript) |
| External | Link targets on other hosts (not fetched); Only nofollow links |
| Response Codes | 2xx, 3xx, 4xx, 5xx, Blocked by robots.txt, No response, redirect chain / loop / to error / off-site / temporary |
| URL | Non-ASCII, Uppercase, Underscores, Parameters, Over 115 characters |
| Page Titles | Missing, Duplicate, Over 60 characters, Too short, Multiple, Same as H1 |
| Meta Description | Missing, Duplicate, Over 155 characters, Too short, Multiple |
| H1 | Missing, Multiple, Duplicate, Over 70 characters |
| H2 | Missing |
| Canonicals | Contains canonical, Self-referencing, Canonicalised, Missing, To non-200, Off-site, Chain, Conflicting, og:url mismatch, Canonicalised but linked |
| Pagination | Contains pagination, To non-200, Canonical to first page, Broken sequence |
| Directives | Index, Noindex, Follow, Nofollow, None, Conflicting, Noindex but linked, Blocked but linked |
| Hreflang | Contains hreflang, Invalid language code, Missing self reference, Missing x-default, Missing return link, To non-200, To non-canonical |
| Links | No inlinks, One follow inlink or none, More than 3 clicks deep, Unreachable from the start page, Links to errors, Links to redirects, Generic anchor text, Nofollow internal links, Has nofollow outlinks, Over 300 links |
| Sitemaps | In sitemap, Not in sitemap, Orphans (in sitemap, no inlinks), Non-indexable in sitemap, Noindex in sitemap, Indexable but not in sitemap, Listed more than once |
| Issues | One row per rule that fired, most severe first; click a row for its URLs, click the rule id for why it matters and how to fix it |

On Response Codes a redirected page counts under 3xx by the status of its
first hop; the `status_code` column still shows where the chain ended.

Grids are sortable (click a header) and filterable (type in the header
boxes). Everything the UI shows is also in the [exports](export.md).
