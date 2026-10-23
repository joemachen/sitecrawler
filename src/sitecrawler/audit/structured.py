"""Structured data index: what is wrong with each page's items (ADR-0013).

Built once per :class:`~sitecrawler.audit.view.CrawlView` and reached as
``crawl.structured``. Every parsed HTML page's items are checked against the
bundled schema.org vocabulary (types, and properties allowed on a type or its
ancestors) and against Google's rich-result requirements
(:data:`~sitecrawler.audit.richresults.RICH_RESULTS`). Names from other
vocabularies keep their IRI in the parsed item and are not checked. The
``schema.*`` rules and the structured data report read the same findings.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import TYPE_CHECKING, Literal
from urllib.parse import urljoin

from sitecrawler.audit.richresults import RICH_RESULTS, Need, RichResult
from sitecrawler.models import PageRecord, StructuredItem, StructuredNode, StructuredValue
from sitecrawler.parse.structured import is_bare

if TYPE_CHECKING:
    from sitecrawler.audit.view import CrawlView

FindingKind = Literal[
    "invalid_json",
    "missing_required",
    "unknown_type",
    "conflicting",
    "unknown_property",
    "missing_recommended",
]
"""What a finding is about; the rule id is ``schema.<kind>``."""

KINDS: tuple[FindingKind, ...] = (
    "invalid_json",
    "missing_required",
    "unknown_type",
    "conflicting",
    "unknown_property",
    "missing_recommended",
)


@dataclass(slots=True, frozen=True)
class Finding:
    """One problem with the structured data on one page."""

    kind: FindingKind
    message: str
    type: str = ""
    """The schema.org type the finding is about; empty for a JSON error."""
    path: str = ""
    """Property path within the item, e.g. ``offers.price``; empty for the item itself."""


class Vocabulary:
    """schema.org types with their parents and properties with the types they are defined on."""

    def __init__(
        self, types: Mapping[str, Sequence[str]], properties: Mapping[str, Sequence[str]]
    ) -> None:
        """Wrap the two maps; :meth:`bundled` reads the copy shipped with the package."""
        self.types = types
        self.properties = properties
        self._ancestors: dict[str, tuple[str, ...]] = {}

    @staticmethod
    @cache
    def bundled() -> Vocabulary:
        """The copy shipped in ``sitecrawler/data/`` (``scripts/update_schemaorg.py``)."""
        raw = json.loads(files("sitecrawler").joinpath("data/schemaorg.json").read_text("utf-8"))
        return Vocabulary(raw["types"], raw["properties"])

    def is_type(self, name: str) -> bool:
        """True for a schema.org type name."""
        return name in self.types

    def ancestors(self, name: str) -> tuple[str, ...]:
        """``name`` and every type it inherits from, nearest first."""
        if name not in self._ancestors:
            order: list[str] = []
            queue = [name]
            while queue:
                current = queue.pop(0)
                if current not in order:
                    order.append(current)
                    queue.extend(self.types.get(current, ()))
            self._ancestors[name] = tuple(order)
        return self._ancestors[name]

    def allows(self, type_name: str, prop: str) -> bool:
        """True when ``prop`` is defined on ``type_name`` or one of its ancestors."""
        domains = self.properties.get(prop)
        if domains is None:
            return False
        return any(d in domains for d in self.ancestors(type_name))


def _schema_names(names: Sequence[object]) -> list[str]:
    """The schema.org names in an ``@type`` list."""
    return [n for n in names if isinstance(n, str) and is_bare(n)]


def _present(node: StructuredNode, path: Sequence[str]) -> bool:
    """True when ``path`` has a non-empty value on every node the earlier segments reach."""
    values = [v for v in node.get(path[0], []) if isinstance(v, dict) or v.strip()]
    if len(path) == 1:
        return bool(values)
    nested = [v for v in values if isinstance(v, dict)]
    return bool(nested) and all(_present(n, path[1:]) for n in nested)


def _satisfied(node: StructuredNode, need: Need) -> bool:
    return any(_present(node, p.split(".")) for p in need.paths)


def rich_result_for(vocabulary: Vocabulary, type_name: str) -> RichResult | None:
    """The rich-result entry for ``type_name`` or its nearest listed ancestor."""
    for name in vocabulary.ancestors(type_name):
        if name in RICH_RESULTS:
            return RICH_RESULTS[name]
    return None


def _missing(node: StructuredNode, needs: Sequence[Need]) -> list[Need]:
    return [
        need
        for need in needs
        if (not need.when or _present(node, need.when.split("."))) and not _satisfied(node, need)
    ]


def _rich_findings(item: StructuredItem, vocabulary: Vocabulary) -> Iterator[Finding]:
    seen: set[str] = set()
    for type_name in _schema_names(item.types):
        spec = rich_result_for(vocabulary, type_name)
        if spec is None or spec.type in seen:
            continue
        seen.add(spec.type)
        for need in _missing(item.data, spec.required):
            yield Finding(
                "missing_required", f"{type_name} needs {need.label}", type_name, need.label
            )
        missing = _missing(item.data, spec.recommended)
        if missing:
            labels = ", ".join(n.label for n in missing)
            yield Finding("missing_recommended", f"{type_name} lacks {labels}", type_name, labels)


def _vocabulary_findings(
    node: StructuredNode, vocabulary: Vocabulary, path: str = ""
) -> Iterator[Finding]:
    """Unknown types and properties in ``node`` and the nodes nested in it."""
    where = f" (at {path})" if path else ""
    types = _schema_names(node.get("@type", []))
    unknown = [t for t in types if not vocabulary.is_type(t)]
    for type_name in unknown:
        yield Finding(
            "unknown_type", f"{type_name} is not a schema.org type{where}", type_name, path
        )
    for key, values in node.items():
        here = f"{path}.{key}" if path else key
        # An action may annotate any property as <name>-input or <name>-output
        # (schema.org Actions; the sitelinks search box's query-input).
        prop = re.sub(r"-(input|output)$", "", key)
        if types and not unknown and not key.startswith("@") and is_bare(key):
            if prop not in vocabulary.properties:
                yield Finding(
                    "unknown_property",
                    f"{key} is not a schema.org property (on {'/'.join(types)}){where}",
                    types[0],
                    here,
                )
            elif not any(vocabulary.allows(t, prop) for t in types):
                yield Finding(
                    "unknown_property",
                    f"{key} is not a property of {'/'.join(types)}{where}",
                    types[0],
                    here,
                )
        for value in values:
            if isinstance(value, dict):
                yield from _vocabulary_findings(value, vocabulary, here)


def _entity(item: StructuredItem, page_url: str) -> str:
    """What the item describes: its ``@id``, else its ``url``, resolved; empty when neither."""
    for key in ("@id", "url"):
        for value in item.data.get(key, []):
            if isinstance(value, str) and value.strip():
                return urljoin(page_url, value.strip())
    return ""


def _texts(values: Sequence[StructuredValue], key: str, page_url: str) -> tuple[str, ...]:
    """A property's text values as compared: whitespace squashed, a ``url`` resolved."""
    texts = (" ".join(v.split()) for v in values if isinstance(v, str))
    return tuple(sorted(urljoin(page_url, t) if key == "url" else t for t in texts))


