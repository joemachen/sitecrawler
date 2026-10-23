# Duplicate content

```bash
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler audit example.db                     # content rules are part of the audit
uv run sitecrawler issues example.db --rule content.duplicate
uv run sitecrawler duplicates report example.db         # every cluster, with each member's status
uv run sitecrawler duplicates report example.db --max-distance 6
```

Every crawl fingerprints the main text of every HTML page: a hash that is
the same when the text is the same, and a SimHash that stays close when
most of the text is the same. The audit groups pages by those
fingerprints, flags the groups where more than one page is indexable, and
reports pages with too little text of their own. `duplicates report`
lists the groups themselves.

## What the crawl computes

| Value | Meaning |
| --- | --- |
| Main text | The visible text of `<main>` (or the element with `role=main`, or the body) with the boilerplate removed: `header`, `nav`, `footer` and `aside` elements, elements with the ARIA roles `banner`, `navigation`, `contentinfo` or `complementary`, and scripts, styles and templates. The page title is in the head and never counts. Under `--render` this is the rendered DOM. |
| `content_words` | Words in the main text. Lower than `word_count`, which counts the whole page, menus included. |
| `content_hash` | SHA-256 of the main text's words, lower-cased, punctuation dropped. Two pages with the same hash have the same content; a changed comma does not change it, a changed word does. |
| `simhash` | A 64-bit SimHash over every run of three consecutive words. Two pages differ by roughly `64 * acos(1 - f) / pi` bits for a fraction `f` of three-word runs changed: 5% changed is about 6 bits, unrelated pages sit at about 32. |

All three are stored on `page_html` and exported at the end of the `pages`
sheet. Pages that were not parsed as HTML (errors, redirects, images) have
no fingerprint; a page whose body is nothing but boilerplate has a
fingerprint of zero words. Design notes, including why the fingerprint is
computed during the crawl, are in ADR-0012.

## How pages are grouped

- **Exact groups:** every page with any main text, grouped by
  `content_hash`. Any length.
- **Near clusters:** pages of 200 words or more whose SimHash values are
  within 10 bits of each other, directly or through another member. Ten
  bits is roughly 88% of three-word runs in common. Shorter pages are
  left out because the SimHash of a page with a few dozen words is too
  coarse to compare; they are reported as low content instead.
- Each group and cluster has a **representative**: the member with the
  highest Link Score, then the first URL. It is the page to keep.

## The rules

| Rule | Severity | Fires on |
| --- | --- | --- |
| `content.duplicate` | high | An indexable page whose main text is identical to another indexable page's. The message names the other page. |
| `content.near_duplicate` | medium | An indexable page of 200+ words within 10 bits of another indexable page with a different text. The message names the closest one and how many bits apart they are. |
| `content.low_word_count` | low | An indexable HTML page with fewer than 200 words of main text. |

Only indexable pages are flagged, which is the canonical cross-check: a
copy that canonicalises to the original, redirects, is `noindex` or returns
an error has already told search engines which page to keep and is not an
issue. Two copies that both claim to be canonical (self-referencing or no
canonical at all) are. `duplicates report` still lists every member of a
group, with its indexability, so you can see the copies that are handled.

`content.low_word_count` fires on most pages of a site built from short
stubs, which is the point; on a site with real articles it singles out the
pages that have none.

## `duplicates report`

One tab-separated line per member of every exact group, then of every near
cluster that holds more than one distinct text: kind, representative URL,
member URL, SimHash bits between the member and the representative, the
member's indexability:

```text
exact  https://example.com/guide       https://example.com/guide           0  indexable
exact  https://example.com/guide       https://example.com/guide?print=1   0  canonicalised to https://example.com/guide
exact  https://example.com/guide       https://example.com/old-guide       0  indexable
near   https://example.com/red-shoes   https://example.com/red-shoes       0  indexable
near   https://example.com/red-shoes   https://example.com/blue-shoes      7  indexable
```

`--max-distance N` reclusters with another threshold (0 to 63) without
changing what the audit stored. The last line, to stderr, is the summary
`sitecrawler audit` prints too: pages fingerprinted, pages in identical
groups, pages in near clusters, and indexable pages under the floor.

```bash
uv run sitecrawler duplicates report example.db 2>/dev/null | grep ^near | cut -f2,3 | sort -u
```

## In the web UI

The **Content** tab shows `content_words`, `word_count`, the number of
exact and near duplicates each page has, the representative of its cluster
(`duplicate_of`, empty when the page is the representative or has none)
and the hash, with a filter per rule plus *No main text*. In the detail
pane, **Content** lists the fingerprint and every other page in the same
group or cluster with its kind, distance and indexability.

## In the file and the exports

`page_html` gained `content_hash`, `simhash` and `content_words`; the
`pages` sheet and JSON list end with `content_words`, `content_hash`,
`simhash`. Crawl files written before 0.10 lack the columns and open with
an error; re-crawl. Changing how the main text is read would change every
fingerprint, so that also means a re-crawl: the bodies are not stored.

Limits for now: the thresholds (10 bits, 200 words) are constants in the
rules and only the report's distance is an option; boilerplate is
recognised by element and role only, so a sidebar in a plain `<div>`
counts as content; and the near-duplicate floor is the low-content floor,
so templated pages under 200 words are reported as thin rather than as
variants of each other.
