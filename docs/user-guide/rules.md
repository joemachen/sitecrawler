# Audit rules

Every check `sitecrawler audit` runs, generated from the rule classes in
`src/sitecrawler/audit/rules/` by `uv run python scripts/gen_rule_docs.py`.
Do not edit by hand.

Severity: **critical** blocks indexing or breaks pages site-wide, **high** costs
rankings on affected pages, **medium** is worth fixing in the next sprint,
**low** is hygiene, **info** is a fact to know rather than a problem.

## Response codes

### `response.4xx`

**Page returns a 4xx client error** (severity: high)

A 4xx page is a dead end for users and gets dropped from the index. When internal links point at it, the crawl budget and link equity spent on it are wasted.

**Fix:** Restore the page, redirect it (301) to the best replacement, or remove every internal link that points at it. Keep 410 for pages that are gone on purpose.

### `response.5xx`

**Page returns a 5xx server error** (severity: critical)

Server errors mean the page could not be served at all. Repeated 5xx responses make search engines slow their crawling of the whole site and eventually drop the affected URLs.

**Fix:** Check the server logs for the URL, fix the underlying error, and re-crawl. If the error is intermittent, look at capacity and rate limits.

### `response.blocked_by_robots`

**Linked page is blocked by robots.txt** (severity: medium)

Search engines will not fetch a disallowed URL, so whatever it contains cannot rank. When it is also linked internally or listed in the sitemap, the site is sending mixed signals and leaking link equity into a page that cannot use it.

**Fix:** If the page should rank, remove the Disallow rule. If it should not, stop linking to it internally and take it out of the sitemap; use noindex rather than robots.txt when it must stay reachable but unindexed.

### `response.error`

**Page could not be fetched (timeout or connection error)** (severity: high)

A timeout or connection failure means the crawler, and probably search engines, got nothing back. Pages that fail this way are not indexed and may be slow for users too.

**Fix:** Open the URL in a browser. If it loads, check for slow responses, aggressive rate limiting or bot blocking; if it does not, fix the server or DNS.
