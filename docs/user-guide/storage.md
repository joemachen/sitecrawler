# Storage

`--db crawl.db` keeps everything the crawler saw in one SQLite file. Open it
with any SQLite browser, or query it directly:

```bash
sqlite3 crawl.db "select url, status_code from pages where state='done' order by url"
```

One file holds exactly one crawl. That keeps every table free of a crawl id
you would otherwise have to filter on, and makes a crawl something you can
copy, email or diff.

Exports (`sitecrawler export`) read from these tables; see [Exporting](export.md).

## Tables

| Table | One row per | Notable columns |
| --- | --- | --- |
| `crawls` | crawl | `start_url`, `mode`, `config_json`, `version`, `started_at`, `finished_at`, `status` (`running`, `done`, or `stopped` when `--max-pages` cut it short or the crawl was stopped from the web UI), `pages_done` |
| `pages` | URL ever queued | `state` (`pending` / `done`), `depth`, `found_on`, `outcome`, `status_code`, `final_url`, `content_type`, `size_bytes`, `fetch_ms`, `error`, `x_robots_tag`, `last_modified`, `headers_json`, `fetched_at`; written by `audit`: `indexable`, `indexability_reason`, `inlinks`, `link_depth`, `link_score` |
| `redirect_hops` | redirect followed | `page_id`, `hop_no`, `from_url`, `to_url`, `status_code` |
| `page_html` | fetched page | `title`, `meta_description`, `meta_robots`, `canonical`, `h1`, `h1s_json`, `h2s_json`, `lang`, `word_count`, `internal_links`, `content_hash`, `simhash`, `content_words` (the main-text fingerprint, ADR-0012; NULL when the page was not parsed as HTML) |
| `page_render` | page the crawl tried to render (`--render`) | `ok`, `render_ms`, `error`, raw and rendered `title`, `meta_description`, `meta_robots`, `canonical`, `h1`, `word_count`, `link_count`, `links_added_json`, `links_removed_json` |
| `links` | anchor on a page | `page_id`, `dst_url`, `anchor_text`, `rel`, `nofollow`, `is_internal`, `position` (`header`, `nav`, `body`, `aside`, `footer`) |
| `sitemaps` | sitemap file the crawl tried to read | `url`, `found_in` (`robots.txt`, `default` or the index that listed it), `kind` (`urlset`, `index`, empty when unusable), `status_code`, `error`, `url_count` |
| `sitemap_urls` | URL in a sitemap | `sitemap_url`, `loc`, `lastmod`, `changefreq`, `priority` |

Notes:

- `pages.state` is how a crawl resumes: `pending` rows are the queue, every
  row is the "seen" set. A page in flight when the process died is still
  `pending` and is fetched again on `--resume`.
- `outcome` is `fetched`, `blocked`, `error` or `redirect_loop`; `status_code`
  is null for the last three.
- Raw HTML is not stored yet. It arrives with JavaScript rendering, when both
  the raw and the rendered document are kept.
- The file is written in WAL mode. `crawl.db-wal` and `crawl.db-shm` appear
  while it is open and disappear on a clean close.
- There are no migrations during `0.x`: `crawls.version` records the version
  that wrote the file, and an old file is simply re-crawled.
