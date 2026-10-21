# Audit rules

Every check `sitecrawler audit` runs, generated from the rule classes in
`src/sitecrawler/audit/rules/` by `uv run python scripts/gen_rule_docs.py`.
Do not edit by hand.

Severity: **critical** blocks indexing or breaks pages site-wide, **high** costs
rankings on affected pages, **medium** is worth fixing in the next sprint,
**low** is hygiene, **info** is a fact to know rather than a problem.

## Headings

### `h1.duplicate`

**H1 is shared with other pages** (severity: low)

Pages with the same main heading look like the same page; it is usually a template putting the site or section name where the page subject belongs.

**Fix:** Make the H1 specific to the page.

### `h1.missing`

**Page has no H1** (severity: medium)

The H1 tells readers and search engines what the page is about at a glance. Pages without one tend to have a weaker topical signal and are harder to scan.

**Fix:** Add one H1 that states the page's subject, usually close to the title.

### `h1.multiple`

**Page has more than one H1** (severity: low)

HTML5 allows several H1s, but most templates that produce them are misusing the tag for styling, which dilutes the main heading and confuses screen readers.

**Fix:** Keep one H1 for the page subject and demote the others to H2.

### `h1.too_long`

**H1 is longer than 70 characters** (severity: low)

A heading that runs to a paragraph is hard to scan and usually says too much.

**Fix:** Shorten the H1 to one line and move the rest into the opening paragraph.

### `h2.missing`

**Page has no H2 headings** (severity: info)

Sub-headings break content into scannable sections and give search engines the page's sub-topics. Short pages do not need them; long ones do.

**Fix:** Add H2s for each section of a page that has more than a few paragraphs.

## Meta descriptions

### `meta_description.duplicate`

**Meta description is shared with other pages** (severity: low)

A description reused across pages is ignored by Google in favour of page text, and it tells searchers nothing about which result to pick.

**Fix:** Describe each page specifically, or leave the description out on thin pages.

### `meta_description.missing`

**Page has no meta description** (severity: medium)

The description is the snippet under the title in search results. Without one Google picks a sentence from the page, which is often a menu or a cookie notice, and the result gets fewer clicks.

**Fix:** Write one or two sentences (70 to 155 characters) that say why to click.

### `meta_description.multiple`

**Page has more than one meta description** (severity: low)

Two descriptions usually mean two plugins or templates writing the head; which one search engines use is undefined.

**Fix:** Keep one <meta name="description">.

### `meta_description.too_long`

**Meta description is longer than 155 characters** (severity: low)

Snippets are cut at about 155 characters on desktop and less on mobile.

**Fix:** Front-load the message and trim to about 155 characters.

### `meta_description.too_short`

**Meta description is shorter than 70 characters** (severity: low)

A few words do not earn a click, and Google will usually replace them.

**Fix:** Use the room: one or two full sentences that promise what the page delivers.

## Redirects

### `link.to_redirect`

**Page links to URLs that redirect** (severity: low)

Every click on such a link takes an extra round trip, and crawlers spend budget following the hop. Linking to the final URL is free to fix and removes the dependency on the redirect staying in place.

**Fix:** Change the href to the URL the redirect lands on.

### `redirect.chain`

**Redirect chain of two or more hops** (severity: medium)

Every hop costs a round trip for users and crawlers, and each one leaks a little link equity. Google follows up to ten hops, but long chains slow crawling and are usually a sign of migrations layered on migrations.

**Fix:** Point the first URL straight at the final destination, and update internal links to use the final URL.

### `redirect.loop`

**Redirect loop or chain that never resolves** (severity: high)

The URL redirects back to itself (or past the hop limit), so neither users nor search engines ever reach a page. Browsers show an error and the URL drops out of the index.

**Fix:** Find the rule that sends the final hop back to the start (often an HTTP to HTTPS rule fighting a trailing-slash rule) and make the chain end at a 200.

### `redirect.off_site`

**Internal URL redirects to another site** (severity: medium)

Internal links are sending visitors and link equity to a different domain. That is fine for a deliberate move, but a surprise when it comes from an old campaign URL, a hijacked plugin or a misconfigured rule.

**Fix:** If the move is intended, update internal links to point at the new domain directly. Otherwise fix the redirect rule.

### `redirect.temporary`

**Temporary redirect (302/307) used for a permanent move** (severity: low)

A temporary redirect tells search engines to keep the old URL indexed and come back later. For a page that has moved for good, that delays the transfer of rankings to the new URL.

**Fix:** Use 301 (or 308 to preserve the method) for permanent moves. Keep 302/307 only for genuinely temporary situations such as A/B tests or maintenance.

### `redirect.to_error`

**Redirect ends on a 4xx or 5xx page** (severity: high)

A redirect promises a replacement page; landing on an error instead is worse than a plain 404 because it also wastes the hop. Search engines treat the chain as a dead end.

**Fix:** Redirect to a live, relevant page, or remove the redirect and let the URL return 404 or 410 honestly.

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

## Titles

### `title.duplicate`

**Title is shared with other pages** (severity: medium)

Identical titles tell search engines the pages are about the same thing, so they compete with each other and the result shown may be the wrong one. They also make the pages indistinguishable in a results list.

**Fix:** Give each page a title that names what makes it different. If the pages really are the same, canonicalise or merge them instead.

### `title.missing`

**Page has no title** (severity: high)

The title is the headline of the search result and the strongest on-page relevance signal. Without one Google invents a title from the content or the anchor text, usually badly.

**Fix:** Add a unique, descriptive <title> of roughly 30 to 60 characters.

### `title.multiple`

**Page has more than one <title> element** (severity: medium)

Which title search engines use is undefined; usually the first, sometimes the last. A second title normally means two templates or plugins are both writing the head.

**Fix:** Keep exactly one <title> in the <head>.

### `title.same_as_h1`

**Title is identical to the H1** (severity: low)

Not wrong, but a missed chance: the title is written for the results page and the H1 for the reader, so the two can carry different phrases.

**Fix:** Keep the H1 for readers and give the title the search phrase and context.

### `title.too_long`

**Title is longer than 60 characters** (severity: low)

Google cuts titles off at about 580 pixels, roughly 60 characters, so the end of a long title is never seen and the whole thing may be rewritten.

**Fix:** Put the distinctive words first and trim the title to about 60 characters.

### `title.too_short`

**Title is shorter than 30 characters** (severity: low)

Very short titles waste the space searchers use to judge a result, and rarely contain the phrases people search for.

**Fix:** Say what the page is and who it is for; the brand name can go at the end.
