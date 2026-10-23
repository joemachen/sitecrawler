# Structured data

```bash
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler audit example.db                       # schema rules are part of the audit
uv run sitecrawler issues example.db --rule schema.missing_required
uv run sitecrawler schema report example.db               # every finding, with type and property
uv run sitecrawler schema report example.db --kind unknown_property
```

Every crawl reads the structured data on every HTML page: JSON-LD
`<script type="application/ld+json">` blocks, microdata (`itemscope`,
`itemtype`, `itemprop`) and RDFa Lite (`vocab`, `typeof`, `property`). The
audit checks each item against the schema.org vocabulary and against what
Google requires for a rich result. `schema report` lists every finding.

## What the crawl reads

| Syntax | Read | Not read |
| --- | --- | --- |
| JSON-LD | `@type` (one or a list), `@id`, `@graph`, top-level arrays, value objects (`@value`, `@list`, `@set`); `@context` for its vocabulary | Full JSON-LD expansion, remote contexts |
| Microdata | `itemscope`, `itemtype` (one or more), `itemprop` (one or more names), `itemid`; values from `content` on `meta`, `href`/`src` (resolved against the page), `value` on `data`/`meter`, `datetime` on `time`, else the text | `itemref` |
| RDFa Lite | `vocab`, `typeof`, `property`, `resource`; values from `content`, then `href`/`src`, then the text | `prefix` maps, `rel`/`rev`, full RDFa |

All three become the same shape, so they are checked the same way. Each
property holds a list of text values and nested items. schema.org names
are bare (`Product`, `offers`) however they were written (`schema:Product`,
`http://schema.org/Product`). Names from another vocabulary keep their full
IRI and are not checked. A `<meta property="og:...">` tag outside any item
is Open Graph, not structured data, and is ignored.

Under `--render` the rendered DOM is read, so JSON-LD added by JavaScript
counts. Design notes, including why this is not extruct, are in ADR-0013.

## The rules

| Rule | Severity | Fires on |
| --- | --- | --- |
| `schema.invalid_json` | high | A JSON-LD block that does not parse. The message gives the parser's complaint and the page line. |
| `schema.missing_required` | high | An item of a rich-result type without a property Google requires, e.g. `Product needs offers.price or offers.priceSpecification.price or offers.lowPrice`. |
| `schema.unknown_type` | medium | A schema.org `@type` that does not exist (`Prodcut`). |
| `schema.conflicting` | medium | Two items of one type naming the same entity (same `@id`, else same `url`) that give a property different text. |
| `schema.unknown_property` | low | A property schema.org does not define, or does not define on the item's type or its ancestors (`price` on a Product rather than its Offer). |
| `schema.missing_recommended` | low | An item of a rich-result type without properties Google recommends. |

A page gets one issue per rule; the message lists every finding of that
kind on it.

## Rich-result types

| Type (and subtypes) | Required | Recommended |
| --- | --- | --- |
| Product | `name`; one of `offers`, `review`, `aggregateRating`; a price on every offer; `ratingValue` and `ratingCount` or `reviewCount` on a rating; `author` and `reviewRating.ratingValue` on a review | `aggregateRating`, `review`, `offers.availability`, `offers.priceCurrency` |
| Article (NewsArticle, BlogPosting, ...) | none | `headline`, `image`, `datePublished`, `dateModified`, `author` with `name` and `url` or `sameAs` |
| BreadcrumbList | `itemListElement`, each with `position` and a `name` | none |
| Organization | none | `name`, `url`, `logo`, `description`, `sameAs`, `address`, one of `contactPoint`, `telephone`, `email` |
| LocalBusiness (Restaurant, Store, ...) | `name`, `address` | `telephone`, `url`, `geo` with `latitude` and `longitude`, `openingHoursSpecification`, `priceRange` |
| Recipe | `name`, `image` | `author`, `datePublished`, `description`, `recipeIngredient`, `recipeInstructions`, times, yield, `nutrition.calories`, ... |
| Event | `name`, `startDate`, `location` with `address` (or `url` online) | `description`, `endDate`, `eventStatus`, `image`, `offers` with price and currency, `organizer`, `performer` |
| VideoObject | `name`, `thumbnailUrl`, `uploadDate` | `contentUrl` or `embedUrl`, `description`, `duration` |

These come from Google Search Central's pages, checked 2026-10-22. Each is
linked from `src/sitecrawler/audit/richresults.py`. A subtype is checked
as its nearest ancestor in the table. FAQPage is not checked: Google
stopped showing FAQ rich results on 2026-05-07. Organization's recommended
list is a subset of Google's. Other types (WebSite, WebPage, Person, ...)
are still checked against the vocabulary, but have no rich-result needs.

## `schema report`

```text
missing_required	https://example.com/teapot	Product	offers.price or offers.priceSpecification.price or offers.lowPrice	Product needs offers.price or ...
unknown_property	https://example.com/about	WebPage	authr	authr is not a schema.org property (on WebPage)
```

There is one tab-separated line per finding: kind (the rule id without
`schema.`), URL, type, property path, message. `--kind` keeps one kind. A
table of the types found goes to stderr: items, pages, and the rich-result
type each is checked as. The last line is the summary `sitecrawler audit`
prints too: pages with items, syntaxes, type count, and pages per kind of
problem.

## In the web UI

The **Structured Data** tab has these columns: the types on each page,
the number of items, the syntaxes, and the number of problems. It has a
filter per rule plus *With* / *Without structured data*. In the detail
pane, **Structured Data** lists the page's problems and every item as
formatted JSON with its syntax and line.

## In the file and the exports

The `structured_data` table holds one row per item (`format`, `types`,
`data_json`, `line`) and one per JSON-LD block that failed to parse
(`error`). The export gains a `structured_data` sheet (`url, line, format,
types, error, json`), and the `pages` sheet ends with `structured_types`.
Crawl files written before 1.0 have no `structured_data` table and open
with an error; re-crawl.

The vocabulary is a reduced copy of schema.org shipped with the package:
each type's parents and each property's domains. Refresh it with
`uv run python scripts/update_schemaorg.py`.

Limits for now:
- Property values are not checked against their expected types (a URL
  where a date belongs passes).
- Rich-result needs are checked on top-level items only.
- Untyped nested items are not checked for unknown properties.
