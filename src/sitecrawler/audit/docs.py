"""Render the rules reference page from the rules themselves, so docs cannot drift."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sitecrawler.audit.rule import Rule

HEADER = """# Audit rules

Every check `sitecrawler audit` runs, generated from the rule classes in
`src/sitecrawler/audit/rules/` by `uv run python scripts/gen_rule_docs.py`.
Do not edit by hand.

Severity: **critical** blocks indexing or breaks pages site-wide, **high** costs
rankings on affected pages, **medium** is worth fixing in the next sprint,
**low** is hygiene, **info** is a fact to know rather than a problem.

One tag can appear under several rules when they ask for different actions:
an off-site canonical is listed by `canonical.off_site` (fix the tag),
`canonical.canonicalised_but_linked` (fix the links) and
`canonical.not_self_referencing` (the informational roll-up). Count problems
by the highest-severity rule, not by the number of rows.
"""


def _text(value: str) -> str:
    """Rule prose for Markdown: tag-like text such as ``<title>`` must not render as HTML."""
    return value.strip().replace("<", "&lt;").replace(">", "&gt;")


def render_rules_page(rules: Iterable[Rule]) -> str:
    """Markdown for the rules reference, grouped by category then rule id."""
    by_category: dict[str, list[Rule]] = defaultdict(list)
    for rule in rules:
        by_category[rule.category].append(rule)

    parts = [HEADER]
    for category in sorted(by_category):
        parts.append(f"\n## {category}\n")
        for rule in sorted(by_category[category], key=lambda r: r.id):
            parts.append(
                f"\n### `{rule.id}`\n\n"
                f"**{_text(rule.summary)}** (severity: {rule.severity.value})\n\n"
                f"{_text(rule.why)}\n\n"
                f"**Fix:** {_text(rule.fix)}\n"
            )
    return "".join(parts)
