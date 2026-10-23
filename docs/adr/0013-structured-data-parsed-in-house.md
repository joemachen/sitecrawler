# ADR-0013: Structured data is parsed in-house over the crawl's own tree, normalised to one shape, and checked against a bundled schema.org vocabulary and a hand-kept table of Google's requirements

**Status:** Accepted
**Date:** 2026-10-22

## Context

Phase 10 asks for structured data validation: extract JSON-LD, microdata
and RDFa from every page, validate types and properties against
schema.org, check Google's rich-result requirements per type, and report
invalid JSON, unknown types and properties, missing required fields and
conflicting entities. The roadmap names `extruct` for the extraction.

The usual constraints apply. The HTML bodies are not stored (ADR-0009), so
whatever reads the markup has to run in the crawl pass. The rules need the
findings, and `audit` may not import `analysis` (ADR-0011, ADR-0012).
Crawls and tests never touch the network.

## Decision

- **We parse in-house, not with extruct.** `parse/structured.py` reads the
  three syntaxes from the lxml tree `parse_html` already has, before the
  scripts are stripped from it. Under `--render` that tree is the rendered
  DOM, so JSON-LD injected by JavaScript is seen, as every other parsed
  field is (ADR-0008). Reasons:
  - extruct's last release (0.18.0) is from 2024-11 and does not list
    Python 3.13.
  - It brings seven dependencies, rdflib and pyrdfa3 among them, for what
    is here about 250 lines.
  - It drops a JSON-LD block that fails to parse, but `schema.invalid_json`
    needs the parser's message and the page line.
  - It parses the page a second time.
- **The three syntaxes are read to the extent search engines use them:**
  - JSON-LD: `@graph`, top-level arrays, `@type` lists, value objects
    (`@value`, `@list`, `@set`). `@context` is read only for its vocabulary
    (a string, `@vocab`, or a list of either).
  - Microdata: `itemscope`, `itemtype`, `itemprop`, `itemid`, with the WHATWG
    value rules (`content` on `meta`, `href`/`src` resolved, `value` on
    `data`/`meter`, `datetime` on `time`, else the text).
  - RDFa Lite: `vocab`, `typeof`, `property`, `resource`; `content` first,
    then the URL attribute, then the text.

  Reason: these are the parts Google's own documentation uses. Full JSON-LD
  expansion, microdata `itemref` and full RDFa (`prefix` maps, `rel`/`rev`,
  chaining) are not supported; they are rare in the wild and cost more than
  they find.
- **All three become one shape.** Each item is a `StructuredItem(format,
  data, line)`. `data` is a dict in which every key maps to a list of text
  values and nested dicts, with `@type` and `@id` kept as keys. schema.org
  names are reduced to their bare form (`Product`, `offers`) however they
  were spelt (`schema:Product`, `http://schema.org/Product`, `https://...`).
  Names from any other vocabulary keep their full IRI, so a bare name always
  means schema.org and the audit skips the rest. Numbers and booleans become
  text. Reason: one checker for three syntaxes, and the stored JSON reads the
  same whatever the source.
- **Storage is one row per item.** The `structured_data` table holds
  `format`, `types`, `data_json` and `line` per item. A JSON-LD block that
  failed to parse gets its own row with `error` set and no data. A parsed
  page with no structured data has no rows; `page_html.content_hash` tells
  it apart from a page that was never parsed. The export gains a
  `structured_data` sheet and a `structured_types` column on `pages`.
- **The schema.org vocabulary is bundled, reduced, and refreshed by a
  script.** `scripts/update_schemaorg.py` downloads the current release and
  keeps only each type's parents and each property's domain types, about
  100 kB. It writes `src/sitecrawler/data/schemaorg.json`, which is
  committed and shipped. Reason: the audit must work offline and
  reproducibly, and the full release (about 1 MB of labels, comments and
  ranges) carries nothing the checks read. Property *ranges* are not
  checked: schema.org says a value of the wrong type is acceptable, and
  Google checks values per rich result instead.
- **Google's requirements are a hand-kept table, `audit/richresults.py`.**
  It covers Product, Article, BreadcrumbList, Organization, LocalBusiness,
  Recipe, Event and VideoObject, each with its required and recommended
  property paths and the Search Central page they come from (checked
  2026-10-22).
  - Subtypes use their nearest listed ancestor in the vocabulary, so
    NewsArticle is checked as Article and Restaurant as LocalBusiness.
  - A need can list alternatives (`offers.price` or
    `offers.priceSpecification.price` or `offers.lowPrice`).
  - A need can be conditional (`aggregateRating.ratingValue` when there is
    an `aggregateRating`).
  - A dotted path must hold on every node it reaches, so every offer needs
    a price.
  - FAQPage is deliberately absent: Google stopped showing FAQ rich results
    on 2026-05-07.
  - Organization's recommended list is a subset of Google's thirty or so,
    so that a plain company page is not buried in suggestions.

  Reason: Google publishes these lists only as prose. A table that names
  its source is easy to review against the source and easy to change.
- **Checking is an audit index, the report is analysis.** `audit/structured.py`
  builds `CrawlView.structured`, which holds per-page findings, from the
  vocabulary and the table. `analysis/structured.py` adds the crawl-wide
  counts and lists every finding (`sitecrawler schema report`), the same
  split as ADR-0011 and ADR-0012.
- **Six rules in a `Structured data` category, one issue per page each.**
  The message joins every finding of that kind on the page.

  | Rule | Severity |
  | --- | --- |
  | `schema.invalid_json` | high |
  | `schema.missing_required` | high |
  | `schema.unknown_type` | medium |
  | `schema.conflicting` | medium |
  | `schema.unknown_property` | low |
  | `schema.missing_recommended` | low |

  The checks behind three of them are narrow on purpose:
  - Unknown properties are only checked on items whose types are all known
    schema.org types; untyped nested values are not checked.
  - *Conflicting* means two items of one type that name the same entity
    (the same `@id`, else the same resolved `url`) and give one property
    different text.
  - Rich-result needs are checked on top-level items only.

  Reason: these catch what goes wrong in practice (a plugin and a theme both
  marking up the product, a hand-edited template) without guessing at
  intent.

## Consequences

- Easier:
  - No new dependency.
  - Findings point at a page line and a property path.
  - Rendered pages are covered without extra work.
  - Adding a rich-result type is one table entry plus a fixture page.
- Harder:
  - We own a parser, so edge cases that extruct handles (full RDFa,
    `itemref`, JSON-LD expansion) are ours to add if they ever matter.
  - Google's requirements change, and the table has to follow them (the
    FAQ retirement is the example).
  - A change to the parsing or the item shape means a re-crawl, like the
    fingerprints (ADR-0012) and the extractors (ADR-0009).
  - Crawl files written before 1.0 have no `structured_data` table and open
    with an error.
- Alternatives considered:
  - extruct (above).
  - Validating against the full schema.org JSON-LD with an RDF library:
    heavier, and it answers questions (range conformance) that search
    engines do not ask.
  - Calling Google's Rich Results Test: it is an online service with no
    public API for bulk use, and crawls must work offline.
