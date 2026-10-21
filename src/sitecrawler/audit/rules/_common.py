"""Helpers shared by rule modules."""

from __future__ import annotations

from collections.abc import Sequence

from sitecrawler.models import PageRecord


def describe_group(page: PageRecord, group: Sequence[PageRecord]) -> str:
    """``same as <first other page> and N more`` for a duplicate group."""
    others = [p.url for p in group if p.url != page.url]
    more = f" and {len(others) - 1} more" if len(others) > 1 else ""
    return f"same as {others[0]}{more}"


def describe_sources(sources: Sequence[str]) -> str:
    """``linked from <first> and N more`` for a list of source URLs."""
    more = f" and {len(sources) - 1} more" if len(sources) > 1 else ""
    return f"linked from {sources[0]}{more}"
