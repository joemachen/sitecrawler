# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Every redirect hop (from, to, status) is recorded on each page record, and
  response headers plus body size are kept.
- `redirect_loop` status: a chain that revisits a URL or exceeds
  `--max-redirects` (default 10) stops after at most that many requests
  instead of timing out.
- `--max-redirects` and `--no-http2` options on `crawl`.
- Project scaffold: uv, ruff, mypy strict, pytest, pre-commit, GitHub Actions CI.
- `sitecrawler crawl URL` command ported from the original single-file crawler:
  sitemap seeding, robots.txt, breadth-first link following, CSV export.
- Fixture site under `tests/fixtures/site/` and unit/integration/e2e tests.
- Planning docs: development process, architecture, roadmap, ADRs.

### Changed

- HTTP is now `httpx` on `asyncio` with HTTP/2 instead of `requests` in a
  thread pool. `--delay` applies per host rather than globally. Bodies with no
  declared charset are decoded as UTF-8. `Crawler.arun()` is available for
  callers that already run an event loop.

### Removed

- The `requests` dependency.
