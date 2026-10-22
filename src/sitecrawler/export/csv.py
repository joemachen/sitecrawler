"""CSV export."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
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
    "render_changes",
)
"""Column order of the pages CSV. Changing this is a breaking change for users;
new columns go at the end. Custom extraction columns follow these, see :func:`write_csv`."""


def _row(record: PageRecord) -> dict[str, str | int | bool]:
    row: dict[str, str | int | bool] = {
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
        "render_changes": record.render.describe() if record.render else record.render_error,
    }
    for extraction in record.extractions:
        row[extraction.column] = (
            extraction.matched if extraction.kind == "search" else extraction.value
        )
    return row


def write_csv(
    records: Iterable[PageRecord], path: Path, *, extra_columns: Sequence[str] = ()
) -> int:
    """Write one row per record to ``path``. Returns the number of rows written.

    Args:
        records: The pages to write.
        path: The CSV file to create or overwrite.
        extra_columns: Custom extraction columns (``extract_<name>``,
            ``search_<name>``) appended after :data:`CSV_FIELDS`; a record's
            extractions that are not listed here are dropped.
    """
    count = 0
    fields = (*CSV_FIELDS, *(c for c in extra_columns if c not in CSV_FIELDS))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", restval="")
        writer.writeheader()
        for record in records:
            writer.writerow(_row(record))
            count += 1
    return count
