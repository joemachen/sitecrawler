"""XLSX export: one sheet per table."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from openpyxl import Workbook

from sitecrawler.store.dump import TableDump


def write_xlsx(tables: Iterable[TableDump], path: Path) -> int:
    """Write each table to its own sheet (named after the table) with a header row.

    Returns:
        Total number of data rows written across all sheets.
    """
    workbook = Workbook(write_only=True)
    count = 0
    for table in tables:
        sheet = workbook.create_sheet(title=table.name)
        sheet.append(list(table.columns))
        for row in table.rows:
            sheet.append(list(row))
            count += 1
    workbook.save(path)
    return count
