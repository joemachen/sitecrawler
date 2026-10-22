# Internal linking

```bash
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler audit example.db                 # link rules are part of the audit
uv run sitecrawler issues example.db --rule link.few_inlinks
uv run sitecrawler links report example.db          # Link Score, links to errors and redirects
uv run sitecrawler links anchors example.db         # what the site calls each page
```

Every crawl stores every anchor: the page it is on, where it points, its
text, its `rel`, whether it is nofollow and where on the page it sits. The
audit builds the internal link graph from those anchors and gives every
page three numbers: how many other pages link to it, how many clicks it is
from the start page, and a Link Score. Six rules read the graph;
`links report` and `links anchors` list the individual links.

## What the audit computes

| Number | Meaning |
| --- | --- |
| Inlinks | Links from other crawled pages to this one, counted two ways: *unique inlinks* (distinct pages, any `rel`) and *follow inlinks* (distinct pages with at least one link that passes equity). Links from the page to itself never count. |
| Click depth | The fewest clicks from the start page over internal links, nofollow included. A link to a redirect counts as a link to where it lands. Pages the start page cannot reach have no depth (`unreachable`), which the crawl's own `depth` hides: a page seeded from the sitemap has `depth` 0 however deep it really is. List-mode crawls have no start page and no click depth. |
| Link Score | PageRank over the *follow graph*: every link between crawled pages except `rel=nofollow` links, links on pages whose robots directives say `nofollow` or `none`, and self-links; a link to a redirect passes its equity to the page the redirect lands on. The scores are put on a log scale from 0 (the least-linked page) to 100 (the best-linked, normally the home page). The number is relative to this crawl and not comparable between sites. |
| Position | Each anchor's nearest `<header>`, `<nav>`, `<footer>` or `<aside>` ancestor (or the matching ARIA role: `banner`, `navigation`, `contentinfo`, `complementary`); `body` when there is none. The main menu inside `<header><nav>` reads `nav`. |

Design notes, including the PageRank parameters, are in ADR-0011.

## The rules

| Rule | Severity | Fires on |
| --- | --- | --- |
| `link.to_error` | medium | A page with an internal link to a target that returns 4xx or 5xx, could not be fetched, or redirects into a loop or an error. The message names the first such link. |
| `link.to_redirect` | low | A page with an internal link to a URL that redirects to a different page (a `/a` to `/a/` hop does not count). |
| `link.few_inlinks` | low | An indexable page (other than the start page) with one follow inlink or none. The message names the one page that links to it. |
| `link.high_depth` | low | An indexable page more than 3 clicks from the start page. |
| `link.generic_anchor` | low | A page whose internal links use anchor text such as "click here", "read more" or "this page", compared case-insensitively without punctuation. |
| `link.nofollow_internal` | low | A page with `rel=nofollow` on an internal link. A page-wide `nofollow` directive is `robots.nofollow` instead. |
| `link.too_many_outlinks` | low | A page with more than 300 anchors, internal and external together. |

`link.few_inlinks` fires on most pages of a site that has no navigation,
which is the point: on a site with menus and related-links blocks it
singles out the pages those forgot. `sitemap.orphan` still reports the
pages only the sitemap knows about.

## `links report`

Prints a table of the pages with the highest and lowest Link Scores
(`--top 10` at each end; the whole table when the crawl is small), then one
line per internal link whose target is an error or a redirect, tab
separated: kind, source page, link href, what it lands on, anchor text:

```text
error     https://example.com/      https://example.com/old-page   404                         Our old page
error     https://example.com/      https://example.com/loop       redirect_loop               Loop
redirect  https://example.com/blog  https://example.com/about-us   https://example.com/about   About us
```

The same facts end `sitecrawler audit` as one line (`Links: ...`). Pipe
the lines where you like:

```bash
uv run sitecrawler links report example.db 2>/dev/null | grep ^error | cut -f2,3 | sort -u
```

## `links anchors`

One line per target page and anchor text, with how many internal links use
that text, most used first:

```text
https://example.com/pricing   14   Pricing
https://example.com/pricing    3   click here
https://example.com/pricing    1   see our plans
```

Give a URL to see one page only. An image link with no text shows an empty
anchor.

## In the web UI

The **Links** tab shows Link Score, inlinks (all, unique, follow), click
depth and the outlink counts per page, with a filter per rule plus *No
inlinks*, *Unreachable from the start page* and *Has nofollow outlinks*.
The **Internal** tab carries `link_depth` and `link_score` beside the
crawl `depth`. In the detail pane, **Inlinks** lists every page linking to
the URL with its anchor, `rel` and position, the anchor texts used and the
four numbers above; **Outlinks** shows each link's position too.

## In the file and the exports

`audit` writes `inlinks`, `link_depth` and `link_score` onto the `pages`
table (NULL until the audit has run), so they appear at the end of the
`pages` sheet and JSON list. The `links` table and sheet gained `position`.
Crawl files written before 0.9 lack these columns and open with an error;
re-crawl.

Limits for now: canonicals are ignored by the graph (a canonicalised page
keeps its own score), PageRank runs in pure Python (about a second per
10,000 pages per audit), and the score says nothing about external links.
