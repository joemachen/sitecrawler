"""Structured data: JSON-LD, microdata and RDFa Lite read into one shape (ADR-0013).

The HTML bodies are not stored, so the items are read in the crawl pass from
the tree the page was parsed from (the rendered DOM under ``--render``). All
three syntaxes become :data:`~sitecrawler.models.StructuredNode` dicts in
which every key maps to a list of values, so the audit validates them without
caring how they were written. This is not a full JSON-LD processor: contexts
are only read for their vocabulary, and anything that is not schema.org keeps
its full IRI so the audit can tell it apart.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

from lxml import etree

from sitecrawler.models import (
    StructuredData,
    StructuredError,
    StructuredItem,
    StructuredNode,
    StructuredValue,
)

_SCHEMA = re.compile(r"(?:schema:|https?://(?:www\.)?schema\.org/)([A-Za-z0-9_]*)/?")
_SCHEMA_CONTEXTS = frozenset(
    f"{scheme}://{host}schema.org" for scheme in ("http", "https") for host in ("", "www.")
)
_JSONLD = "application/ld+json"
_URL_ATTRS = {
    "a": "href",
    "area": "href",
    "link": "href",
    "audio": "src",
    "embed": "src",
    "iframe": "src",
    "img": "src",
    "source": "src",
    "track": "src",
    "video": "src",
    "object": "data",
}
"""Elements whose microdata or RDFa value is a URL attribute, resolved against the page."""


def _is_bare(name: str) -> bool:
    return not any(c in name for c in ":/#")


def schema_name(raw: str) -> str | None:
    """The bare schema.org name for ``raw``, or None when it names another vocabulary.

    ``Product``, ``schema:Product`` and ``https://schema.org/Product`` (http or
    https, with or without ``www.`` or a trailing slash) all give ``Product``.
    """
    raw = raw.strip()
    if _is_bare(raw):
        return raw or None
    match = _SCHEMA.fullmatch(raw)
    return (match.group(1) or None) if match else None


def _term(raw: str, vocab: str) -> str:
    """``raw`` as a bare schema.org name, or prefixed with ``vocab`` / kept as written."""
    raw = raw.strip()
    if _is_bare(raw):
        return vocab + raw
    name = schema_name(raw)
    return name if name is not None else raw


def _add(node: StructuredNode, key: str, value: StructuredValue) -> None:
    node.setdefault(key, []).append(value)


def _text(element: etree._Element) -> str:
    return " ".join(
        " ".join(t if isinstance(t, str) else t.decode() for t in element.itertext()).split()
    )


def _line(element: etree._Element) -> int:
    line: object = element.sourceline  # lxml-stubs types it as Ellipsis
    return line if isinstance(line, int) else 0


def _tag(element: etree._Element) -> str:
    return element.tag.lower() if isinstance(element.tag, str) else ""


# ------------------------------------------------------------------ JSON-LD


def _vocab(context: Any, inherited: str) -> str:  # Any: raw JSON
    """The vocabulary ``context`` puts bare names in: ``""`` for schema.org, else an IRI."""
    if isinstance(context, str):
        if context.strip().rstrip("/") in _SCHEMA_CONTEXTS:
            return ""
        return context if context.endswith(("/", "#")) else f"{context}/"
    if isinstance(context, dict):
        return _vocab(context["@vocab"], inherited) if "@vocab" in context else inherited
    if isinstance(context, list):
        for entry in context:
            inherited = _vocab(entry, inherited)
    return inherited


def _scalar(value: Any) -> str | None:  # Any: raw JSON
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value)


def _values(value: Any, vocab: str) -> list[StructuredValue]:  # Any: raw JSON
    """One JSON-LD property value as a flat list of text and nodes."""
    if isinstance(value, list):
        return [v for entry in value for v in _values(entry, vocab)]
    if isinstance(value, dict):
        if "@value" in value:
            text = _scalar(value["@value"])
            return [text] if text is not None else []
        for key in ("@list", "@set"):
            if key in value:
                return _values(value[key], vocab)
        return [_node(value, vocab)]
    text = _scalar(value)
    return [text] if text is not None else []


def _node(raw: dict[str, Any], vocab: str) -> StructuredNode:  # Any: raw JSON
    vocab = _vocab(raw.get("@context"), vocab)
    node: StructuredNode = {}
    types = raw.get("@type", [])
    for name in types if isinstance(types, list) else [types]:
        if isinstance(name, str) and name.strip():
            _add(node, "@type", _term(name, vocab))
    if isinstance(raw.get("@id"), str):
        _add(node, "@id", raw["@id"])
    for key, value in raw.items():
        if key.startswith("@"):
            continue
        for entry in _values(value, vocab):
            _add(node, _term(key, vocab), entry)
    return node


def _jsonld_items(raw: Any, line: int) -> list[StructuredItem]:  # Any: raw JSON
    if isinstance(raw, list):
        return [item for entry in raw for item in _jsonld_items(entry, line)]
    if not isinstance(raw, dict):
        return []
    if "@graph" in raw:
        vocab = _vocab(raw.get("@context"), "")
        graph = raw["@graph"]
        return [
            StructuredItem("json-ld", _node(entry, vocab), line)
            for entry in (graph if isinstance(graph, list) else [graph])
            if isinstance(entry, dict)
        ]
    return [StructuredItem("json-ld", _node(raw, ""), line)]


def _jsonld(
    doc: etree._Element, items: list[StructuredItem], errors: list[StructuredError]
) -> None:
    for script in doc.iter("script"):
        if (script.get("type") or "").strip().lower() != _JSONLD:
            continue
        text = script.text or ""
        if not text.strip():
            continue
        start = _line(script)
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as error:
            line = start + error.lineno - 1 if start else error.lineno
            message = f"{error.msg} (line {line}, column {error.colno})"
            errors.append(StructuredError(message, line))
            continue
        items.extend(_jsonld_items(raw, start))


# ------------------------------------------------------------------ microdata and RDFa


def _element_value(element: etree._Element, base_url: str, content: str | None) -> str:
    """The value an element gives its property: ``content``, a URL, a machine value, or text."""
    if content is not None:
        return content.strip()
    tag = _tag(element)
    attr = _URL_ATTRS.get(tag)
    if attr is not None and element.get(attr) is not None:
        return urljoin(base_url, (element.get(attr) or "").strip())
    if tag in ("data", "meter") and element.get("value") is not None:
        return (element.get("value") or "").strip()
    if tag == "time" and element.get("datetime") is not None:
        return (element.get("datetime") or "").strip()
    return _text(element)


def _microdata_item(element: etree._Element, base_url: str) -> StructuredNode:
    node: StructuredNode = {}
    for name in (element.get("itemtype") or "").split():
        _add(node, "@type", _term(name, ""))
    if element.get("itemid"):
        _add(node, "@id", (element.get("itemid") or "").strip())
    for child in element:
        _microdata_props(child, node, base_url)
    return node


def _microdata_props(element: etree._Element, node: StructuredNode, base_url: str) -> None:
    if not _tag(element):
        return
    scoped = element.get("itemscope") is not None
    names = (element.get("itemprop") or "").split()
    if names:
        value: StructuredValue = (
            _microdata_item(element, base_url)
            if scoped
            else _element_value(
                element, base_url, element.get("content") if _tag(element) == "meta" else None
            )
        )
        for name in names:
            _add(node, _term(name, ""), value)
    if scoped:  # its descendants belong to it, whether it is a value or an item of its own
        return
    for child in element:
        _microdata_props(child, node, base_url)


def _microdata(doc: etree._Element, base_url: str, items: list[StructuredItem]) -> None:
    for element in doc.iter():
        if (
            _tag(element)
            and element.get("itemscope") is not None
            and element.get("itemprop") is None
        ):
            items.append(
                StructuredItem("microdata", _microdata_item(element, base_url), _line(element))
            )


def _rdfa(
    element: etree._Element,
    base_url: str,
    vocab: str,
    current: StructuredNode | None,
    items: list[StructuredItem],
) -> None:
    """Walk ``element`` for RDFa Lite: ``vocab``, ``typeof``, ``property``, ``resource``."""
    if not _tag(element):
        return
    if element.get("vocab") is not None:
        vocab = _vocab(element.get("vocab"), vocab)
    names = (element.get("property") or "").split()
    typeof = element.get("typeof")
    if typeof is not None:
        node: StructuredNode = {}
        for name in typeof.split():
            _add(node, "@type", _term(name, vocab))
        if element.get("resource"):
            _add(node, "@id", (element.get("resource") or "").strip())
        if names and current is not None:
            for name in names:
                _add(current, _term(name, vocab), node)
        else:
            items.append(StructuredItem("rdfa", node, _line(element)))
        current = node
    elif names and current is not None:
        value = _element_value(element, base_url, element.get("content"))
        for name in names:
            _add(current, _term(name, vocab), value)
    for child in element:
        _rdfa(child, base_url, vocab, current, items)


# ------------------------------------------------------------------ entry point


def extract_structured(doc: etree._Element, base_url: str) -> StructuredData:
    """Every JSON-LD, microdata and RDFa Lite item on the page, in that order.

    Args:
        doc: The parsed page, before scripts are stripped.
        base_url: URL the page was served from; URL values resolve against it.
    """
    items: list[StructuredItem] = []
    errors: list[StructuredError] = []
    _jsonld(doc, items, errors)
    _microdata(doc, base_url, items)
    _rdfa(doc, base_url, "", None, items)
    return StructuredData(tuple(items), tuple(errors))
