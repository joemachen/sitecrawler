"""The FastAPI application: one page over a :class:`CrawlSession`, plus JSON for its grid."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from sitecrawler.models import CrawlConfig
from sitecrawler.session import CrawlSession, SessionBusyError
from sitecrawler.web.rows import RowStore
from sitecrawler.web.tabs import TABS, to_json

_HERE = Path(__file__).parent

templates = Jinja2Templates(directory=_HERE / "templates")
router = APIRouter()


def _rows(request: Request) -> RowStore:
    return cast(RowStore, request.app.state.rows)


def _render(request: Request, name: str, status_code: int = 200, **context: object) -> HTMLResponse:
    rows = _rows(request)
    return templates.TemplateResponse(
        request,
        name,
        {"state": rows.session.state(), "rows": rows, **context},
        status_code=status_code,
    )


def crawl_json(rows: RowStore) -> dict[str, object]:
    """The session state as the ``/api/crawl`` payload."""
    state = rows.sync()
    return {
        "status": state.status.value,
        "start_url": state.start_url,
        "db": str(state.db) if state.db else None,
        "read_only": state.read_only,
        "done": state.done,
        "queued": state.queued,
        "seq": state.done,
        "audit_rev": state.audit_rev,
        "elapsed": round(state.elapsed, 1),
        "error": state.error,
    }


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    """The app shell: tab strip, grid, detail pane and sidebar, filled by JavaScript."""
    return _render(request, "index.html", tabs=TABS, specs=to_json())


@router.get("/issues", response_class=HTMLResponse)
def issues(request: Request) -> HTMLResponse:
    """Fragment for the Issues tab: one row per rule that fired, most severe first."""
    rows = _rows(request)
    return _render(request, "issues.html", rule_rows=rows.rule_rows(), audited=rows.audited)


@router.get("/issues/{rule_id}", response_class=HTMLResponse)
def issue_urls(request: Request, rule_id: str) -> HTMLResponse:
    """Fragment for the Issues tab: the URLs one rule flagged, with details."""
    rows = _rows(request)
    rule = rows.rules.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"unknown rule {rule_id!r}")
    return _render(request, "issue_urls.html", rule=rule, issues=rows.issues_for(rule_id))


@router.get("/rules/{rule_id}", response_class=HTMLResponse)
def rule_page(request: Request, rule_id: str) -> HTMLResponse:
    """A rule's explanation: what it checks, why it matters, how to fix it."""
    rows = _rows(request)
    rule = rows.rules.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"unknown rule {rule_id!r}")
    return _render(request, "rule.html", rule=rule, count=rows.issue_count(rule_id))


@router.get("/page", response_class=HTMLResponse)
def page_detail(request: Request, url: str = "") -> HTMLResponse:
    """Page detail: everything stored about one URL, its issues and its links."""
    detail = _rows(request).page_detail(url) if url else None
    if detail is None:
        raise HTTPException(status_code=404, detail=f"{url} is not in this crawl")
    return _render(request, "page.html", detail=detail)


@router.get("/api/crawl")
def api_crawl(request: Request) -> JSONResponse:
    """Where the crawl is: status, counts, sequence and audit revision."""
    return JSONResponse(crawl_json(_rows(request)))


@router.get("/api/rows")
def api_rows(request: Request, since: int = 0, rev: int = 0) -> JSONResponse:
    """Page rows from ``since`` on, plus audit patches for rows changed after ``rev``."""
    return JSONResponse(_rows(request).rows(since, rev).to_json())


@router.get("/api/external")
def api_external(request: Request) -> JSONResponse:
    """The External tab's rows."""
    return JSONResponse(_rows(request).external())


@router.get("/api/summary")
def api_summary(request: Request) -> JSONResponse:
    """Counts per tab filter, severity, status class and depth."""
    return JSONResponse(_rows(request).summary().to_json())


@router.get("/api/issues")
def api_issues(request: Request) -> JSONResponse:
    """Every finding as JSON rows: url, rule_id, severity, message."""
    return JSONResponse(_rows(request).issue_rows())


class StartRequest(BaseModel):
    """Body of ``POST /api/crawl/start``: the crawl options the UI exposes."""

    url: str
    max_pages: int = Field(default=5000, ge=1)
    delay_seconds: float = Field(default=0.5, ge=0)
    workers: int = Field(default=4, ge=1, le=32)
    timeout_seconds: float = Field(default=20.0, gt=0)
    use_sitemap: bool = True
    keep_query: bool = False
    respect_robots: bool = True

    def to_config(self) -> CrawlConfig:
        """The crawl config these options describe."""
        return CrawlConfig(
            start_url=self.url.strip(),
            max_pages=self.max_pages,
            delay_seconds=self.delay_seconds,
            workers=self.workers,
            timeout_seconds=self.timeout_seconds,
            use_sitemap=self.use_sitemap,
            keep_query=self.keep_query,
            respect_robots=self.respect_robots,
        )


@router.post("/api/crawl/start")
def api_crawl_start(request: Request, body: StartRequest) -> JSONResponse:
    """Start a crawl into a new file. 400 for a bad URL, 409 while one is running."""
    rows = _rows(request)
    try:
        rows.session.start(body.to_config())
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(crawl_json(rows))


@router.post("/api/crawl/{action}")
def api_crawl_action(request: Request, action: str) -> JSONResponse:
    """``pause``, ``resume``, ``stop`` or ``clear`` the crawl; 409 when the status forbids it."""
    rows = _rows(request)
    session = rows.session
    actions = {
        "pause": session.pause,
        "resume": session.resume,
        "stop": session.stop,
        "clear": session.clear,
    }
    transition = actions.get(action)
    if transition is None:
        raise HTTPException(status_code=404, detail=f"unknown action {action!r}")
    try:
        transition()
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(crawl_json(rows))


async def _not_found(request: Request, exc: StarletteHTTPException) -> HTMLResponse | JSONResponse:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": str(exc.detail)}, status_code=exc.status_code)
    if exc.status_code != 404:
        return HTMLResponse(str(exc.detail), status_code=exc.status_code)
    return _render(request, "404.html", status_code=404, detail=exc.detail)


def create_app(db: Path | None = None, *, crawls_dir: Path = Path("crawls")) -> FastAPI:
    """The app over ``db`` (read-only) or, with no file, over an empty session.

    Args:
        db: A stored crawl to open, or None to start idle.
        crawls_dir: Where crawls started from the UI are written.

    Raises:
        ValueError: when ``db`` holds no crawl.
    """
    session = CrawlSession.open(db, crawls_dir) if db is not None else CrawlSession(crawls_dir)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            session.close()

    app = FastAPI(
        title="sitecrawler", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.session = session
    app.state.rows = RowStore(session)
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    app.include_router(router)
    app.add_exception_handler(StarletteHTTPException, _not_found)  # type: ignore[arg-type]
    return app
