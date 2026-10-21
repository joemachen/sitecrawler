from pathlib import Path

from sitecrawler.audit import load_rules
from sitecrawler.audit.docs import render_rules_page

RULES_MD = Path(__file__).resolve().parents[3] / "docs" / "user-guide" / "rules.md"


def test_committed_rules_page_is_current() -> None:
    """Fails when a rule changed but `scripts/gen_rule_docs.py` was not re-run."""
    assert RULES_MD.read_text(encoding="utf-8") == render_rules_page(load_rules())
