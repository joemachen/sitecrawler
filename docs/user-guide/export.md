# Exporting a crawl

Once a crawl is stored with `--db` it can be exported any number of times
without touching the site again:

```bash
uv run sitecrawler export crawl.db                   # crawl.csv, the pages table
uv run sitecrawler export crawl.db --format xlsx     # crawl.xlsx, one sheet per table
uv run sitecrawler export crawl.db --format json -o out.json
```

| Format | Contents |
| --- | --- |
| `csv` | The pages table with the same columns as `crawl -o`, see [Crawling a site](crawl.md#csv-columns) |
| `xlsx` | Sheets `pages`, `issues`, `links`, `redirects`, `hreflang`, `sitemaps`, `sitemap_urls` and `extractions`, each with a header row |
| `json` | `{"crawl": {...}, "pages": [...], "issues": [...], "links": [...], "redirects": [...], "hreflang": [...], "sitemaps": [...], "sitemap_urls": [...], "extractions": [...]}` |

The `pages` sheet (and JSON list) is wider than the CSV: it adds `outcome`,
`final_url`, `size_bytes`, `meta_robots`, `lang`, `x_robots_tag`,
`last_modified`, `fetched_at` and, once `audit` has run, `inlinks`,
`link_depth` and `link_score` (see [Internal linking](links.md)), then the
content fingerprint `content_words`, `content_hash`, `simhash` (see
[Duplicate content](duplicates.md)). `links`
has one row per anchor with its source page, text, `rel`, `nofollow`,
whether it is internal and its `position` on the page. `redirects`
has one row per hop with the page that started the chain. `sitemaps` has one
row per sitemap file the crawl tried (`url`, `found_in`, `kind`,
`status_code`, `url_count`, `error`) and `sitemap_urls` one row per entry
with its `lastmod`, `changefreq` and `priority`; see [Sitemaps](sitemaps.md)
for the sitemap the crawl can write. A crawl run with
`--extract` or `--search` adds one `extract_<name>` / `search_<name>` column
per name to `pages` and fills `extractions` (one row per page per name with
`count` and `value`); see [Custom extraction and search](extract.md).

`-o` sets the output file; the default is the database name with the
format's extension.
