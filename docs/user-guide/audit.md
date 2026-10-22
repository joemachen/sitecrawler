# Auditing a crawl

```bash
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler audit example.db
uv run sitecrawler issues example.db --rule response.4xx
```

`audit` runs every [rule](rules.md) over a stored crawl, writes the findings
to the `issues` table, records an indexability verdict on every page, and
prints the fix list: one row per rule that fired, most severe first, with the
number of URLs affected. It never touches the site; re-run it as often as you
like on the same file, including after upgrading sitecrawler, and the issues
table is rebuilt each time.

`issues` prints one line per finding to stdout, tab separated: severity, rule
id, URL and a detail such as the page that links to a broken URL. Filter to a
single rule with `--rule`. Pipe it where you like:

```bash
uv run sitecrawler issues example.db --rule response.4xx | cut -f3 > broken.txt
```

Both tables are also in the xlsx and json exports (`issues` sheet, and the
`indexable` / `indexability_reason` columns on `pages`).

On a crawl run with `--render`, `audit` also prints how many pages were
rendered, how many differ from their raw HTML (`render.differs`) and how
many the browser could not load (`render.failed`); see
[JavaScript rendering](render.md).

When the crawl read sitemaps, `audit` ends with one line on them: files
read, entries, and how many point at other hosts, were never crawled or are
listed twice; `sitecrawler sitemap report` has the detail and the four
`sitemap.*` rules are part of the fix list. See [Sitemaps](sitemaps.md).

## Indexability

Every page gets a verdict: indexable, or not indexable with the first reason
found in this order: blocked by robots.txt, redirect loop, fetch error, 4xx or
5xx status, a redirect, not HTML, `noindex` (meta robots or `X-Robots-Tag`),
or a canonical that points elsewhere (HTML `<link>` or `Link` header). The
verdict is a fact about the page, not an issue; the rules say whether it is a
problem.

## Severity

| Severity | Meaning |
| --- | --- |
| critical | Blocks indexing or breaks pages site-wide |
| high | Costs rankings on the affected pages |
| medium | Worth fixing in the next sprint |
| low | Hygiene |
| info | A fact to know, not a problem in itself |
