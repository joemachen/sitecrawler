# Audit rules

Every check `sitecrawler audit` runs, generated from the rule classes in
`src/sitecrawler/audit/rules/` by `uv run python scripts/gen_rule_docs.py`.
Do not edit by hand.

Severity: **critical** blocks indexing or breaks pages site-wide, **high** costs
rankings on affected pages, **medium** is worth fixing in the next sprint,
**low** is hygiene, **info** is a fact to know rather than a problem.

One tag can appear under several rules when they ask for different actions:
an off-site canonical is listed by `canonical.off_site` (fix the tag),
`canonical.canonicalised_but_linked` (fix the links) and
`canonical.not_self_referencing` (the informational roll-up). Count problems
by the highest-severity rule, not by the number of rows.

## Canonicals

### `canonical.canonicalised_but_linked`

**Internal links point at a page that canonicalises elsewhere** (severity: low)

Links are sending users and crawlers to a URL the site itself says is not the one to index. Linking to the canonical URL instead keeps the signals in one place.

**Fix:** Update internal links to the canonical URL.

### `canonical.chain`

**Canonical target has a different canonical of its own** (severity: medium)

Search engines do not follow canonical chains reliably; the signal may stop at the first hop or be ignored altogether.

**Fix:** Point every page in the group straight at the final canonical URL.

### `canonical.conflict`

**HTML canonical and Link header canonical disagree** (severity: medium)

Two canonicals for one page is a contradiction search engines resolve by ignoring both. It usually means a CDN or framework adds a header the template does not know about.

**Fix:** Remove one of them, or make both say the same URL.

### `canonical.missing`

**Page declares no canonical URL** (severity: low)

Without a canonical, search engines pick which of a page's URL variants (trailing slash, query strings, http/https, www) to index, and may split signals across several. A self-referencing canonical settles it.

**Fix:** Add <link rel="canonical" href="..."> pointing at the page's preferred URL.

### `canonical.not_self_referencing`

**Canonical points at a different URL** (severity: info)

Not a problem by itself: this is how duplicates are meant to be handled. Listed so you can confirm every one of these is intentional.

**Fix:** Check the list; if a page should rank on its own, make its canonical self-referencing.

### `canonical.off_site`

**Canonical points at another site** (severity: medium)

A cross-domain canonical hands this page's ranking to the other site. That is right for syndicated content and wrong for almost everything else, including staging sites that kept the production canonical.

**Fix:** Unless the content is deliberately syndicated, point the canonical at this site's own URL.

### `canonical.og_url_mismatch`

**og:url differs from the canonical** (severity: low)

Social networks treat og:url as the page's identity, search engines use the canonical. When they disagree, shares and links accumulate on two URLs.

**Fix:** Set og:url to the same URL as the canonical.

### `canonical.to_non_200`

**Canonical points at a URL that is not a 200 page** (severity: high)

A canonical is a request to index a different URL instead of this one. If that URL is missing, errors or redirects, the request is ignored at best, and at worst this page drops out while nothing replaces it.

**Fix:** Point the canonical at a URL that returns 200 directly (no redirect).

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

## Hreflang

### `hreflang.invalid_lang`

**hreflang uses an invalid language or region code** (severity: medium)

Hreflang values must be ISO 639-1 language codes, optionally with an ISO 3166-1 region (``en-GB``) or script, or ``x-default``. Anything else (``en-UK``, ``english``, ``uk``) is ignored, silently.

**Fix:** Use the ISO codes: language in lowercase, region in uppercase, joined by a hyphen.

### `hreflang.missing_return_link`

**hreflang alternate does not link back to this page** (severity: high)

Hreflang only works when both pages confirm the relationship. If the alternate does not list this page, Google ignores the annotation on both.

**Fix:** Add the matching hreflang link on every alternate page.

### `hreflang.missing_self`

**hreflang set does not reference the page itself** (severity: low)

Each page in a language cluster must list every version including its own; without the self reference the annotations on this page may be discarded.

**Fix:** Add an hreflang link whose href is this page's own canonical URL.

### `hreflang.missing_x_default`

**hreflang set has no x-default** (severity: low)

``x-default`` tells search engines which version to show users whose language matches none of the alternates. Without it they pick one, often the wrong one.

**Fix:** Add <link rel="alternate" hreflang="x-default" href=...> pointing at the fallback page.

### `hreflang.to_non_200`

**hreflang points at a URL that is not a 200 page** (severity: high)

An alternate that is missing, errors or redirects breaks the whole cluster for that language and wastes crawl budget.

**Fix:** Point hreflang at the final, live URL of each language version.

