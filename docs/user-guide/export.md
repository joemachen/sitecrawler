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
| `xlsx` | Sheets `pages`, `issues`, `links`, `redirects`, `hreflang`, `sitemap_urls` and `extractions`, each with a header row |
| `json` | `{"crawl": {...}, "pages": [...], "issues": [...], "links": [...], "redirects": [...], "hreflang": [...], "sitemap_urls": [...], "extractions": [...]}` |

The `pages` sheet (and JSON list) is wider than the CSV: it adds `outcome`,
`final_url`, `size_bytes`, `meta_robots`, `lang`, `x_robots_tag`,
`last_modified` and `fetched_at`. `links` has one row per anchor with its
source page, text, `rel`, `nofollow` and whether it is internal. `redirects`
has one row per hop with the page that started the chain. A crawl run with
`--extract` or `--search` adds one `extract_<name>` / `search_<name>` column
per name to `pages` and fills `extractions` (one row per page per name with
`count` and `value`); see [Custom extraction and search](extract.md).

`-o` sets the output file; the default is the database name with the
format's extension.
