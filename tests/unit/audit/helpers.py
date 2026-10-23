"""Builders for audit unit tests: records and views without a crawl."""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit import CrawlView, Rule
from sitecrawler.models import Issue, LinkRef, Outcome, PageRecord

SITE = "https://site.test"


def page(path: str, status: int | None = 200, **fields: object) -> PageRecord:
    """A fetched HTML page at ``path`` with sensible defaults, overridable per field."""
    defaults: dict[str, object] = {
        "outcome": Outcome.FETCHED,
        "depth": 0,
        "found_on": "start",
        "status_code": status,
        "content_type": "text/html",
        "final_url": f"{SITE}{path}",
        "title": f"Title of {path}",
        "meta_description": f"Description of {path} that is long enough to pass the checks.",
        "h1": f"Heading {path}",
        "h1s": (f"Heading {path}",),
        "h2s": ("Sub",),
        "title_count": 1,
        "meta_description_count": 1,
        "canonical": f"{SITE}{path}",
        "word_count": 100,
    }
    defaults.update(fields)
    return PageRecord(url=f"{SITE}{path}", **defaults)  # type: ignore[arg-type]


def blocked(path: str) -> PageRecord:
    """A robots-blocked page."""
    return PageRecord(
        url=f"{SITE}{path}",
        outcome=Outcome.BLOCKED,
        depth=1,
        found_on=f"{SITE}/",
        error="disallowed by robots.txt",
    )


def links(*paths: str, rel: str = "") -> tuple[LinkRef, ...]:
    """Anchors to ``paths`` on the site."""
    return tuple(LinkRef(f"{SITE}{p}", text=p, rel=rel) for p in paths)


def long_text(count: int, prefix: str = "word") -> str:
    """``count`` distinct numbered words, for pages over the low-content floor."""
    return " ".join(f"{prefix}{i}" for i in range(count))


def view(pages: Iterable[PageRecord], **kwargs: object) -> CrawlView:
    """A view over ``pages``."""
    return CrawlView.from_records(pages, **kwargs)  # type: ignore[arg-type]


def flagged(rule: Rule, pages: Iterable[PageRecord], **kwargs: object) -> dict[str, Issue]:
    """Run ``rule`` and return its issues keyed by URL path."""
    found = list(rule.check(view(pages, **kwargs)))
    assert all(i.rule_id == rule.id and i.severity is rule.severity for i in found)
    return {i.url.removeprefix(SITE): i for i in found}
