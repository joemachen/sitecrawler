"""CSV export."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from sitecrawler.models import PageRecord

CSV_FIELDS: tuple[str, ...] = (
    "url",
    "status",
    "title",
    "meta_description",
    "h1",
    "canonical",
    "content_type",
    "depth",
    "found_on",
    "internal_links",
    "word_count",
    "fetch_ms",
    "error",
)
"""Column order of the pages CSV. Changing this is a breaking change for users."""


def _row(record: PageRecord) -> dict[str, str | int]:
    return {
        "url": record.url,
        "status": record.status,
        "title": record.title,
        "meta_description": record.meta_description,
        "h1": record.h1,
        "canonical": record.canonical,
        "content_type": record.content_type,
        "depth": record.depth,
        "found_on": record.found_on,
        "internal_links": record.internal_links,
        "word_count": record.word_count,
        "fetch_ms": record.fetch_ms,
        "error": record.error,
    }


def write_csv(records: Iterable[PageRecord], path: Path) -> int:
    """Write one row per record to ``path``. Returns the number of rows written."""
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(_row(record))
            count += 1
    return count
