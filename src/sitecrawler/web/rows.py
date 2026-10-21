"""Grid rows, summaries and page detail over a :class:`CrawlSession`.

A row has two halves. The *base* cells come straight from the page record
and never change once the page is fetched. The *audit* cells (rules that
flagged it, verdict, inlinks) are rebuilt every time the audit runs, and
each row remembers the revision that last changed them, so a client that
already holds revision ``r`` only needs the rows whose cells moved since.
Nothing here imports FastAPI.
"""

from __future__ import annotations

import threading
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

from sitecrawler.audit import AuditResult, CrawlView, Rule
from sitecrawler.audit.engine import RuleCount, robots_directives
from sitecrawler.audit.view import Inlink
from sitecrawler.crawl.urls import normalize, same_site
from sitecrawler.models import Issue, Outcome, PageRecord, Severity
from sitecrawler.session import CrawlSession, SessionState
from sitecrawler.web.tabs import TABS, Row, matches

URL_LONG = 115
"""URLs longer than this get the ``long`` flag on the URL tab."""

_RANK = {s.value: s.rank for s in Severity}

NO_AUDIT: Row = {
    "rules": [],
    "issues_n": 0,
    "indexable": None,
    "indexability_reason": "",
    "inlinks": 0,
    "non_indexable_in_sitemap": False,
}
"""Audit cells of a page the audit has not seen yet."""


# ----------------------------------------------------------------- base cells
def _first_status(record: PageRecord) -> int | None:
    return record.redirect_hops[0].status_code if record.redirect_hops else record.status_code


def _status_class(record: PageRecord) -> str:
    if record.outcome is Outcome.BLOCKED:
        return "blocked"
    if record.outcome is Outcome.ERROR:
        return "no_response"
    code = _first_status(record)
    return f"{code // 100}xx" if code is not None else "no_response"


def _url_flags(url: str) -> str:
    parts = urlparse(url)
    flags = []
    if any(ord(c) > 127 for c in url):
        flags.append("non_ascii")
    if any(c.isupper() for c in parts.path):
        flags.append("uppercase")
    if "_" in parts.path:
        flags.append("underscores")
    if parts.query:
        flags.append("parameters")
    if len(url) > URL_LONG:
        flags.append("long")
    return " ".join(flags)


def _canonical_kind(record: PageRecord, *, keep_query: bool) -> str:
    """``self``, ``other`` or ``missing`` for a parsed HTML page; empty otherwise."""
    if not _is_html(record):
        return ""
    canonical = record.canonical_header or record.canonical
    if not canonical:
        return "missing"
    same = normalize(canonical, keep_query=keep_query) == normalize(
        record.url, keep_query=keep_query
    )
    return "self" if same else "other"


def _is_html(record: PageRecord) -> bool:
    return (
        record.outcome is Outcome.FETCHED
        and "html" in record.content_type
        and record.status_code is not None
        and record.status_code < 400
    )


def base_row(
    record: PageRecord, *, sitemap: frozenset[str] = frozenset(), keep_query: bool = False
) -> Row:
    """The cells of ``record`` that never change: response, HTML fields, computed lengths.

    Args:
        record: The fetched page.
        sitemap: Normalised URLs listed in any sitemap.
        keep_query: The crawl's query-string setting, for URL comparisons.
    """
    page_host = urlparse(record.url).netloc
    internal = [link for link in record.links if same_site(urlparse(link.href).netloc, page_host)]
    directives = " ".join(sorted(robots_directives(record)))
    kind = _canonical_kind(record, keep_query=keep_query)
    return {
        "url": record.url,
        "status": record.status,
        "status_code": record.status_code,
        "first_status": _first_status(record),
        "status_class": _status_class(record),
        "outcome": record.outcome.value,
        "final_url": record.final_url,
        "redirect_hops": len(record.redirect_hops),
        "content_type": record.content_type,
        "content_class": ""
        if record.outcome is not Outcome.FETCHED
        else ("html" if "html" in record.content_type else "other"),
        "size_bytes": record.size_bytes,
        "depth": record.depth,
        "found_on": record.found_on,
        "title": record.title,
        "title_length": len(record.title),
        "title_count": record.title_count,
        "meta_description": record.meta_description,
        "meta_length": len(record.meta_description),
        "meta_description_count": record.meta_description_count,
        "h1": record.h1,
        "h1_length": len(record.h1),
        "h1_count": len(record.h1s),
        "h2": record.h2s[0] if record.h2s else "",
        "h2_count": len(record.h2s),
        "canonical": record.canonical,
        "canonical_header": record.canonical_header,
        "canonical_kind": kind,
        "has_canonical": kind in ("self", "other"),
        "og_url": record.og_url,
        "meta_robots": record.meta_robots,
        "x_robots_tag": record.headers.get("x-robots-tag", ""),
        "directives": directives,
        "lang": record.lang,
        "word_count": record.word_count,
        "outlinks": len(record.links),
        "outlinks_internal": len(internal),
        "outlinks_external": len(record.links) - len(internal),
        "nofollow_outlinks": sum(1 for link in record.links if link.nofollow),
        "internal_links": record.internal_links,
        "hreflang_count": len(record.hreflang),
        "hreflang_langs": ", ".join(ref.lang for ref in record.hreflang),
        "rel_prev": record.rel_prev,
        "rel_next": record.rel_next,
        "paginated": bool(record.rel_prev or record.rel_next),
        "url_length": len(record.url),
        "url_flags": _url_flags(record.url),
        "in_sitemap": normalize(record.url, keep_query=keep_query) in sitemap,
        "fetch_ms": record.fetch_ms,
        "error": record.error,
    }