def _conflicts(items: Sequence[StructuredItem], page_url: str) -> Iterator[Finding]:
    """Items of one type describing one entity that give a property different text values."""
    groups: dict[tuple[str, str], list[StructuredItem]] = defaultdict(list)
    for item in items:
        entity = _entity(item, page_url)
        for type_name in _schema_names(item.types) if entity else []:
            groups[type_name, entity].append(item)
    for (type_name, entity), group in groups.items():
        if len(group) < 2:
            continue
        for key in dict.fromkeys(k for item in group for k in item.data):
            if key.startswith("@"):
                continue
            texts = {_texts(item.data.get(key, []), key, page_url) for item in group} - {()}
            if len(texts) > 1:
                shown = " vs ".join(repr(" | ".join(t)) for t in sorted(texts))
                yield Finding(
                    "conflicting",
                    f"{len(group)} {type_name} items for {entity} disagree on {key}: {shown}",
                    type_name,
                    key,
                )


def check_page(page: PageRecord, vocabulary: Vocabulary) -> list[Finding]:
    """Every finding for ``page``, in :data:`KINDS` order."""
    data = page.structured
    if data is None:
        return []
    found = [Finding("invalid_json", e.message) for e in data.errors]
    for item in data.items:
        found += _vocabulary_findings(item.data, vocabulary)
        found += _rich_findings(item, vocabulary)
    found += _conflicts(data.items, page.url)
    return sorted(found, key=lambda f: KINDS.index(f.kind))


class StructuredIndex:
    """Findings per page over every parsed HTML page of a crawl."""

    def __init__(self, crawl: CrawlView, vocabulary: Vocabulary | None = None) -> None:
        """Check every parsed HTML page; ``vocabulary`` defaults to the bundled one."""
        self.vocabulary = vocabulary or Vocabulary.bundled()
        self.pages = [p for p in crawl.html_pages if p.structured is not None]
        """Parsed HTML pages, with or without items."""
        self._findings = {p.url: check_page(p, self.vocabulary) for p in self.pages}

    def findings_for(self, url: str, kind: FindingKind | None = None) -> list[Finding]:
        """The findings for the page at ``url``, all of them or one kind."""
        found = self._findings.get(url, [])
        return [f for f in found if kind is None or f.kind == kind]
