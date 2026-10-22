# Custom extraction and search

```bash
uv run sitecrawler crawl https://shop.example --db shop.db \
  --extract "price=css:.price" \
  --extract "sku=xpath://*[@data-sku]/@data-sku" \
  --extract "ga=regex:gtag\('config',\s*'(G-[A-Z0-9]+)'\)" \
  --search "gtag=G-[A-Z0-9]{6,}"
uv run sitecrawler export shop.db --format xlsx
```

The audit knows about titles, metas and links. Anything else you want off
every page of a site (a price, a SKU, an author, a tag manager id, the text
of a banner) is a **custom extractor**: a named CSS selector, XPath
expression or regular expression that runs on every HTML page the crawl
fetches. A **custom search** is simpler: a pattern, and a yes/no per page
for whether its HTML contains it, so `--search` is the way to list the pages
that are missing something.

Both run during the crawl on the HTML the crawler parsed the page from: the
raw response, or the rendered DOM when `--render` is on and the render
succeeded (ADR-0009). They never run on pages that are not HTML (errors, 4xx
and 5xx, files), and the results are stored with the crawl, so exports and
the web UI show them without crawling again. Changing an extractor does mean
crawling again; [list mode](list-mode.md) re-fetches just the pages you care
about.

## Extractors

An extractor on the command line is `NAME=KIND:EXPRESSION`, repeatable.
Quote it; selectors and patterns are full of shell characters.

| Kind | Expression | Example |
| --- | --- | --- |
| `css` | A CSS selector (what `document.querySelectorAll` takes) | `price=css:.product .price` |
| `xpath` | An XPath 1.0 expression. Attributes and `text()` come back as strings, `count()` as a number | `sku=xpath://*[@data-sku]/@data-sku` |
| `regex` | A Python regular expression run over the HTML source. The first capture group is the value, or the whole match when there is none | `ga=regex:G-[A-Z0-9]{6,}` |

`NAME` is letters, digits, `_` and `-`, and must be unique across extractors
and searches. It names the column: `extract_price`, `extract_sku`.

### Modifiers

What to keep from a matched element goes in square brackets after the kind,
comma-separated:

| Modifier | Effect |
| --- | --- |
| `text` | The element's visible text, whitespace collapsed. The default |
| `html` | The element's inner HTML |
| `attr=NAME` | One attribute of the element, e.g. `attr=href`, `attr=content` |
| `all` | Every match, joined with ` | `, instead of the first one only |
| `first` | The first match only. The default |

```bash
--extract "images=css[attr=src,all]:img"          # every image URL
--extract "intro=css[html]:article > p:first-child"
--extract "author=xpath[attr=content]://meta[@name='author']"
--extract "headings=xpath[all]://h2/text()"
```

A regex extractor only has `text` and `all`; `html` and `attr` do not apply
to it. An element with no text (or no such attribute) is not a match, so
`extract_price` is empty on a page where `.price` exists but is blank.

### From a TOML file

`--extract-file extract.toml` reads any number of extractors and searches
from one file; `--extract` and `--search` on the same command line are added
after it. Each entry is a table with the kind as a key, or a string in the
command-line form after the `=`:

```toml
[extract.price]
css = ".price"

[extract.images]
css = "img"
attr = "src"       # implies mode = "attr"
all = true

[extract.intro]
xpath = "//article/p[1]"
mode = "html"      # text (default), html or attr

[extract]
sku = "xpath://*[@data-sku]/@data-sku"   # the command-line form

[search]
gtag = "G-[A-Z0-9]{6,}"

[search.consent]
pattern = "cookie-banner"
```

A bad selector, expression or pattern, an unknown key or a name used twice
is reported before the first request is made, with exit status 2.

## Searches

`--search PATTERN` is a regular expression matched case-insensitively against
the HTML source of every page, so it finds text and markup alike. Name it
with `NAME=PATTERN`; an unnamed search is called `search` (then `search2`,
`search3`). Its column, `search_<name>`, is `True` or `False` per HTML page
and empty for pages that are not HTML.

```bash
--search "gtag=G-[A-Z0-9]{6,}"        # Google Analytics 4 measurement id
--search "consent=cookie-banner"      # a class name
--search "lorem ipsum"                # placeholder copy, named search
```

The crawl summary prints one line per search: how many HTML pages contain it
and how many do not. The pages that do not are the ones to look at; filter
the column in a spreadsheet, or use the web UI's **Custom** tab.

## Where the results show up

- **CSV** (`crawl -o`, `export`): one column per extractor and search after
  the fixed columns, in the order they were given.
- **XLSX and JSON** (`export`): the same columns on `pages`, plus an
  `extractions` table with one row per page per name: `url`, `name`,
  `kind`, `count` (how many matches the page had, whether or not `all`
  kept them) and `value`.
- **Web UI**: a **Custom** tab with one column per extractor and search and
  a filter pair per name (*found* / *not found*, *contains* / *does not
  contain*), and a **Custom** section in the detail pane with every
  extractor's matches for the selected page. In **Settings**, the
  **Extract** and **Search** boxes take one entry per line in the
  command-line form, so a crawl started from the browser can extract too.
- **Python**: `PageRecord.extractions`, a tuple of `Extraction` records
  (`name`, `kind`, `values`, `count`), and `Store.extraction_columns()`.
