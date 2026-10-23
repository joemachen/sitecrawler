"""Refresh the bundled schema.org vocabulary (ADR-0013).

Run with ``uv run python scripts/update_schemaorg.py``. It downloads the
current schema.org release as JSON-LD and keeps only what the structured data
audit reads: every type with its direct parents, and every property with the
types it is defined on. The result is ``src/sitecrawler/data/schemaorg.json``,
committed so that crawls and tests never touch the network.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

SOURCE = "https://schema.org/version/latest/schemaorg-current-https.jsonld"
TARGET = Path(__file__).resolve().parent.parent / "src" / "sitecrawler" / "data" / "schemaorg.json"
PREFIX = "schema:"


def _ids(value: Any) -> list[str]:  # Any: raw JSON-LD node
    """The schema.org names referenced by an ``{"@id": ...}`` node or a list of them."""
    nodes = value if isinstance(value, list) else [value]
    names = []
    for node in nodes:
        ref = node.get("@id", "") if isinstance(node, dict) else ""
        if ref.startswith(PREFIX):
            names.append(ref.removeprefix(PREFIX))
    return names


def _kinds(node: dict[str, Any]) -> set[str]:
    kind = node.get("@type", [])
    return set(kind if isinstance(kind, list) else [kind])


def reduce(graph: Iterable[dict[str, Any]]) -> dict[str, dict[str, list[str]]]:
    """Types to their parents and properties to their domains, both sorted."""
    types: dict[str, list[str]] = {}
    properties: dict[str, list[str]] = {}
    for node in graph:
        ref = node.get("@id", "")
        if not ref.startswith(PREFIX):
            continue
        name = ref.removeprefix(PREFIX)
        kinds = _kinds(node)
        if "rdfs:Class" in kinds:
            types[name] = sorted(_ids(node.get("rdfs:subClassOf", [])))
        elif "rdf:Property" in kinds:
            properties[name] = sorted(_ids(node.get("schema:domainIncludes", [])))
    return {"types": dict(sorted(types.items())), "properties": dict(sorted(properties.items()))}


def main() -> None:
    """Download, reduce and write the vocabulary."""
    response = httpx.get(SOURCE, follow_redirects=True, timeout=60)
    response.raise_for_status()
    graph = response.json()["@graph"]
    vocabulary = {"source": SOURCE, **reduce(graph)}
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(vocabulary, indent=0, sort_keys=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(  # noqa: T201
        f"wrote {TARGET} ({len(vocabulary['types'])} types, "
        f"{len(vocabulary['properties'])} properties)"
    )


if __name__ == "__main__":
    main()
