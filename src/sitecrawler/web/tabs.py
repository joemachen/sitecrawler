"""The tab strip and each tab's filters, as data.

A tab is a column list over one row source; a filter is one test on one
column of a row. Rule filters test the ``rules`` column (the audit rule ids
that flagged the page), so Page Titles > Missing is exactly ``title.missing``
and its count matches the audit. The same specs are rendered into the page
as JSON and evaluated by a few lines of JavaScript; :func:`matches` is the
Python twin, used for the summary counts and as the test oracle.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Literal

from sitecrawler.store.dump import Cell

Op = Literal["eq", "ne", "has", "gt", "truthy", "falsy"]
"""How a filter compares its column: equal, not equal, contains a token or
list item, greater than, truthy, falsy."""

Source = Literal["pages", "external", "issues"]
"""What a tab lists: crawled pages, external link targets, or the rule table."""

Value = Cell | list[str]
"""A cell as the grid sees it; ``rules`` is a list of rule ids."""

Row = dict[str, Value]
"""One grid row: column name to cell value, as the JSON endpoints send it."""


@dataclass(slots=True, frozen=True)
class FilterSpec:
    """One entry of a tab's filter dropdown."""

    id: str
    label: str
    column: str = ""
    """Column the test reads; empty for the ``All`` filter."""
    op: Op | None = None
    value: Cell = None
    rule: str = ""
    """The audit rule id when this filter is one; shown as a link in the UI."""

    @classmethod
    def for_rule(cls, id: str, label: str, rule: str) -> FilterSpec:
        """A filter that keeps the pages ``rule`` flagged."""
        return cls(id, label, "rules", "has", rule, rule)


ALL = FilterSpec("all", "All")


@dataclass(slots=True, frozen=True)
class TabSpec:
    """One tab of the strip."""

    id: str
    label: str
    columns: tuple[str, ...]
    filters: tuple[FilterSpec, ...] = (ALL,)
    source: Source = "pages"
    titles: dict[str, str] = field(default_factory=dict)
    """Column headers that differ from the column name (the Custom tab's extractor names)."""


def matches(row: Row, spec: FilterSpec) -> bool:
    """True when ``row`` passes ``spec``. Missing columns count as ``None``."""
    if spec.op is None:
        return True
    cell = row.get(spec.column)
    if spec.op == "eq":
        return cell == spec.value
    if spec.op == "ne":
        return cell != spec.value
    if spec.op == "has":
        tokens = cell if isinstance(cell, list) else str(cell or "").split()
        return spec.value in tokens
    if spec.op == "gt":
        return (
            isinstance(cell, int | float)
            and isinstance(spec.value, int | float)
            and cell > spec.value
        )
    if spec.op == "truthy":
        return bool(cell)
    return not cell


def to_json(tabs: tuple[TabSpec, ...] = ()) -> list[dict[str, object]]:
    """The specs as plain dicts for the page's ``<script type="application/json">``."""
    return [
        {**asdict(tab), "columns": list(tab.columns), "filters": [asdict(f) for f in tab.filters]}
        for tab in (tabs or TABS)
    ]


def tab_by_id(tab_id: str) -> TabSpec | None:
    """The tab with ``tab_id``, or None."""
    return next((t for t in TABS if t.id == tab_id), None)


CUSTOM = "custom"
"""Id of the Custom tab, whose columns depend on the crawl."""


def custom_tab(extractions: Sequence[tuple[str, str]] = ()) -> TabSpec:
    """The Custom tab for a crawl that extracted or searched for these ``(name, kind)`` pairs.

    One column per name (the extracted value, or True/False for a search) and
    a found / not-found filter pair each; with nothing configured it lists
    URLs only. A page the extractors never ran on (not HTML) passes neither
    filter of a pair.
    """
    columns = ["url"]
    filters = [ALL]
    titles: dict[str, str] = {}
    for name, kind in extractions:
        if kind == "search":
            column = f"search_{name}"
            filters.append(_F(f"has:{name}", f"{name}: contains", column, "truthy"))
            filters.append(_F(f"not:{name}", f"{name}: does not contain", column, "eq", False))
        else:
            column = f"extract_{name}"
            filters.append(_F(f"has:{name}", f"{name}: found", f"{column}_n", "gt", 0))
            filters.append(_F(f"not:{name}", f"{name}: not found", f"{column}_n", "eq", 0))
        columns.append(column)
        titles[column] = name
    columns += ["status_code", "indexable"]
    return TabSpec(CUSTOM, "Custom", tuple(columns), tuple(filters), titles=titles)


def with_custom(extractions: Sequence[tuple[str, str]]) -> tuple[TabSpec, ...]:
    """The tab strip with the Custom tab built for ``extractions``."""
    return tuple(custom_tab(extractions) if tab.id == CUSTOM else tab for tab in TABS)


