"""Regenerate docs/user-guide/rules.md from the rule classes.

Run with ``uv run python scripts/gen_rule_docs.py``. A test fails when the
committed page is stale, so run this after adding or editing a rule.
"""

from __future__ import annotations

from pathlib import Path

from sitecrawler.audit import load_rules
from sitecrawler.audit.docs import render_rules_page

TARGET = Path(__file__).resolve().parent.parent / "docs" / "user-guide" / "rules.md"


def main() -> None:
    """Write the page and report how many rules it covers."""
    rules = load_rules()
    TARGET.write_text(render_rules_page(rules), encoding="utf-8", newline="\n")
    print(f"wrote {TARGET} ({len(rules)} rules)")  # noqa: T201


if __name__ == "__main__":
    main()
