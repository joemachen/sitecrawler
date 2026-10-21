# Browsing a crawl

```bash
uv run sitecrawler crawl https://example.com --db example.db
uv run sitecrawler audit example.db
uv run sitecrawler serve example.db
```

`serve` loads a stored crawl into memory and opens the local web UI at
`http://127.0.0.1:8765` in your browser. It only ever listens on loopback
and has no login: it is a viewer for files on your own machine, not a
service. Stop it with Ctrl+C.

Run `audit` first. Without stored issues the Overview says so, and the
issue counts are zero until you audit and restart `serve`.

| Option | Meaning |
| --- | --- |
| `--port 8765` | Listen on another port, still on 127.0.0.1 |
| `--no-open` | Print the URL instead of opening a browser |

## Tabs

| Tab | Shows |
| --- | --- |
| Overview | Crawl summary, page counts by status and depth, issue totals by severity, indexable vs. non-indexable |
| Pages | Every column of every fetched page in a grid |

Grids are sortable (click a header) and filterable (type in the header
boxes, or in the search box to match any column). **Download CSV** writes
the rows that are currently shown, filters applied, to your downloads
folder.

The UI reads the file once at start; to see a new crawl or a fresh audit,
restart `serve`. Everything it shows is also in the [exports](export.md).