def rule_filters() -> list[tuple[TabSpec, FilterSpec]]:
    """Every (tab, filter) pair that is backed by an audit rule."""
    return [(tab, f) for tab in TABS for f in tab.filters if f.rule]


_R = FilterSpec.for_rule
_F = FilterSpec

TABS: tuple[TabSpec, ...] = (
    TabSpec(
        "internal",
        "Internal",
        (
            "url",
            "content_type",
            "status_code",
            "status",
            "indexable",
            "indexability_reason",
            "title",
            "title_length",
            "meta_description",
            "meta_length",
            "h1",
            "h1_count",
            "canonical",
            "word_count",
            "inlinks",
            "outlinks",
            "depth",
            "size_bytes",
            "fetch_ms",
            "issues_n",
        ),
        (
            ALL,
            _F("html", "HTML", "content_class", "eq", "html"),
            _F("other", "Other content", "content_class", "eq", "other"),
            _F("indexable", "Indexable", "indexable", "truthy"),
            _R("non_indexable", "Non-indexable", "page.non_indexable"),
        ),
    ),
    TabSpec(
        "external",
        "External",
        ("url", "inlinks", "nofollow_inlinks", "first_found_on"),
        (ALL, _F("nofollow_only", "Only nofollow links", "nofollow_only", "truthy")),
        source="external",
    ),
    TabSpec(
        "response_codes",
        "Response Codes",
        (
            "url",
            "first_status",
            "status_code",
            "status",
            "outcome",
            "final_url",
            "redirect_hops",
            "error",
            "content_type",
            "indexable",
        ),
        (
            ALL,
            _F("2xx", "Success (2xx)", "status_class", "eq", "2xx"),
            _F("3xx", "Redirection (3xx)", "status_class", "eq", "3xx"),
            _F("4xx", "Client error (4xx)", "status_class", "eq", "4xx"),
            _F("5xx", "Server error (5xx)", "status_class", "eq", "5xx"),
            _F("blocked", "Blocked by robots.txt", "status_class", "eq", "blocked"),
            _F("no_response", "No response", "status_class", "eq", "no_response"),
            _R("redirect_chain", "Redirect chain", "redirect.chain"),
            _R("redirect_loop", "Redirect loop", "redirect.loop"),
            _R("redirect_to_error", "Redirect to error", "redirect.to_error"),
            _R("redirect_off_site", "Redirect off-site", "redirect.off_site"),
            _R("redirect_temporary", "Temporary redirect", "redirect.temporary"),
        ),
    ),
    TabSpec(
        "url",
        "URL",
        ("url", "url_length", "url_flags", "status_code", "indexable"),
        (
            ALL,
            _F("non_ascii", "Non-ASCII characters", "url_flags", "has", "non_ascii"),
            _F("uppercase", "Uppercase", "url_flags", "has", "uppercase"),
            _F("underscores", "Underscores", "url_flags", "has", "underscores"),
            _F("parameters", "Parameters", "url_flags", "has", "parameters"),
            _F("long", "Over 115 characters", "url_flags", "has", "long"),
        ),
    ),
    TabSpec(
        "titles",
        "Page Titles",
        ("url", "title", "title_length", "title_count", "h1", "status_code", "indexable"),
        (
            ALL,
            _R("missing", "Missing", "title.missing"),
            _R("duplicate", "Duplicate", "title.duplicate"),
            _R("too_long", "Over 60 characters", "title.too_long"),
            _R("too_short", "Too short", "title.too_short"),
            _R("multiple", "Multiple", "title.multiple"),
            _R("same_as_h1", "Same as H1", "title.same_as_h1"),
        ),
    ),
    TabSpec(
        "meta",
        "Meta Description",
        (
            "url",
            "meta_description",
            "meta_length",
            "meta_description_count",
            "status_code",
            "indexable",
        ),
        (
            ALL,
            _R("missing", "Missing", "meta_description.missing"),
            _R("duplicate", "Duplicate", "meta_description.duplicate"),
            _R("too_long", "Over 155 characters", "meta_description.too_long"),
            _R("too_short", "Too short", "meta_description.too_short"),
            _R("multiple", "Multiple", "meta_description.multiple"),
        ),
    ),
    TabSpec(
        "h1",
        "H1",
        ("url", "h1", "h1_length", "h1_count", "title", "status_code", "indexable"),
        (
            ALL,
            _R("missing", "Missing", "h1.missing"),
            _R("multiple", "Multiple", "h1.multiple"),
            _R("duplicate", "Duplicate", "h1.duplicate"),
            _R("too_long", "Over 70 characters", "h1.too_long"),
        ),
    ),
    TabSpec(
        "h2",
        "H2",
        ("url", "h2", "h2_count", "h1", "status_code", "indexable"),
        (ALL, _R("missing", "Missing", "h2.missing")),
    ),
    TabSpec(
        "canonicals",
        "Canonicals",
        (
            "url",
            "canonical",
            "canonical_header",
            "canonical_kind",
            "og_url",
            "status_code",
            "indexable",
            "indexability_reason",
        ),
        (
            ALL,
            _F("contains", "Contains canonical", "has_canonical", "truthy"),
            _F("self", "Self-referencing", "canonical_kind", "eq", "self"),
            _R("canonicalised", "Canonicalised", "canonical.not_self_referencing"),
            _R("missing", "Missing", "canonical.missing"),
            _R("to_non_200", "To non-200", "canonical.to_non_200"),
            _R("off_site", "Off-site", "canonical.off_site"),
            _R("chain", "Chain", "canonical.chain"),
            _R("conflict", "Conflicting", "canonical.conflict"),
            _R("og_url_mismatch", "og:url mismatch", "canonical.og_url_mismatch"),
            _R("linked", "Canonicalised but linked", "canonical.canonicalised_but_linked"),
        ),
    ),
    TabSpec(
        "pagination",
        "Pagination",
        ("url", "rel_prev", "rel_next", "canonical", "status_code", "indexable"),
        (
            ALL,
            _F("contains", "Contains pagination", "paginated", "truthy"),
            _R("to_non_200", "To non-200", "pagination.to_non_200"),
            _R("canonical_to_first", "Canonical to first page", "pagination.canonical_to_first"),
            _R("broken_sequence", "Broken sequence", "pagination.broken_sequence"),
        ),
    ),
    TabSpec(
        "directives",
        "Directives",
        ("url", "directives", "meta_robots", "x_robots_tag", "indexable", "indexability_reason"),
        (
            ALL,
            _F("index", "Index", "directives", "has", "index"),
            _R("noindex", "Noindex", "robots.noindex"),
            _F("follow", "Follow", "directives", "has", "follow"),
            _R("nofollow", "Nofollow", "robots.nofollow"),
            _R("none", "None", "robots.none"),
            _R("conflicting", "Conflicting", "robots.conflicting"),
            _R("noindex_linked", "Noindex but linked", "robots.noindex_linked"),
            _R("blocked_linked", "Blocked but linked", "robots.blocked_but_linked"),
        ),
    ),
    TabSpec(
        "hreflang",
        "Hreflang",
        ("url", "lang", "hreflang_count", "hreflang_langs", "status_code", "indexable"),
        (
            ALL,
            _F("contains", "Contains hreflang", "hreflang_count", "gt", 0),
            _R("invalid_lang", "Invalid language code", "hreflang.invalid_lang"),
            _R("missing_self", "Missing self reference", "hreflang.missing_self"),
            _R("missing_x_default", "Missing x-default", "hreflang.missing_x_default"),
            _R("missing_return", "Missing return link", "hreflang.missing_return_link"),
            _R("to_non_200", "To non-200", "hreflang.to_non_200"),
            _R("to_non_canonical", "To non-canonical", "hreflang.to_non_canonical"),
        ),
    ),
    TabSpec(
        "links",
        "Links",
        (
            "url",
            "inlinks",
            "outlinks",
            "outlinks_internal",
            "outlinks_external",
            "nofollow_outlinks",
            "internal_links",
            "status_code",
        ),
        (
            ALL,
            _F("no_inlinks", "No inlinks", "inlinks", "eq", 0),
            _R("to_redirect", "Links to redirects", "link.to_redirect"),
            _F("nofollow_outlinks", "Has nofollow outlinks", "nofollow_outlinks", "gt", 0),
        ),
    ),
    TabSpec(
        "sitemaps",
        "Sitemaps",
        ("url", "in_sitemap", "indexable", "indexability_reason", "status_code"),
        (
            ALL,
            _F("in_sitemap", "In sitemap", "in_sitemap", "truthy"),
            _F("not_in_sitemap", "Not in sitemap", "in_sitemap", "falsy"),
            _F(
                "non_indexable_in_sitemap",
                "Non-indexable in sitemap",
                "non_indexable_in_sitemap",
                "truthy",
            ),
            _R("noindex_in_sitemap", "Noindex in sitemap", "robots.noindex_in_sitemap"),
        ),
    ),
    TabSpec(
        "javascript",
        "JavaScript",
        (
            "url",
            "render_status",
            "render_changes",
            "title",
            "raw_title",
            "canonical",
            "raw_canonical",
            "outlinks",
            "render_ms",
            "render_error",
        ),
        (
            ALL,
            _F("rendered", "Rendered", "render_status", "eq", "rendered"),
            _F("same", "Same as raw HTML", "render_same", "truthy"),
            _R("differs", "Changed by JavaScript", "render.differs"),
            _R("failed", "Render failed", "render.failed"),
        ),
    ),
    custom_tab(),
    TabSpec("issues", "Issues", ("rule_id", "severity", "count"), (ALL,), source="issues"),
)
"""The tab strip, in display order."""
