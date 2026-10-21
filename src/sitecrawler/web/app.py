"""The FastAPI application: routes and templates over a :class:`CrawlSnapshot`."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sitecrawler.web.data import CrawlSnapshot, load_snapshot, to_rows

_HERE = Path(__file__).parent

TABS: tuple[tuple[str, str], ...] = (
    ("/", "Overview"),
    ("/pages", "Pages"),
)
"""Navigation: (path, label) in display order."""

templates = Jinja2Templates(directory=_HERE / "templates")
router = APIRouter()


def _snapshot(request: Request) -> CrawlSnapshot:
    return cast(CrawlSnapshot, request.app.state.snapshot)


def _render(request: Request, name: str, active: str, **context: object) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        name,
        {"snapshot": _snapshot(request), "tabs": TABS, "active": active, **context},
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


@router.get("/api/pages")
def api_pages(request: Request) -> JSONResponse:
    """The pages table as JSON rows for the grid."""
    return JSONResponse(to_rows(_snapshot(request).pages))


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
    return app
