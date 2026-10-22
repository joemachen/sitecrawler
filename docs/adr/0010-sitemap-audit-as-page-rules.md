# ADR-0010: Sitemap findings are page rules; file-level facts are a report; generation is an export

**Status:** Accepted
**Date:** 2026-10-22

## Context

Phase 7 asks for sitemaps that match reality: parse every sitemap and
sitemap index (gzip included), keep every URL with the file it came from,
report orphans, non-indexable sitemap entries, indexable pages missing from
the sitemap, entries on other hosts and entries listed more than once, and
write a valid sitemap from a crawl. Before this phase the crawler read only
`<loc>`, remembered `(sitemap_url, loc)` pairs, and one rule
(`robots.noindex_in_sitemap`) used them.

Three things had to be decided: what the sitemap audit compares, where each
kind of finding lives, and how generation treats `lastmod`, `changefreq` and
`priority`.

## Decision

- **The audit compares the sitemap entries, normalised the crawl's way, with
  the crawled pages and their indexability verdict.** A sitemap entry is
  looked up with `CrawlView.normalize`, so `/a/`, `/a` and `www.` variants
  meet the page they describe, exactly as links do. Reason in one line: the
  crawler already decided which URLs are the same page, and a second
  definition would report differences that search engines do not see.
- **Per-page findings are audit rules in a new `Sitemaps` category.**
  `sitemap.orphan` (an indexable page the sitemap lists and no other page
  links to), `sitemap.non_indexable` (a listed page whose verdict is not
  indexable, with the reason as the message), `sitemap.missing` (an
  indexable 200 page no sitemap lists) and `sitemap.duplicate` (a page listed
  more than once, across files or within one). Reason: an issue is a fix on a
  page, and these four are; they then get a fixture page, generated docs, an
  Issues row and a tab filter for free. `sitemap.orphan` is limited to
  indexable pages because a noindex or blocked orphan wants removing from the
  sitemap, not linking to, and `sitemap.non_indexable` already says so.
  `sitemap.missing` stays silent when the crawl read no sitemap: one "no
  sitemap found" line beats one issue per page. `robots.noindex_in_sitemap`
  stays as the more specific rule for the noindex case, the way
  `page.non_indexable` and `canonical.not_self_referencing` overlap with
  their specific rules.
- **File-level facts are a report, not issues.** Which sitemap files were
  read, which could not be fetched or parsed, how many entries each holds
  and which entries point at other hosts are stored (a new `sitemaps` table,
  and `lastmod`, `changefreq`, `priority` on `sitemap_urls`) and printed by
  `sitecrawler sitemap report` and as one line under `audit`. Reason: an
  issue row needs a crawled page to hang on, and these facts belong to a
  file, not a page; an entry on another host was never fetched, so there is
  no page.
- **Generation is an export.** `sitecrawler sitemap generate crawl.db` is
  `export/sitemap.py`: it writes the pages whose indexability verdict,
  computed on the spot from the stored crawl, is indexable with status 200,
  one `urlset` up to 50,000 URLs, otherwise numbered files plus an index
  named after the output path. Reason: it is a writer over the pages table
  with a filter the audit already defines, which is what `export/` is for,
  and the `cli/` command stays a few lines.
- **`lastmod` only on request, from `Last-Modified`; never `changefreq` or
  `priority`.** `--lastmod` copies each page's `Last-Modified` response
  header as a W3C date; without the flag the sitemap has `<loc>` only.
  Reason: Google ignores `changefreq` and `priority`, and uses `lastmod`
  only while it stays accurate, so emitting a server's current time as a
  modification date does more harm than leaving it out.

## Consequences

- Easier: the four rules reuse `CrawlView` and the indexability verdict, so
  they cost nothing to keep consistent with the rest of the audit; the web
  UI's Sitemaps tab becomes rule-backed filters; the sitemap export reuses
  the same verdict, so what `generate` writes is exactly what
  `sitemap.missing` would stop flagging.
- Harder: two places to look (the Issues list for page findings, `sitemap
  report` for file findings); a crawl capped by `--max-pages` leaves sitemap
  entries uncrawled, which the rules skip and the report counts.
- Alternatives considered: issues without a page (a schema change to
  `issues` and a second row shape in every reader, for two findings);
  one roll-up `sitemap.mismatch` rule with the kind in the message (one
  count for four different fixes); generation in `analysis/` or `audit/`
  (neither writes files); always emitting `lastmod` (wrong dates are worse
  than none).
