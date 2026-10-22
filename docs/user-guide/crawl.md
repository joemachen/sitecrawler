# Crawling a site

```bash
uv run sitecrawler crawl https://example.com -o pages.csv
```

The crawler:

1. Fetches `robots.txt` and honours its `Disallow` rules.
2. Seeds its queue from the site's sitemap(s), including sitemap indexes.
3. Follows every internal link breadth-first until nothing is left or `--max-pages` is hit.
4. Skips other hosts, non-HTML files (images, PDFs, CSS, JS), and `mailto:`/`tel:` links.
5. Writes one row per URL, sorted alphabetically.

`www.example.com` and `example.com` count as the same site. Query strings are
stripped by default so `/faq?faq=shipping` and `/faq` are one page.

## Options

| Flag | Default | Purpose |
| --- | --- | --- |
| `-o, --output` | `pages.csv` | CSV to write. With `--db` the default is no CSV; pass `-o` to get one as well |
| `--db` | off | SQLite file to store the crawl in. One crawl per file; see [Storage](storage.md) |
| `--resume` | off | Continue the crawl already in `--db` from where it stopped |
| `--max-pages` | 5000 | Stop after this many pages |
| `--delay` | 0.5 | Minimum seconds between requests to the same host, shared across workers |
| `--workers` | 4 | Concurrent fetchers |
| `--timeout` | 20 | Per-request timeout in seconds |
| `--max-redirects` | 10 | Give up on a redirect chain longer than this and report `redirect_loop` |
| `--no-http2` | off | Use HTTP/1.1 only. By default HTTP/2 is negotiated when an HTTPS server offers it |
| `--no-sitemap` | off | Discover only by following links |
| `--keep-query` | off | Treat different query strings as different pages (tracking parameters are still dropped) |
| `--ignore-robots` | off | Crawl pages robots.txt disallows. Use only on sites you own. |
| `--render` | off | Also load every HTML page in headless Chromium and parse the rendered DOM; see [JavaScript rendering](render.md) for `--render-workers`, `--render-wait`, `--render-selector` and `--render-timeout` |
| `--extract` | none | Custom extractor `NAME=css:SELECTOR`, `NAME=xpath:EXPR` or `NAME=regex:PATTERN`, repeatable; see [Custom extraction and search](extract.md) for modifiers and `--extract-file` |
| `--search` | none | Flag pages whose HTML matches a regex (case-insensitive), `[NAME=]PATTERN`, repeatable; see [Custom extraction and search](extract.md) |
| `-v, --verbose` | off | Debug logging |

To fetch a fixed set of URLs instead, see [List mode](list-mode.md).

## Storing the crawl

```bash
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler crawl https://example.com --db example.db --resume   # after a crash or Ctrl-C
```

With `--db` every page is written to the SQLite file as soon as it is fetched,
so nothing is lost if the crawl stops early. A file holds one crawl: running
`crawl` again on an existing file is refused unless you pass `--resume`, which
carries on from the queued URLs without re-fetching finished pages (`max-pages`
counts across both runs). The start URL must match the stored crawl.

Progress goes to stderr, so it can be captured separately:

```bash
uv run sitecrawler crawl https://example.com -o pages.csv 2> crawl.log
```

## CSV columns

| Column | Meaning |
| --- | --- |
| `url` | Normalised URL that was requested |
| `status` | HTTP status code, or `blocked` (robots.txt) / `error` (network failure) / `redirect_loop` (redirects never resolved: a cycle, or more than `--max-redirects` hops) |
| `title` | `<title>` text |
| `meta_description` | `<meta name="description">` content |
| `h1` | First `<h1>` on the page |
| `canonical` | `<link rel="canonical">` href, or the final URL if the request redirected |
| `content_type` | Response MIME type |
| `depth` | Link hops from the start URL along the path that first discovered the page. Sitemap URLs are depth 0. With several workers this can differ from the shortest path by a hop or two; exact shortest-path depth comes with the link-graph phase. |
| `found_on` | Page (or `sitemap:URL`) where this URL was first discovered |
| `internal_links` | Count of distinct same-site hrefs on the page |
| `word_count` | Visible words, with scripts and styles removed |
| `fetch_ms` | Request time in milliseconds, including redirects |
| `error` | Error detail, if any. For `redirect_loop` this is the chain, e.g. `redirect loop: /a -> /b -> /a` |
| `render_changes` | With `--render`: what JavaScript changed (`title, canonical, links +3`), or why the page could not be rendered. Empty otherwise |
| `extract_<name>`, `search_<name>` | One column per `--extract` and `--search`, after the fixed columns: the extracted value (matches joined with ` \| `), or `True`/`False` for a search. Empty on pages that are not HTML |

## Redirects

Redirects are followed one hop at a time, and every hop is kept (status code,
from, to). The CSV shows only the end of the chain; the full chain is kept on
each record for the SQLite store and the redirect audits in later phases. A
chain that returns to a URL it already visited stops immediately, so a loop
costs two requests rather than a timeout.
