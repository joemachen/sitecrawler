# ADR-0002: CLI first, local web UI from Phase 3

**Status:** Accepted
**Date:** 2026-10-21

## Context

Several must-have features ("Issues tab", filtering, page detail) imply a
graphical interface. Building a UI before there is an issues engine means
building it twice. Desktop frameworks (Qt, Electron) add a second language or
heavy packaging.

## Decision

- Phases 0-2 are command-line only, with CSV/XLSX/JSON exports as the UI.
- From Phase 3 the UI is a **local web app**: FastAPI serving Jinja2 templates
  with HTMX for interactivity and Tabulator for data grids, bound to
  127.0.0.1. `sitecrawler serve crawl.db` opens it.
- The CLI and the web UI call the same library functions. No feature exists in
  only one of them.

## Consequences

- Easier: one language; the UI is a thin read layer over SQLite; browser tabs
  map naturally to "tabs" in the tool; trivial to test with Playwright.
- Harder: not a double-click desktop app. Revisit packaging (PyInstaller,
  Tauri shell) if non-technical users need it.
- Alternatives considered: Streamlit (fast but poor for large sortable tables
  and multi-tab state); React SPA (better grids, but a second toolchain for a
  solo developer); desktop Qt (packaging burden, no benefit for local use).
