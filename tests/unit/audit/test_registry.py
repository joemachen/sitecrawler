import re
from pathlib import Path

import pytest

import sitecrawler.audit.rules as rules_package
from sitecrawler.audit import load_rules, rule_by_id
from sitecrawler.audit.docs import render_rules_page

ID_PATTERN = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def test_rules_are_discovered_sorted_and_well_formed() -> None:
    rules = load_rules()
    ids = [r.id for r in rules]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    for rule in rules:
        assert ID_PATTERN.match(rule.id), rule.id
        assert rule.summary
        assert rule.why
        assert rule.fix
        assert rule.category
        assert not rule.summary.endswith("."), rule.id


def test_rule_by_id() -> None:
    assert rule_by_id("response.4xx") is not None
    assert rule_by_id("nope.nope") is None


def test_duplicate_ids_are_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "dup_rule.py").write_text(
        "from sitecrawler.audit.rules.response import ClientError\n"
        "class Dup(ClientError):\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rules_package, "__path__", [*rules_package.__path__, str(tmp_path)])
    with pytest.raises(ValueError, match="duplicate rule id"):
        load_rules()


def test_rules_page_lists_every_rule() -> None:
    rules = load_rules()
    text = render_rules_page(rules)
    for rule in rules:
        assert f"### `{rule.id}`" in text
        assert f"## {rule.category}" in text
