# ADR-0011: The link graph is part of the audit index; Link Score is log-scaled PageRank over the follow graph, stored on `pages` by `audit`

**Status:** Accepted
**Date:** 2026-10-22

## Context

Phase 8 asks for internal linking analysis: inlinks and outlinks per page
with anchor text, `rel`, position and nofollow; a shortest-path click depth
next to the crawl's first-discovery depth; a Link Score (PageRank over the
internal follow graph, scaled 0-100); rules for pages with few inlinks,
deep pages, links to redirects or errors, generic anchors, nofollow
internal links and pages with too many outlinks; and anchor text per
target. Before this phase the crawl stored every anchor (`links` table) and
`CrawlView.inlinks` indexed them by target, but nothing walked the graph.

Four things had to be decided: where the graph lives, what PageRank runs
over, how the score is scaled, and where the results are kept.

## Decision

- **The graph index lives in `audit/graph.py`, reached as
  `CrawlView.link_graph`; the link *report* lives in `analysis/links.py`.**
  `docs/ARCHITECTURE.md` had PageRank under `analysis/`, but the audit
  rules need inlink counts, depth and score, and `audit` may not import
  `analysis` (the dependency direction runs the other way:
  `analysis/sitemaps.py` already imports `CrawlView`). So the graph joins
  the index the rules read, next to `inlinks` and the sitemap listings,
  and `analysis/` keeps what Phase 7 put there: the whole-crawl report
  (every link to a broken or redirecting page with its source and anchor,
  anchor text per target, the score extremes) that `sitecrawler links
  report` and `links anchors` print. Reason in one line: an import cycle
  or a lazy import to dodge one is worse than moving a box on a diagram.
  `robots_directives` moved from `audit/engine.py` to `audit/directives.py`
  so the graph and the engine can both use it; `engine` re-exports it.
- **Nodes are every crawled page; edges are follow links between them,
  resolved through redirects.** An edge runs from a parsed HTML page to
  the page a click would land on: the link's target after normalisation,
  then its `final_url` when that is another crawled page. Links with
  `rel=nofollow`, every link on a page whose robots directives say
  `nofollow` or `none`, self-links and links to URLs the crawl never
  fetched are left out of the follow graph; duplicate links between the
  same two pages count once. Redirect sources contribute no edges of their
  own (their parsed links belong to the target, which has its own node).
  Pages with no out-edges spread their rank evenly over every node, the
  textbook treatment, so a 404 or a leaf page does not sink rank. Damping
  is 0.85, iteration stops when the total change drops below 1e-9 or
  after 100 rounds. Canonicals are ignored for now: a canonicalised page
  keeps its own node. Reason: this is the graph search engines are told to
  follow, and every exclusion matches a rule the audit already has
  (`robots.nofollow`, `link.nofollow_internal`, `link.to_redirect`).
- **Click depth is a breadth-first search from the start page over every
  internal link, nofollow included, also resolved through redirects.** A
  redirecting URL and the page it lands on both sit one click below the
  page that links to them. Pages nothing reaches have no depth (`None`),
  which is what the first-discovery `depth` of a sitemap-seeded page (0)
  hides. List-mode crawls have no start page and so no click depth.
  Reason: depth is "how many clicks from home", and a visitor follows
  nofollow links too.
- **Link Score is PageRank on a log scale from 0 (the lowest page) to 100
  (the highest).** `100 * (ln p - ln min) / (ln max - ln min)`, rounded;
  when every page is equal, every page scores 100. Reason: raw PageRank on
  a real site is one home page and thousands of pages within rounding of
  zero; a linear scale would put every content page at 0-3, a log scale
  spreads them so the grid can be sorted and compared. The number is
  relative to this crawl only and is not comparable between sites.
- **`audit` writes `inlinks`, `link_depth` and `link_score` onto `pages`**,
  the way it writes the indexability verdict, and the `links` table gains
  `position`. Reason: the three numbers are derived from the whole crawl,
  which is the audit's job, and putting them on `pages` makes them export
  columns and grid cells with no new table or reader. Old crawl files lack
  the columns and open with an error, as every schema change has during
  0.x: re-crawl.
- **Position is the nearest sectioning ancestor of the anchor**:
  `header`, `nav`, `footer` or `aside` (or an element with the ARIA role
  `banner`, `navigation`, `contentinfo` or `complementary`), else `body`.
  Nearest wins, so the main menu in `<header><nav>` is `nav` and a link
  list in `<footer><nav>` is `nav` too. Reason: one rule anyone can
  predict from the markup beats a priority table; templates that want the
  footer menu counted as footer links can drop the inner `nav`.

## Consequences

- Easier: rules read `crawl.link_graph` like any other index; the web
  UI's Links tab and detail pane get the metrics from the same object the
  audit used, so the numbers agree; the fixture acceptance (home page
  highest, `/orphan` lowest) is a plain assertion over the graph.
- Harder: PageRank is pure Python, about a second per 10k pages per audit
  pass; the live session re-runs it on every audit revision, bounded by
  the adaptive audit gap. The fixture needed `Home` links on its hub pages
  before the home page outranked the blog, because a site whose home page
  is linked from one place is not what PageRank rewards; real sites link
  home from every page.
- Alternatives considered: personalised PageRank teleporting to the start
  URL (would make the acceptance true by construction and the score
  meaningless); linear scaling (unreadable on real sites); a `link_metrics`
  table (one more join for three numbers); computing the metrics at crawl
  time (the graph is not complete until the crawl is); a graph library
  (networkx for one algorithm on dicts).
