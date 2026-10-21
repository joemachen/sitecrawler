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
from sitecrawler.audit.view import Inlink
from sitecrawler.models import CrawlInfo, PageRecord, Severity
from sitecrawler.store import open_store
from sitecrawler.store.dump import Cell, TableDump, dump_tables

Row = dict[str, Cell]
"""One grid row: column name to cell value, as the JSON endpoints send it."""

_RANK = {s.value: s.rank for s in Severity}


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
class RuleRow:
    """One row of the Issues tab: a rule that fired and how many URLs it flagged."""

    rule: Rule
    count: int


@dataclass(slots=True, frozen=True)
class PageDetail:
    """Everything the crawl and audit know about one URL."""

    page: PageRecord
    indexable: bool | None
    """``None`` until an audit has run."""
    indexability_reason: str
    issues: list[Row]
    """``rule_id``, ``severity``, ``summary``, ``message`` per finding on this URL."""
    inlinks: list[Inlink]


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

    def rule_rows(self) -> list[RuleRow]:
        """Rules that fired, most severe first, then most URLs, then by id.

        Same order as the ``audit`` command's table. A stored rule id this
        version does not know is skipped.
        """
        rows = [
            RuleRow(self.rules[rule_id], count)
            for rule_id, count in self.issue_counts.items()
            if count and rule_id in self.rules
        ]
        return sorted(rows, key=lambda r: (r.rule.severity.rank, -r.count, r.rule.id))

    def issues_for(self, rule_id: str) -> list[Row]:
        """The stored issues of one rule, as rows, in URL order."""
        return to_rows(self._issues_where("rule_id", rule_id))

    def page_detail(self, url: str) -> PageDetail | None:
        """Everything about the page at ``url`` (any form), or ``None`` if it was not crawled."""
        page = self.view.page_for(url)
        if page is None:
            return None
        col = self.pages.columns.index
        indexable: bool | None = None
        reason = ""
        for row in self.pages.rows:
            if row[col("url")] == page.url:
                verdict = row[col("indexable")]
                indexable = verdict if isinstance(verdict, bool) else None
                reason = str(row[col("indexability_reason")] or "")
                break
        issues = [
            {
                "rule_id": row["rule_id"],
                "severity": row["severity"],
                "summary": self._summary(row["rule_id"]),
                "message": row["message"],
            }
            for row in to_rows(self._issues_where("url", page.url))
        ]
        issues.sort(key=lambda r: (_RANK.get(str(r["severity"]), len(_RANK)), str(r["rule_id"])))
        return PageDetail(
            page=page,
            indexable=indexable,
            indexability_reason=reason,
            issues=issues,
            inlinks=self.view.inlinks_to(page.url),
        )

    def _issues_where(self, column: str, value: Cell) -> TableDump:
        col = self.issues.columns.index(column)
        rows = [row for row in self.issues.rows if row[col] == value]
        return TableDump(self.issues.name, self.issues.columns, rows)

    def _summary(self, rule_id: Cell) -> str:
        rule = self.rules.get(str(rule_id))
        return rule.summary if rule else ""


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
