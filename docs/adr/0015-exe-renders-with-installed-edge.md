# ADR-0015: The exe bundles Playwright and renders with the installed Edge

**Status:** Accepted
**Date:** 2026-10-28

## Context

ADR-0014 left Playwright out of the exe because rendering needs a Chromium
download (about 150 MB) that a single file cannot carry. That made
*Render JavaScript* useless in the exe: the only way to render was a
second install of sitecrawler with uv, Playwright and Chromium, which is
what the exe was meant to spare the user.

Playwright can also drive a Chromium-based browser that is already
installed, through `launch(channel=...)`. Microsoft Edge is Chromium-based
and ships with Windows 10 and 11, the only platforms the exe is built for.

## Decision

- **The renderer falls back to Edge.** `Renderer.__aenter__` launches
  Playwright's own Chromium first. When that fails (it was never
  downloaded), it launches `channel="msedge"`. When both fail, the crawl
  stops before any request with a `RenderUnavailableError` naming both
  errors. The fallback is not exe-specific: a checkout or `pip` install
  without `playwright install chromium` renders with Edge too.
- **The exe bundles Playwright** (`packaging/sitecrawler.spec`): its
  modules, and its driver (`node.exe` and the Node package) as data files,
  which Playwright finds beside its own modules. No Chromium is bundled.
- **The exe's hint names Edge.** Inside the frozen exe, a failed launch
  says to install Edge or untick Render JavaScript, not to run `uv` or
  `pip`.

## Consequences

- Easier: Render JavaScript works in the exe with nothing else to install.
- Harder: the exe grows from about 30 MB to about 70 MB, and each launch
  unpacks the driver too, so start-up is a little slower. Rendered pages
  come from whatever Edge version the machine has, not Playwright's pinned
  Chromium, so results can drift slightly between machines; Edge updates
  itself, so it stays close to current Chromium.
- Alternatives considered:
  - Download Chromium on first use from inside the exe: a 150 MB download
    and a progress UI, for a browser the machine already has.
  - Keep rendering out of the exe and document a second install: what the
    exe existed to avoid.
  - Bundle Chromium in an `--onedir` build: a 250 MB folder instead of the
    single exe asked for.
