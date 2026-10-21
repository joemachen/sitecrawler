"""Read side of the web UI: one in-memory snapshot of a stored crawl.

The UI serves a finished crawl, so everything is read once from the SQLite
file, which is then closed (Windows keeps it locked while open). The
snapshot is plain data; nothing here imports FastAPI, so the CLI could show
the same numbers.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sitecrawler.audit import CrawlView, Rule, load_rules
from sitecrawler.models import CrawlInfo, Severity
from sitecrawler.store import open_store
from sitecrawler.store.dump import Cell, TableDump, dump_tables

Row = dict[str, Cell]
"""One grid row: column name to cell value, as the JSON endpoints send it."""


@dataclass(slots=True, frozen=True)
class Overview:
    """The numbers on the Overview tab."""

    pages: int
    status_buckets: dict[str, int]
    """``2xx`` .. ``5xx`` for responses, else the outcome (``blocked``, ``error``, ...)."""
    depth_histogram: dict[int, int]
    issues_by_severity: dict[str, int]
    """Every severity, most severe first, zero when none."""
    indexable: int
    non_indexable: int

    @property
    def issues(self) -> int:
        """Total stored issues."""
        return sum(self.issues_by_severity.values())


@dataclass(slots=True, frozen=True)
class CrawlSnapshot:
    """Everything the UI shows, loaded once by :func:`load_snapshot`."""

    path: Path
    info: CrawlInfo
    view: CrawlView
    """Index over the page records: lookups by URL, inlinks, sitemap membership."""
    pages: TableDump
    issues: TableDump
    redirects: TableDump
    rules: dict[str, Rule]
    issue_counts: dict[str, int]

    @property
    def audited(self) -> bool:
        """True once ``sitecrawler audit`` has stored a verdict on any page."""
        col = self.pages.columns.index("indexable")
        return any(row[col] is not None for row in self.pages.rows)

    def overview(self) -> Overview:
        """Compute the Overview tab's numbers from the pages and issues tables."""
        col = self.pages.columns.index
        status_code, outcome, depth, indexable = (
            col("status_code"),
            col("outcome"),
            col("depth"),
            col("indexable"),
        )
        buckets: Counter[str] = Counter()
        depths: Counter[int] = Counter()
        yes = no = 0
        for row in self.pages.rows:
            code = row[status_code]
            buckets[
                f"{code // 100}xx" if isinstance(code, int) else str(row[outcome] or "error")
            ] += 1
            d = row[depth]
            depths[d if isinstance(d, int) else 0] += 1
            if row[indexable] is True:
                yes += 1
            elif row[indexable] is False:
                no += 1
        severity = self.issues.columns.index("severity")
        by_severity = {s.value: 0 for s in Severity}
        for row in self.issues.rows:
            level = str(row[severity])  # a db from a newer sitecrawler may know more levels
            by_severity[level] = by_severity.get(level, 0) + 1
        return Overview(
            pages=len(self.pages.rows),
            status_buckets=dict(sorted(buckets.items())),
            depth_histogram=dict(sorted(depths.items())),
            issues_by_severity=by_severity,
            indexable=yes,
            non_indexable=no,
        )


def to_rows(table: TableDump) -> list[Row]:
    """A dump as a list of dicts, which is what Tabulator consumes."""
    return [dict(zip(table.columns, row, strict=True)) for row in table.rows]


def load_snapshot(path: Path) -> CrawlSnapshot:
    """Read ``path`` into a :class:`CrawlSnapshot` and close the file.

    Raises:
        ValueError: when the file holds no crawl.
    """
    path = Path(path)
    with open_store(path) as store:
        info = store.crawl()
        view = CrawlView.from_store(store)
        tables = {t.name: t for t in dump_tables(store, ("pages", "issues", "redirects"))}
        counts = store.issue_counts()
    return CrawlSnapshot(
        path=path,
        info=info,
        view=view,
        pages=tables["pages"],
        issues=tables["issues"],
        redirects=tables["redirects"],
        rules={r.id: r for r in load_rules()},
        issue_counts=counts,
    )