def external_rows(records: Iterable[PageRecord]) -> list[Row]:
    """One row per external link target: how many pages link to it, and how."""
    inlinks: Counter[str] = Counter()
    nofollow: Counter[str] = Counter()
    first_found: dict[str, str] = {}
    for record in records:
        page_host = urlparse(record.url).netloc
        for link in record.links:
            if not link.href.startswith(("http://", "https://")):
                continue
            if same_site(urlparse(link.href).netloc, page_host):
                continue
            inlinks[link.href] += 1
            if link.nofollow:
                nofollow[link.href] += 1
            first_found.setdefault(link.href, record.url)
    return [
        {
            "url": url,
            "inlinks": count,
            "nofollow_inlinks": nofollow[url],
            "nofollow_only": nofollow[url] == count,
            "first_found_on": first_found[url],
        }
        for url, count in sorted(inlinks.items())
    ]


# ---------------------------------------------------------------- audit cells
class AuditIndex:
    """One audit revision, indexed by URL."""

    def __init__(self, rev: int, result: AuditResult, view: CrawlView) -> None:
        """Index ``result`` for per-URL lookups."""
        self.rev = rev
        self.result = result
        self.view = view
        by_url: defaultdict[str, list[Issue]] = defaultdict(list)
        for issue in result.issues:
            by_url[issue.url].append(issue)
        self._issues = dict(by_url)
        self._in_sitemap = view.in_sitemap

    def issues_for_url(self, url: str) -> list[Issue]:
        """This revision's findings on ``url``, most severe first."""
        return sorted(self._issues.get(url, []), key=lambda i: (i.severity.rank, i.rule_id))

    def cells(self, url: str) -> Row:
        """The audit half of the row for ``url``."""
        issues = self.issues_for_url(url)
        verdict = self.result.verdicts.get(url)
        indexable = verdict.indexable if verdict else None
        key = self.view.normalize(url)
        return {
            "rules": [i.rule_id for i in issues],
            "issues_n": len(issues),
            "indexable": indexable,
            "indexability_reason": verdict.reason if verdict else "",
            "inlinks": len(self.view.inlinks_to(url)),
            "non_indexable_in_sitemap": indexable is False and key in self._in_sitemap,
        }


# ------------------------------------------------------------------ results
@dataclass(slots=True, frozen=True)
class RowsPage:
    """What ``/api/rows`` returns: new rows, and the audit cells that moved."""

    seq: int
    audit_rev: int
    rows: list[Row]
    patches: list[Row] = field(default_factory=list)
    """``url`` plus the audit cells, for rows the client already has."""
    full: bool = False
    """True when ``rows`` is the whole table and ``patches`` is empty."""

    def to_json(self) -> dict[str, object]:
        """A JSON-ready dict."""
        return asdict(self)


