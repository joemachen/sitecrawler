# List mode

Fetch exactly the URLs you give it, instead of spidering a site:

```bash
uv run sitecrawler list urls.txt -o pages.csv
cat urls.txt | uv run sitecrawler list - --db list.db
```

`urls.txt` has one URL per line. Blank lines and lines starting with `#` are
ignored, duplicates are dropped, and the URLs may be on any number of hosts.
An invalid line stops the command before any request is made.

Each URL is fetched (with redirects followed and recorded), parsed and
reported exactly like a crawled page, with `found_on` set to `list` and
`depth` 0. Sitemaps are never read. `robots.txt` is honoured per host, and
`--delay` applies per host, so a list spanning ten sites runs ten times
faster than a list on one.

## Following links

By default no links are followed. With `--follow` the crawler also queues the
links it finds, but only on the hosts that appear in your list, so a list of
two sites never wanders into a third.

## Options

The same as [crawl](crawl.md) except there is no `--no-sitemap` (list mode
never reads sitemaps), plus:

| Flag | Default | Purpose |
| --- | --- | --- |
| `--follow` | off | Also follow links found on the listed pages, staying on the listed hosts |

`--db` and `--resume` work as for `crawl`; the stored crawl has `mode = list`.
