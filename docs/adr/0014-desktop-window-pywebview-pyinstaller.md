# ADR-0014: The desktop app is the web UI in a pywebview window, packed into one exe by PyInstaller

**Status:** Accepted
**Date:** 2026-10-23

## Context

The UI runs in the user's browser: `serve` (or `run.bat`) starts a server
and opens a tab. That needs uv, a checkout and a terminal window left open.
The owner wants a standalone Windows exe that opens as its own window, not
in a browser. ADR-0002 left this open: "revisit packaging (PyInstaller,
Tauri shell) if non-technical users need it".

The UI is about 2,700 lines of templates, JavaScript, CSS and FastAPI routes over htmx and Tabulator, with a
Playwright e2e suite. Rewriting it in a native toolkit would mean two UIs,
or throwing away a tested one.

## Decision

- **The window is pywebview** (`sitecrawler.web.desktop`). It hosts the
  same FastAPI app in a native window, using Edge WebView2 on Windows,
  which ships with Windows 11. The server listens on a loopback port that
  the OS picks: the socket is bound before the server thread starts, so
  there is no race and no clash with a running `serve`. Closing the window
  stops the server, and the app's lifespan stops any running crawl.
- **`sitecrawler desktop [DB]`** opens the window from a checkout, so the
  module stays reachable from the CLI. pywebview is an optional `desktop`
  extra (and in the dev group), the same pattern as `render`.
- **The exe is a PyInstaller one-file, windowed build**
  (`packaging/sitecrawler.spec` → `dist/sitecrawler.exe`, about 30 MB).
  Its only argument is an optional crawl file, which is what Windows
  passes when a `.db` is dropped on the exe. Crawls go to `crawls\` beside
  the exe, because a double-clicked exe's working directory can be
  anywhere. Errors appear in a message box. stdout and stderr, which a
  windowed exe lacks, go to `sitecrawler.log` beside the exe.
- **Playwright is excluded from the exe.** Rendering needs a separate
  Chromium download that a single file cannot carry. Ticking *Render
  JavaScript* in the exe reports the install hint, as it does in a
  checkout without the `render` extra.

## Consequences

- Easier: one UI and one test suite. The exe is the browser UI without
  the browser, so every feature lands in both at once. Building the exe
  is one command.
- Harder: the app depends on WebView2's engine version. One difference
  has already shown up: a closed `<details>` whose body has an author
  `display` stays visible in WebView2, so `app.css` hides it explicitly.
  A one-file exe unpacks itself to a temporary folder on every launch,
  so start-up takes a few seconds. The exe is unsigned, so SmartScreen
  warns on first run on another machine.
- Alternatives considered:
  - Tauri or Electron shell: a second toolchain (Rust or Node) to wrap
    the same pages.
  - Qt (PySide6) native UI: a rewrite, and a 100 MB+ build.
  - `--onedir` build: faster start, but a folder, not the single exe
    asked for.
