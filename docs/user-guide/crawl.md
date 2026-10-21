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
| `-o, --output` | `pages.csv` | Output file |
| `--max-pages` | 5000 | Stop after this many pages |
| `--delay` | 0.5 | Minimum seconds between requests to the same host, shared across workers |
| `--workers` | 4 | Concurrent fetchers |
| `--timeout` | 20 | Per-request timeout in seconds |
| `--max-redirects` | 10 | Give up on a redirect chain longer than this and report `redirect_loop` |
| `--no-http2` | off | Use HTTP/1.1 only. By default HTTP/2 is negotiated when an HTTPS server offers it |
| `--no-sitemap` | off | Discover only by following links |
| `--keep-query` | off | Treat different query strings as different pages (tracking parameters are still dropped) |
| `--ignore-robots` | off | Crawl pages robots.txt disallows. Use only on sites you own. |
| `-v, --verbose` | off | Debug logging |

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

## Redirects

Redirects are followed one hop at a time, and every hop is kept (status code,
from, to). The CSV shows only the end of the chain; the full chain is kept on
each record for the SQLite store and the redirect audits in later phases. A
chain that returns to a URL it already visited stops immediately, so a loop
costs two requests rather than a timeout.
