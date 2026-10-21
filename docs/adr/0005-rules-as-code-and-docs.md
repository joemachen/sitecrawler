# ADR-0005: Audit rules are discovered classes, and their docs are generated

**Status:** Accepted
**Date:** 2026-10-21

## Context

Phase 2 adds forty-odd checks. Each needs an id, a severity, a category, an
explanation for the person fixing it, a test, and a page in the user guide.
Written separately those drift apart within weeks. The audit must also run
without touching the network (ARCHITECTURE section 2) and be re-runnable on
an old crawl file.

## Decision

- **A rule is a class** under `src/sitecrawler/audit/rules/` extending
  `Rule` (site-wide), `PageRule` (one page at a time) or `HtmlPageRule`
  (parsed HTML pages only). Class attributes `id`, `severity`, `category`,
  `summary`, `why` and `fix` carry everything the report and the docs need.
- **Rules are discovered**, not registered: `load_rules()` imports every
  module in the package and instantiates each concrete `Rule` subclass.
  Adding a rule is adding a class. Duplicate ids raise.
- **The user-guide page is generated** from those attributes by
  `scripts/gen_rule_docs.py`, and a unit test fails when the committed page is
  stale. Docs cannot describe a rule that does not exist or miss one that does.
- **Rules read a `CrawlView`**, an in-memory index over the stored pages
  (lookups by normalised URL, inlinks, groups, sitemap membership). They
  never fetch. Site-wide rules get the whole view; page rules get one page
  and the view.
- **Issues are rebuilt, not accumulated.** `audit` deletes the `issues`
  table and writes the new findings, and stores an indexability verdict
  (`indexable`, `indexability_reason`) on each page. The verdict is a fact;
  rules decide whether it is a problem.
- **Every rule has a triggering fixture page** and the rest of the fixture
  site is its non-triggering case: `tests/integration/test_audit.py` maps each
  rule id to the exact set of paths it must flag, and fails for a rule missing
  from the table.

## Consequences

- Easier: a new check is one class, one fixture page, one table row and a
  regenerated page; the Issues report and the web UI read the same
  `summary`/`why`/`fix`; 100% branch coverage on `audit/` is enforced in CI
  because the package is small and pure.
- Harder: rule modules must not have side effects at import; a very large
  site makes `CrawlView` memory-heavy (one record per page plus indexes),
  which is acceptable up to the roadmap's 10k-page target and revisited with
  the web UI.
- Alternatives considered: a YAML rule registry (duplicates the class list and
  cannot express logic); plugins via entry points (useful later for third
  parties, premature now); computing issues on the fly in the UI (slow and
  not exportable).
