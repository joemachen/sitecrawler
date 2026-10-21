"""JSON export: the crawl summary plus every table as a list of objects."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from sitecrawler.models import CrawlInfo
from sitecrawler.store.dump import TableDump


def _plain(value: object) -> object:
    return value.isoformat(timespec="seconds") if isinstance(value, datetime) else value


def write_json(crawl: CrawlInfo, tables: Iterable[TableDump], path: Path) -> int:
    """Write ``{"crawl": {...}, "<table>": [{column: value, ...}, ...], ...}``.

    Returns:
        Total number of rows written across all tables.
    """
    document: dict[str, object] = {
        "crawl": {key: _plain(value) for key, value in asdict(crawl).items()}
    }
    count = 0
    for table in tables:
        rows = [dict(zip(table.columns, row, strict=True)) for row in table.rows]
        document[table.name] = rows
        count += len(rows)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return count
