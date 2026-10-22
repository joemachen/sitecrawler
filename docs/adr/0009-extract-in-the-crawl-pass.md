# ADR-0009: Run custom extractors in the crawl pass, over the HTML already in hand

**Status:** Accepted
**Date:** 2026-10-22

## Context

Phase 6 adds `--extract` (CSS, XPath or regex extractors with a name) and
`--search` (a pattern every page is checked for). Both must see the page as
the crawl saw it: the rendered DOM when `--render` is on and the render
succeeded, the raw HTML otherwise. ADR-0008 decided not to store either HTML
body, so there is nothing in the file to extract from after the fact. Two
ways out: run the extractors inside the crawl, where
`Crawler._fetch_and_parse` holds the text that produced the page record, or
start storing the bodies behind a flag and extract from the store. The
package rules in `CLAUDE.md` still apply: `crawl/` never parses HTML and
`parse/` never does I/O.

## Decision

- **Extract during the crawl.** `Crawler._fetch_and_parse` hands the text it
  parsed the page from (the rendered DOM or the raw HTML) to pure functions
  in `parse/extract.py`, which return one `Extraction` per extractor and
  per search. The crawler stores them on the `PageRecord`; the store writes
  them to a new `extractions` table. Reason in one line: the HTML is in hand
  exactly once, so extracting there costs a few milliseconds per page and
  nothing on disk, while storing bodies would multiply every file by the
  page weight to buy re-extraction that nobody has asked for yet.
- **The HTML bodies stay unstored.** Changing an extractor means crawling
  again. That is the trade: a crawl file stays a few megabytes, and list
  mode (`sitecrawler list urls.txt --extract ...`) re-fetches just the pages
  of interest in seconds. Storing bodies behind a flag remains the obvious
  next step if re-extraction is ever wanted, and nothing here prevents it.
- **lxml with cssselect replaces BeautifulSoup** as the HTML parser, as
  decided earlier in the handoff. One library now parses the page for the
  audit fields and evaluates CSS selectors and XPath expressions, and a bad
  selector or expression fails when the crawl is configured, before the
  first request, the same way a bad `--render` setup does.
- **One grammar everywhere.** An extractor is
  `NAME=KIND[MODIFIERS]:EXPRESSION` on the command line and a table with the
  same keys in TOML; a search is `[NAME=]PATTERN`. Results, columns and
  filters are named after the extractor (`extract_<name>`, `search_<name>`),
  so they can never shadow a built-in column such as `title`.

## Consequences

- Easier: one code path for raw and rendered pages, no new storage format,
  the web UI and the exports read the same `extractions` rows as everything
  else, and a stored crawl opened read-only shows its custom columns without
  knowing the extractor configuration.
- Harder: extractors cannot be added to a finished crawl; the file does not
  hold the HTML. The `pages` export and the Pages grid gain columns whose
  names depend on the crawl, so readers derive them from the data rather
  than from a constant.
- Alternatives considered: store raw and rendered bodies behind a flag and
  run an `extract` command over the store (file size, and a second
  extraction path that the live UI could not share); run extraction in
  `audit` (no HTML to read there); render on demand for extraction only
  (would re-fetch what the crawl already fetched, and lose the raw-vs-
  rendered guarantee of ADR-0008).
