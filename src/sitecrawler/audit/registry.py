"""Finds every rule shipped under ``sitecrawler.audit.rules``."""

from __future__ import annotations

import importlib
import inspect
import pkgutil

from sitecrawler.audit import rules as rules_package
from sitecrawler.audit.rule import Rule


def load_rules() -> list[Rule]:
    """Import every module in ``audit/rules/`` and instantiate each concrete rule.

    Rules come back sorted by id. Two rules sharing an id is a programming
    error and raises ``ValueError``.
    """
    found: dict[str, Rule] = {}
    for module_info in pkgutil.iter_modules(rules_package.__path__):
        module = importlib.import_module(f"{rules_package.__name__}.{module_info.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not issubclass(cls, Rule) or inspect.isabstract(cls):
                continue
            if cls.__module__ != module.__name__:
                continue  # imported base class, not a rule defined here
            rule = cls()
            if rule.id in found:
                msg = f"duplicate rule id {rule.id!r} in {module.__name__}"
                raise ValueError(msg)
            found[rule.id] = rule
    return [found[rule_id] for rule_id in sorted(found)]


def rule_by_id(rule_id: str) -> Rule | None:
    """The rule with ``rule_id``, or ``None``."""
    return next((r for r in load_rules() if r.id == rule_id), None)
