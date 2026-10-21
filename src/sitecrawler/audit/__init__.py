"""Audit rules that turn stored page records into issues. Never fetches anything."""

from sitecrawler.audit.engine import AuditResult, indexability, run_audit
from sitecrawler.audit.registry import load_rules, rule_by_id
from sitecrawler.audit.rule import HtmlPageRule, PageRule, Rule
from sitecrawler.audit.view import CrawlView

__all__ = [
    "AuditResult",
    "CrawlView",
    "HtmlPageRule",
    "PageRule",
    "Rule",
    "indexability",
    "load_rules",
    "rule_by_id",
    "run_audit",
]