### `hreflang.to_non_canonical`

**hreflang points at a URL whose canonical is a different page** (severity: medium)

Hreflang must reference canonical URLs. Pointing at a page that defers to another URL sends search engines a contradiction, and the alternate is dropped.

**Fix:** Use each alternate's canonical URL in the hreflang link.

## Indexability

### `page.non_indexable`

**Page cannot be indexed** (severity: info)

One list of everything search engines will not index, whatever the cause: robots.txt, errors, redirects, noindex or a canonical pointing elsewhere. The specific rules say which of these are problems; this one is the roll-up to check against what you expect the site to show in search.

**Fix:** Scan the reasons; anything you did not intend has its own rule and fix above.

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

## Pagination

### `pagination.broken_sequence`

**rel=next target does not link back with rel=prev** (severity: medium)

prev/next should form a chain that reads the same in both directions. A next page whose prev points somewhere else (or nowhere) means the series has a gap or two series are tangled.

**Fix:** Make the next page's rel=prev point back at this page.

### `pagination.canonical_to_first`

**Paginated page canonicalises to another page in the series** (severity: medium)

Pointing page 2, 3, ... at page 1 tells search engines those pages are duplicates, so the items listed only on them are never discovered. Each page in a series should be its own canonical.

**Fix:** Give every paginated page a self-referencing canonical.

### `pagination.to_non_200`

**rel=prev or rel=next points at a URL that is not a 200 page** (severity: high)

A pagination link to a missing or redirecting page breaks the series: crawlers stop there and the pages beyond it lose their path in.

**Fix:** Point rel=prev/next at the live URL of the neighbouring page.

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

**Sitemap or list URL is blocked by robots.txt** (severity: low)

Search engines will not fetch a disallowed URL, so whatever it contains cannot rank. A blocked URL that arrived via the sitemap or your URL list is the site advertising a page it also forbids. Blocked URLs that internal links point at are reported by robots.blocked_but_linked.

**Fix:** If the page should rank, remove the Disallow rule. If it should not, take it out of the sitemap; use noindex rather than robots.txt when it must stay reachable but unindexed.

### `response.error`

**Page could not be fetched (timeout or connection error)** (severity: high)

A timeout or connection failure means the crawler, and probably search engines, got nothing back. Pages that fail this way are not indexed and may be slow for users too.

**Fix:** Open the URL in a browser. If it loads, check for slow responses, aggressive rate limiting or bot blocking; if it does not, fix the server or DNS.

## Robots directives

### `robots.blocked_but_linked`

**Internal links point at a URL blocked by robots.txt** (severity: medium)

Crawlers follow the link, hit the Disallow rule and stop: the page can still be indexed (URL only, no content) and the link equity goes nowhere useful.

**Fix:** If the page should rank, allow it in robots.txt. If it should not, use noindex instead of Disallow, or stop linking to it.

### `robots.conflicting`

**Robots directives contradict each other** (severity: medium)

index and noindex (or follow and nofollow) on the same page, across the meta tag and the X-Robots-Tag header, leave the outcome to each search engine's tie-break rule. Google takes the most restrictive.

**Fix:** Decide what the page should do and keep a single consistent directive.

### `robots.nofollow`

**Page is set to nofollow** (severity: low)

A page-level nofollow tells crawlers to ignore every link on the page, so nothing it links to gets any equity from it. Rarely what anyone intends.

**Fix:** Remove nofollow from meta robots or X-Robots-Tag; use rel=nofollow on individual links instead.

### `robots.noindex`

**Page is set to noindex** (severity: info)

The page asks not to be indexed, via meta robots or X-Robots-Tag. Correct for thank-you pages and internal search; a disaster when it is left on after a launch.

**Fix:** Confirm each listed page should stay out of search; remove the directive otherwise.

### `robots.noindex_in_sitemap`

**Noindex page is listed in the sitemap** (severity: medium)

The sitemap says 'please index this' and the page says 'do not'. Search engines follow the page, and lose a little trust in the sitemap.

**Fix:** Remove noindex pages from the sitemap (or drop the noindex if they should rank).

### `robots.noindex_linked`

**Noindex page receives internal links** (severity: low)

Links into a page that cannot rank are wasted link equity, and over time Google stops following links from long-term noindex pages too.

**Fix:** Link to an indexable page instead, or reconsider whether this page should be noindex.

### `robots.none`

**Page uses the robots directive none (noindex and nofollow)** (severity: low)

``none`` is shorthand for noindex plus nofollow. It is easy to misread as 'no directives' and is best spelled out.

**Fix:** Replace it with the explicit directives you mean, or remove it.

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
