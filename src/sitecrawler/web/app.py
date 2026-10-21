"""The FastAPI application: routes and templates over a :class:`CrawlSnapshot`."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from sitecrawler.web.data import CrawlSnapshot, load_snapshot, to_rows

_HERE = Path(__file__).parent

TABS: tuple[tuple[str, str], ...] = (
    ("/", "Overview"),
    ("/pages", "Pages"),
    ("/issues", "Issues"),
    ("/redirects", "Redirects"),
)
"""Navigation: (path, label) in display order."""

templates = Jinja2Templates(directory=_HERE / "templates")
router = APIRouter()


def _snapshot(request: Request) -> CrawlSnapshot:
    return cast(CrawlSnapshot, request.app.state.snapshot)


def _render(
    request: Request, name: str, active: str, status_code: int = 200, **context: object
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        name,
        {"snapshot": _snapshot(request), "tabs": TABS, "active": active, **context},
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse)
def overview(request: Request) -> HTMLResponse:
    """Overview tab: crawl summary, status and depth breakdowns, issue totals."""
    snapshot = _snapshot(request)
    return _render(request, "overview.html", "Overview", overview=snapshot.overview())


@router.get("/pages", response_class=HTMLResponse)
def pages(request: Request) -> HTMLResponse:
    """Pages tab: every column of every fetched page in a filterable grid."""
    return _render(request, "pages.html", "Pages", columns=list(_snapshot(request).pages.columns))


@router.get("/issues", response_class=HTMLResponse)
def issues(request: Request) -> HTMLResponse:
    """Issues tab: one row per rule that fired, most severe first."""
    return _render(request, "issues.html", "Issues", rows=_snapshot(request).rule_rows())


@router.get("/issues/{rule_id}", response_class=HTMLResponse)
def issue_urls(request: Request, rule_id: str) -> HTMLResponse:
    """Fragment for the Issues tab: the URLs one rule flagged, with details."""
    snapshot = _snapshot(request)
    rule = snapshot.rules.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"unknown rule {rule_id!r}")
    return _render(
        request, "issue_urls.html", "Issues", rule=rule, issues=snapshot.issues_for(rule_id)
    )


@router.get("/rules/{rule_id}", response_class=HTMLResponse)
def rule_page(request: Request, rule_id: str) -> HTMLResponse:
    """A rule's explanation: what it checks, why it matters, how to fix it."""
    snapshot = _snapshot(request)
    rule = snapshot.rules.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"unknown rule {rule_id!r}")
    count = snapshot.issue_counts.get(rule_id, 0)
    return _render(request, "rule.html", "Issues", rule=rule, count=count)


@router.get("/redirects", response_class=HTMLResponse)
def redirects(request: Request) -> HTMLResponse:
    """Redirects tab: every hop of every redirected page in a grid."""
    columns = list(_snapshot(request).redirects.columns)
    return _render(request, "redirects.html", "Redirects", columns=columns)


@router.get("/page", response_class=HTMLResponse)
def page_detail(request: Request, url: str = "") -> HTMLResponse:
    """Page detail: everything stored about one URL, its issues and its inlinks."""
    detail = _snapshot(request).page_detail(url) if url else None
    if detail is None:
        raise HTTPException(status_code=404, detail=f"{url} is not in this crawl")
    return _render(request, "page.html", "Pages", detail=detail)


@router.get("/api/pages")
def api_pages(request: Request) -> JSONResponse:
    """The pages table as JSON rows for the grid."""
    return JSONResponse(to_rows(_snapshot(request).pages))


@router.get("/api/issues")
def api_issues(request: Request) -> JSONResponse:
    """The issues table as JSON rows: url, rule_id, severity, message."""
    return JSONResponse(to_rows(_snapshot(request).issues))


@router.get("/api/redirects")
def api_redirects(request: Request) -> JSONResponse:
    """The redirect hops as JSON rows for the grid."""
    return JSONResponse(to_rows(_snapshot(request).redirects))


async def _not_found(request: Request, exc: StarletteHTTPException) -> HTMLResponse:
    if exc.status_code != 404:
        return HTMLResponse(str(exc.detail), status_code=exc.status_code)
    return _render(request, "404.html", "", status_code=404, detail=exc.detail)


def create_app(db: Path) -> FastAPI:
    """Load ``db`` into memory and return the app that serves it.

    Raises:
        ValueError: when ``db`` holds no crawl.
    """
    snapshot = load_snapshot(db)
    app = FastAPI(title="sitecrawler", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.snapshot = snapshot
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    app.include_router(router)
    app.add_exception_handler(StarletteHTTPException, _not_found)  # type: ignore[arg-type]
    return app
