# Sitemaps

```bash
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler audit example.db                 # sitemap rules are part of the audit
uv run sitecrawler issues example.db --rule sitemap.orphan
uv run sitecrawler sitemap report example.db        # the sitemap files themselves
uv run sitecrawler sitemap generate example.db      # write sitemap.xml from the crawl
```

A crawl reads every sitemap the site declares and keeps what it found. The
audit then compares the sitemaps with the pages the crawl fetched: pages the
sitemap lists but the site never links to, entries that cannot be indexed,
indexable pages the sitemap forgot, and pages listed twice. `sitemap report`
prints the facts about the files, and `sitemap generate` writes a sitemap
that matches the crawl.

## What the crawl reads

1. The `Sitemap:` lines in `robots.txt`. If there are none, `/sitemap.xml`
   is tried instead.
2. Every sitemap index is followed, to any depth; a file listed twice is
   read once.
3. Gzip-compressed files (`sitemap.xml.gz`, or a plain `.xml` served with
   `Content-Encoding: gzip`) are decompressed. Files that omit the
   sitemaps.org namespace still parse.
4. Each entry's `<loc>`, `<lastmod>`, `<changefreq>` and `<priority>` are
   stored in `sitemap_urls` with the file they came from; each file tried is
   stored in `sitemaps` with its status and, when it could not be used, why
   (`status 404`, `not sitemap XML`, `fetch error: ...`).
5. Entries on the crawled site are queued at depth 0 with
   `found_on = sitemap:<file>`. Entries on other hosts are stored but never
   fetched.

`--no-sitemap` skips all of this; the sitemap rules then stay silent and
`sitemap report` says so. List mode never reads sitemaps.

## The rules

| Rule | Severity | Fires on |
| --- | --- | --- |
| `sitemap.orphan` | medium | An indexable page a sitemap lists and no other page links to (self-links do not count; the start URL is never an orphan). |
| `sitemap.non_indexable` | medium | A listed page whose [indexability verdict](audit.md#indexability) is not indexable: redirect, error, blocked by robots.txt, noindex, canonicalised elsewhere. The message says which. |
| `sitemap.missing` | low | An indexable 200 page no sitemap lists. Silent when the crawl read no sitemap, so a site without one gets one line in `sitemap report`, not one issue per page. |
| `sitemap.duplicate` | low | A page listed more than once: in two files, twice in one, or as two spellings (`/a` and `/a/`) that the crawl treats as one page. |

`robots.noindex_in_sitemap` (the noindex case, with its more specific fix)
still fires alongside `sitemap.non_indexable`, the way the informational
roll-ups overlap with their specific rules; count by the highest severity.

Sitemap URLs are matched to pages the way links are: trailing slashes,
`www.` and fragments are ignored, and query strings follow the crawl's
`--keep-query` setting.

In the web UI the **Sitemaps** tab has a filter per rule plus *In sitemap*
and *Not in sitemap*; the URL Details pane shows which files list a page and
their `lastmod`.

## `sitemap report`

Prints one row per sitemap file the crawl tried (where it was found, its
kind, status, how many entries, and the problem if any), then one line per
entry that matches no page:

```text
other host    https://cdn.example.net/x    https://example.com/sitemap.xml
not crawled   https://example.com/a.pdf    https://example.com/sitemap.xml
duplicate     https://example.com/about    https://example.com/sitemap.xml, https://example.com/sitemap-2.xml
```

`other host` entries were never fetched. `not crawled` entries are on the
site but have no page row: the crawl hit `--max-pages` first, or the URL
does not look like a page (a PDF, an image). The same summary appears as
one line at the end of `sitecrawler audit`.

## `sitemap generate`

```bash
uv run sitecrawler sitemap generate example.db                 # sitemap.xml next to the DB
uv run sitecrawler sitemap generate example.db -o out/sitemap.xml --lastmod
uv run sitecrawler sitemap generate example.db --base-url https://example.com/
```

Writes every page whose status is 200 and whose indexability verdict is
indexable, in URL order, as a sitemaps.org `urlset`. The verdict is computed
from the stored crawl, so `audit` need not have run first. Over 50,000 URLs
the output becomes a sitemap index pointing at `sitemap-1.xml`,
`sitemap-2.xml`, ... in the same directory, named under `--base-url` (the
crawl's start URL origin by default).

| Flag | Default | Purpose |
| --- | --- | --- |
| `-o, --output` | `sitemap.xml` beside the DB | File to write; parts and the index take its directory and stem |
| `--lastmod` | off | Add `<lastmod>` from each page's `Last-Modified` response header, as a W3C datetime. Pages without the header get no `lastmod`. |
| `--base-url` | start URL origin | Where the files will be served from; only the index form needs it |

`changefreq` and `priority` are never written: search engines ignore them.
`lastmod` is off by default because a server's `Last-Modified` is often the
response time of a dynamic page, and a sitemap whose dates are wrong is
trusted less than one with none (ADR-0010).

The output validates against the sitemaps.org schemas;
`tests/unit/test_sitemap_export.py` checks it against the XSD files vendored
under `tests/fixtures/schemas/`.
