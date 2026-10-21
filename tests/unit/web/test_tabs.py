"""The tab and filter specs are consistent with the rules and the row builder."""

from __future__ import annotations

import pytest

from sitecrawler.audit import load_rules
from sitecrawler.models import LinkRef
from sitecrawler.web.rows import NO_AUDIT, base_row, external_rows
from sitecrawler.web.tabs import ALL, TABS, FilterSpec, matches, rule_filters, tab_by_id, to_json
from tests.unit.audit.helpers import links, page


def test_tab_and_filter_ids_are_unique_and_every_tab_starts_with_all() -> None:
    assert len({t.id for t in TABS}) == len(TABS)
    for tab in TABS:
        assert tab.filters[0] is ALL, tab.id
        assert len({f.id for f in tab.filters}) == len(tab.filters), tab.id


def test_every_rule_filter_names_a_real_rule_and_most_rules_have_a_filter() -> None:
    known = {r.id for r in load_rules()}
    used = {f.rule for _, f in rule_filters()}
    assert used <= known
    # Response-code rules are reached through the status-class filters instead.
    assert known - used <= {
        "response.4xx",
        "response.5xx",
        "response.error",
        "response.blocked_by_robots",
    }


def test_every_filter_column_is_produced_by_the_row_builder() -> None:
    row = {**base_row(page("/", links=links("/a"))), **NO_AUDIT}
    external = external_rows([page("/", links=(LinkRef("https://o.test/x", "x"),))])
    for tab in TABS:
        if tab.source == "issues":
            continue
        produced = set(row) if tab.source == "pages" else set(external[0]) if external else set()
        for f in tab.filters:
            if f.op is not None:
                assert f.column in produced, f"{tab.id}/{f.id} reads {f.column}"
        for column in tab.columns:
            assert column in produced, f"{tab.id} shows {column}"


@pytest.mark.parametrize(
    ("spec", "row", "expected"),
    [
        (ALL, {}, True),
        (FilterSpec("x", "", "n", "eq", 3), {"n": 3}, True),
        (FilterSpec("x", "", "n", "eq", 3), {"n": 4}, False),
        (FilterSpec("x", "", "n", "ne", 3), {"n": 4}, True),
        (FilterSpec("x", "", "d", "has", "index"), {"d": "noindex follow"}, False),
        (FilterSpec("x", "", "d", "has", "index"), {"d": "index follow"}, True),
        (FilterSpec("x", "", "rules", "has", "title.missing"), {"rules": ["title.missing"]}, True),
        (FilterSpec("x", "", "rules", "has", "title.missing"), {"rules": []}, False),
        (FilterSpec("x", "", "n", "gt", 0), {"n": 1}, True),
        (FilterSpec("x", "", "n", "gt", 0), {"n": 0}, False),
        (FilterSpec("x", "", "n", "gt", 0), {"n": None}, False),
        (FilterSpec("x", "", "b", "truthy"), {"b": True}, True),
        (FilterSpec("x", "", "b", "truthy"), {}, False),
        (FilterSpec("x", "", "b", "falsy"), {"b": False}, True),
        (FilterSpec("x", "", "b", "falsy"), {"b": "yes"}, False),
    ],
)
def test_matches_per_operator(spec: FilterSpec, row: dict[str, object], expected: bool) -> None:
    assert matches(row, spec) is expected  # type: ignore[arg-type]


def test_json_specs_carry_everything_the_browser_needs() -> None:
    data = to_json()
    assert [d["id"] for d in data] == [t.id for t in TABS]
    titles = next(d for d in data if d["id"] == "titles")
    assert titles["source"] == "pages"
    filters = titles["filters"]
    assert isinstance(filters, list)
    assert filters[1] == {
        "id": "missing",
        "label": "Missing",
        "column": "rules",
        "op": "has",
        "value": "title.missing",
        "rule": "title.missing",
    }


def test_tab_by_id() -> None:
    assert tab_by_id("h1") is not None
    assert tab_by_id("nope") is None