@dataclass(slots=True, frozen=True)
class Summary:
    """Counts for the sidebar and the filter dropdowns, at one ``(seq, audit_rev)``."""

    seq: int
    audit_rev: int
    pages: int
    indexable: int
    non_indexable: int
    issues: dict[str, int]
    """Issues per severity, every severity present, most severe first."""
    status: dict[str, int]
    """Pages per status class (``2xx`` .. ``5xx``, ``blocked``, ``no_response``)."""
    depth: dict[str, int]
    tabs: dict[str, dict[str, int]]
    """``tabs[tab_id][filter_id]`` is how many rows that filter keeps."""

    def to_json(self) -> dict[str, object]:
        """A JSON-ready dict."""
        return asdict(self)


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
    outlinks: list[Row]
    """``href``, ``text``, ``rel`` and ``crawled`` (True when the target is a page row)."""


class RowStore:
    """Rows and counts over a session, kept in step with it by :meth:`sync`.

    Every public method syncs first, so callers see the latest records and
    audit. Safe to call from several threads.
    """

    def __init__(self, session: CrawlSession) -> None:
        """Wrap ``session``; nothing is read until the first call."""
        self.session = session
        self._lock = threading.RLock()
        self._generation: float | None = None
        self._rules: dict[str, Rule] = {r.id: r for r in session.rules}
        self._reset()

    def _reset(self) -> None:
        self._base: list[Row] = []
        self._by_url: dict[str, PageRecord] = {}
        self._cells: dict[str, Row] = {}
        self._changed: dict[str, int] = {}
        self._index: AuditIndex | None = None
        self._rev = 0
        self._sitemap: frozenset[str] = frozenset()
        self._sitemap_size = -1
        self._summary: Summary | None = None
        self._external: tuple[int, list[Row]] | None = None

    # ----------------------------------------------------------------- sync
    def sync(self) -> SessionState:
        """Pull new records and the latest audit from the session."""
        with self._lock:
            state = self.session.state()
            if state.started_at != self._generation or state.done < len(self._base):
                self._reset()  # a new crawl (or none) replaced the one these rows came from
                self._generation = state.started_at
            keep_query = self.session.config.keep_query
            if len(self._base) < state.done:
                self._refresh_sitemap(keep_query)
                for record in self.session.records_since(len(self._base)):
                    self._base.append(
                        base_row(record, sitemap=self._sitemap, keep_query=keep_query)
                    )
                    self._by_url[record.url] = record
            audit = self.session.audit()
            if audit.rev != self._rev and audit.result is not None and audit.view is not None:
                index = AuditIndex(audit.rev, audit.result, audit.view)
                for row in self._base:
                    url = str(row["url"])
                    cells = index.cells(url)
                    if cells != self._cells.get(url):
                        self._cells[url] = cells
                        self._changed[url] = audit.rev
                self._index = index
                self._rev = audit.rev
            return state

    def _refresh_sitemap(self, keep_query: bool) -> None:
        raw = self.session.sitemap_urls
        if len(raw) != self._sitemap_size:
            self._sitemap = frozenset(
                n for n in (normalize(u, keep_query=keep_query) for u in raw) if n
            )
            self._sitemap_size = len(raw)

    def _merged(self, row: Row) -> Row:
        return {**row, **self._cells.get(str(row["url"]), NO_AUDIT)}

    # ----------------------------------------------------------------- reads
    def rows(self, since: int = 0, rev: int = 0) -> RowsPage:
        """Rows from ``since`` on, plus audit patches for earlier rows changed after ``rev``.

        When more than half the earlier rows changed, the whole table is sent
        instead (``full``), which is cheaper for the grid than many updates.
        """
        with self._lock:
            self.sync()
            since = max(0, min(since, len(self._base)))
            new = [self._merged(r) for r in self._base[since:]]
            patches = [
                {"url": r["url"], **self._cells[str(r["url"])]}
                for r in self._base[:since]
                if self._changed.get(str(r["url"]), 0) > rev
            ]
            if since and len(patches) * 2 > since:
                return RowsPage(len(self._base), self._rev, self.all_rows(), full=True)
            return RowsPage(len(self._base), self._rev, new, patches)

    def all_rows(self) -> list[Row]:
        """Every page row with its current audit cells."""
        with self._lock:
            self.sync()
            return [self._merged(r) for r in self._base]

    def external(self) -> list[Row]:
        """The External tab's rows, cached per record count."""
        with self._lock:
            self.sync()
            if self._external is None or self._external[0] != len(self._base):
                self._external = (len(self._base), external_rows(self._by_url.values()))
            return self._external[1]

    def summary(self) -> Summary:
        """Counts per filter, severity, status class and depth; cached per ``(seq, rev)``."""
        with self._lock:
            self.sync()
            cached = self._summary
            if cached is not None and (cached.seq, cached.audit_rev) == (
                len(self._base),
                self._rev,
            ):
                return cached
            rows = self.all_rows()
            external = self.external()
            tabs: dict[str, dict[str, int]] = {}
            for tab in TABS:
                source = (
                    rows if tab.source == "pages" else external if tab.source == "external" else []
                )
                tabs[tab.id] = {f.id: sum(1 for r in source if matches(r, f)) for f in tab.filters}
            if self._index is not None:
                tabs["issues"]["all"] = len(self._index.result.counts())
            status = Counter(str(r["status_class"]) for r in rows)
            depth = Counter(str(r["depth"]) for r in rows)
            issues = {s.value: 0 for s in Severity}
            if self._index is not None:
                for issue in self._index.result.issues:
                    issues[issue.severity.value] += 1
            self._summary = Summary(
                seq=len(self._base),
                audit_rev=self._rev,
                pages=len(rows),
                indexable=sum(1 for r in rows if r["indexable"] is True),
                non_indexable=sum(1 for r in rows if r["indexable"] is False),
                issues=issues,
                status=dict(sorted(status.items())),
                depth=dict(sorted(depth.items(), key=lambda kv: int(kv[0]))),
                tabs=tabs,
            )
            return self._summary

    def rule_rows(self) -> list[RuleCount]:
        """Rules that fired, most severe first, then by count, then by id."""
        with self._lock:
            self.sync()
            return self._index.result.counts() if self._index else []

    def issue_rows(self) -> list[Row]:
        """Every finding as ``url``, ``rule_id``, ``severity``, ``message``."""
        with self._lock:
            self.sync()
            if self._index is None:
                return []
            return [_issue_row(i) for i in self._index.result.issues]

    def issues_for(self, rule_id: str) -> list[Row]:
        """The findings of one rule, in URL order."""
        with self._lock:
            self.sync()
            if self._index is None:
                return []
            found = [i for i in self._index.result.issues if i.rule_id == rule_id]
            return [_issue_row(i) for i in sorted(found, key=lambda i: i.url)]

    def issue_count(self, rule_id: str) -> int:
        """How many URLs ``rule_id`` flagged."""
        return sum(1 for r in self.issue_rows() if r["rule_id"] == rule_id)

    @property
    def rules(self) -> dict[str, Rule]:
        """Every rule the audit runs, by id."""
        return self._rules

    @property
    def audited(self) -> bool:
        """True once an audit has run over this crawl."""
        with self._lock:
            self.sync()
            return self._index is not None

    def lookup(self, url: str) -> PageRecord | None:
        """The page at ``url`` in any form (``www.``, trailing slash, scheme), or None."""
        with self._lock:
            self.sync()
            key = normalize(url, keep_query=self.session.config.keep_query)
            if key is None:
                return None
            for candidate in (key, _swap_scheme(key)):
                if (record := self._by_url.get(candidate)) is not None:
                    return record
            return None

    def page_detail(self, url: str) -> PageDetail | None:
        """Everything about the page at ``url``, or None if it was not crawled."""
        with self._lock:
            page = self.lookup(url)
            if page is None:
                return None
            cells = self._cells.get(page.url, NO_AUDIT)
            indexable = cells["indexable"]
            issues: list[Row] = [
                {
                    "rule_id": i.rule_id,
                    "severity": i.severity.value,
                    "summary": self._rules[i.rule_id].summary if i.rule_id in self._rules else "",
                    "message": i.message,
                }
                for i in (self._index.issues_for_url(page.url) if self._index else [])
            ]
            return PageDetail(
                page=page,
                indexable=indexable if isinstance(indexable, bool) else None,
                indexability_reason=str(cells["indexability_reason"]),
                issues=issues,
                inlinks=self._index.view.inlinks_to(page.url) if self._index else [],
                outlinks=[
                    {
                        "href": link.href,
                        "text": link.text,
                        "rel": link.rel,
                        "crawled": self.lookup(link.href) is not None,
                    }
                    for link in page.links
                ],
            )


def _issue_row(issue: Issue) -> Row:
    return {
        "url": issue.url,
        "rule_id": issue.rule_id,
        "severity": issue.severity.value,
        "message": issue.message,
    }


def _swap_scheme(url: str) -> str:
    if url.startswith("http://"):
        return "https://" + url.removeprefix("http://")
    return "http://" + url.removeprefix("https://")
