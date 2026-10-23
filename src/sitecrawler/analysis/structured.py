"""Structured data report: which types the crawl carries and everything wrong with them.

The per-page findings are the six ``schema.*`` rules; this module adds the
crawl-wide view (pages with items, syntaxes, type counts) and lists every
finding with its type and property path, which the issue messages only
summarise (ADR-0013). ``sitecrawler schema report`` prints it and ``audit``
prints its one-line summary.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from sitecrawler.audit.richresults import RICH_RESULTS
from sitecrawler.audit.structured import KINDS, Finding, FindingKind, rich_result_for
from sitecrawler.audit.view import CrawlView


@dataclass(slots=True, frozen=True)
class TypeCount:
    """How often one top-level type appears in the crawl."""

    type: str
    items: int
    pages: int
    rich_result: str
    """The rich-result type it is checked as, or empty when none applies."""


@dataclass(slots=True, frozen=True)
class StructuredReport:
    """What the structured data of one crawl looks like."""

    pages: int
    """Parsed HTML pages."""
    with_items: int
    """Of those, pages with at least one item."""
    formats: dict[str, int]
    """Pages per syntax (``json-ld``, ``microdata``, ``rdfa``)."""
    types: tuple[TypeCount, ...]
    """Top-level types, most items first."""
    findings: tuple[tuple[str, Finding], ...]
    """Every finding as ``(url, finding)``, by URL then :data:`KINDS` order."""

    def pages_with(self, kind: FindingKind) -> int:
        """Pages with at least one finding of ``kind``."""
        return len({url for url, f in self.findings if f.kind == kind})

    def summary(self) -> str:
        """One line for the audit output."""
        formats = ", ".join(f"{name} {count}" for name, count in self.formats.items())
        problems = ", ".join(
            f"{self.pages_with(kind)} {kind.replace('_', ' ')}"
            for kind in KINDS
            if self.pages_with(kind)
        )
        return (
            f"Structured data: {self.with_items} of {self.pages} pages carry items"
            f"{f' ({formats})' if formats else ''}; {len(self.types)} type(s); pages with "
            f"problems: {problems or 'none'}."
        )


def structured_report(crawl: CrawlView) -> StructuredReport:
    """Summarise the structured data index of ``crawl``."""
    index = crawl.structured
    items: Counter[str] = Counter()
    pages: Counter[str] = Counter()
    formats: Counter[str] = Counter()
    findings: list[tuple[str, Finding]] = []
    for page in sorted(index.pages, key=lambda p: p.url):
        data = page.structured
        assert data is not None  # index.pages are the parsed ones
        formats.update(data.formats)
        items.update(t for item in data.items for t in item.types)
        pages.update(data.types)
        findings += [(page.url, f) for f in index.findings_for(page.url)]
    types = tuple(
        TypeCount(name, count, pages[name], _rich(crawl, name))
        for name, count in sorted(items.items(), key=lambda kv: (-kv[1], kv[0]))
    )
    return StructuredReport(
        pages=len(index.pages),
        with_items=sum(1 for p in index.pages if p.structured and p.structured.items),
        formats={name: formats[name] for name in ("json-ld", "microdata", "rdfa") if formats[name]},
        types=types,
        findings=tuple(findings),
    )


def _rich(crawl: CrawlView, type_name: str) -> str:
    spec = rich_result_for(crawl.structured.vocabulary, type_name)
    return spec.type if spec is not None and spec.type in RICH_RESULTS else ""
