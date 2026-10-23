# ADR-0012: Content fingerprints are computed in the crawl pass and stored on the page; clustering is an audit index, the rules flag indexable members only

**Status:** Accepted
**Date:** 2026-10-22

## Context

Phase 9 asks for duplicate and near-duplicate content detection: exact
duplicates by a hash of the main text with boilerplate stripped,
near-duplicates by SimHash with a configurable Hamming threshold reported
as clusters with a representative URL, low-content pages under a word
count, and a cross-check against canonicals so that copies which already
canonicalise to one page are not the issue.

Two earlier decisions shape the design. ADR-0009 keeps the HTML bodies out
of the crawl file (the extractors run while the page is in hand), and
ADR-0011 put the link graph in `audit/` rather than `analysis/` because the
rules read it and `audit` may not import `analysis`. Both apply again:
hashing needs the body, and the duplicate rules need the clusters.

## Decision

- **The fingerprint is computed by the parser and stored on the page.**
  `parse_html` ends by calling `parse/fingerprint.py`, which reads the
  *main text* (below), hashes its casefolded words with SHA-256 and builds
  a 64-bit SimHash over three-word runs. The result is a
  `Fingerprint(content_hash, simhash, words)` on `ParsedPage` and
  `PageRecord`, written to three new `page_html` columns (`content_hash`,
  `simhash` as 16 hex digits, `content_words`; NULL on pages that were not
  parsed as HTML). Under `--render` the rendered DOM is what gets
  fingerprinted, the same text every other parsed field comes from. Reason
  in one line: the only alternative is storing bodies, which ADR-0009
  deliberately does not do yet, and three small columns cost nothing per
  page; the trade is that a change to the fingerprint algorithm means a
  re-crawl, like a changed extractor does.
- **Main text is the body (or `<main>`, or `role=main`) minus the
  boilerplate**: `header`, `nav`, `footer`, `aside`, their ARIA-role
  stand-ins (`banner`, `navigation`, `contentinfo`, `complementary`),
  `script`, `style`, `noscript` and `template`. These are the same
  sectioning elements the link position (ADR-0011) recognises, so one
  rule explains both. The page `<title>` is in the head and never counts.
  Reason: readability-style extraction (text density, link ratios) is a
  heuristic that fails differently on every template; stripping named
  elements is predictable, and templates that mark their chrome get full
  credit for it. Nothing in the fingerprint reads CSS, so hidden elements
  still count.
- **The SimHash is 64 bits over three-word shingles, weighted by count,
  hashed with BLAKE2b.** Three-word runs tell reordered text from
  repeated text; unigrams would call a shuffled page identical. Pages
  with fewer than three words use the whole text as one feature. The
  Hamming distance between two fingerprints depends on the share of
  shingles the pages have in common and not on their length: about
  `64 * acos(1 - f) / pi` bits for a fraction `f` of changed shingles,
  so 5% changed is about 6 bits and unrelated pages sit at 32 give or
  take 4.
- **Clustering is an audit index, `audit/duplicates.py`, reached as
  `CrawlView.duplicates`; the report is `analysis/duplicates.py`.** The
  same split as ADR-0011, for the same reason: the rules read the
  clusters and `audit` may not import `analysis`. The index groups every
  parsed HTML page with any main text by content hash (*exact groups*),
  and clusters the pages of `MIN_WORDS` (200) words or more whose SimHash
  values are within `NEAR_DUPLICATE_DISTANCE` (10) bits of each other,
  directly or through other members (*near clusters*, single linkage).
  Candidate pairs come from the pigeonhole trick: the 64 bits are cut into
  `distance + 1` blocks and only values that agree on one block are
  compared, over distinct SimHash values, so a thousand identical pages
  are one comparison and a 10k-page crawl stays well under a second. Each
  cluster's representative is its best-linked member (highest Link Score,
  then first URL): the one to keep.
- **Ten bits, not three, and a 200-word floor.** Three bits is the
  textbook threshold for web-scale deduplication of long documents; on a
  250-word page it only catches a word or two of change, and the roadmap's
  acceptance (two pages differing by one sentence) measured nine bits.
  Ten bits is about 88% of shingles in common, close to the 90% other
  crawlers default to. The floor exists because the SimHash of a page
  with a few dozen features is a vote among a few dozen features: the
  fixture's one-sentence pages landed within five to nine bits of each
  other. Below the floor a page is reported as low content instead,
  which is what it is. Exact groups have no floor; identical tiny pages
  are identical. The distance is configurable on `sitecrawler duplicates
  report --max-distance`; the rules use the constant, like every other
  rule threshold so far.
- **The rules flag indexable members only.** `content.duplicate` (high)
  fires on every indexable member of an exact group that has another
  indexable member; `content.near_duplicate` (medium) on every indexable
  member of a near cluster that has an indexable partner with a different
  text, naming the closest one and the bit distance;
  `content.low_word_count` (low) on indexable HTML pages under the floor.
  The canonical cross-check is the existing indexability verdict: a copy
  that canonicalises to the original, redirects, is noindex or errors is
  not indexable and so is never reported, while two copies that both
  claim to be canonical (self-referencing or missing canonical) both are.
  Reason: one definition of "is this page competing" already exists and
  every other site-wide rule uses it.

## Consequences

- Easier: the rules, the report, the web Content tab and the detail pane
  read one `DuplicateIndex`, so their numbers agree; the acceptance test
  is a plain assertion over the index against the fixture crawl; the
  per-page columns export with no new table.
- Harder: crawl files written before this version lack the three
  `page_html` columns and open with an error (re-crawl, as every schema
  change during 0.x); a change to the main-text rule or the shingle size
  changes every stored fingerprint, so it also means a re-crawl; the
  low-content floor doubles as the near-duplicate floor, so templated
  pages under 200 words are reported as thin rather than as variants of
  each other; the `h1-dup-1` / `h1-dup-2` fixture pages, which differ only
  in `<head>`, are now exact duplicates too.
- Alternatives considered: storing the bodies behind a flag (still the
  obvious next step, and then fingerprints could be recomputed without a
  crawl); MinHash with Jaccard similarity (a larger signature per page
  for a threshold expressed as a percentage, which the distance formula
  above gives anyway); readability-style main-content extraction (not
  predictable); clustering in `analysis/` (an import cycle); flagging a
  page whenever any member of its cluster is indexable (reports the
  canonicalised copies the owner already fixed).
