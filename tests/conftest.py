"""Shared fixtures: a local HTTP server that serves tests/fixtures/site."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pytest_httpserver import HTTPServer
from werkzeug.wrappers import Request, Response

FIXTURE_SITE = Path(__file__).parent / "fixtures" / "site"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".xml": "application/xml",
    ".txt": "text/plain",
}


def _url_path(file: Path) -> str:
    """Map a fixture file to the URL path it is served at.

    ``index.html`` serves its directory with a trailing slash (``/`` or
    ``/blog/``); ``about.html`` serves ``/about``; non-HTML files keep their
    extension. Like a real web server, ``/blog`` redirects to ``/blog/``.
    """
    rel = file.relative_to(FIXTURE_SITE).as_posix()
    if file.suffix != ".html":
        return f"/{rel}"
    stem = rel.removesuffix(".html")
    if stem == "index":
        return "/"
    if stem.endswith("/index"):
        return f"/{stem.removesuffix('index')}"
    return f"/{stem}"


def _routes() -> dict[str, Any]:  # Any: free-form JSON, see routes.json's _comment
    return dict(json.loads((FIXTURE_SITE / "routes.json").read_text()))


def _html_paths() -> set[str]:
    return {_url_path(f) for f in FIXTURE_SITE.rglob("*.html")}


def _linked_paths() -> set[str]:
    """Root-relative hrefs found in any fixture HTML page, without query or fragment."""
    found: set[str] = set()
    for file in FIXTURE_SITE.rglob("*.html"):
        for href in re.findall(r"href=\"(/[^\"#?]*)", file.read_text(encoding="utf-8")):
            found.add(href.rstrip("/") or "/")
    return found


def site_pages() -> frozenset[str]:
    """Every URL path a full crawl of the fixture site records, as the crawler stores it.

    Directory pages are stored without the trailing slash (``/blog``), the
    root is ``/``. A redirect, special status, truncated response or dead link
    counts only when a fixture page links to it; intermediate redirect hops
    are not pages.
    """
    routes = _routes()
    pages = {p.rstrip("/") or "/" for p in _html_paths()}
    special: set[str] = set()
    for key in ("redirects", "statuses"):
        special |= set(routes.get(key, {}))
    for key in ("truncated", "dead_links"):
        special |= set(routes.get(key, []))
    return frozenset(pages | (special & _linked_paths()))


@pytest.fixture
def pages() -> frozenset[str]:
    """See :func:`site_pages`."""
    return site_pages()


@pytest.fixture(scope="session")
def httpserver_listen_address() -> tuple[str, int]:
    """Bind to IPv4 loopback explicitly.

    On Windows ``localhost`` resolves to ``::1`` first and every connection
    stalls ~2 s before falling back to IPv4, which turns a redirect-loop test
    into a minute-long wait.
    """
    return ("127.0.0.1", 0)


@pytest.fixture
def site(httpserver: HTTPServer) -> str:
    """Serve the fixture site and return its base URL (no trailing slash).

    Sitemap and robots files contain root-relative URLs, which are rewritten to
    absolute ones for this server's port so that the crawler sees a realistic site.
    """
    base = httpserver.url_for("/").rstrip("/")
    httpserver.no_handler_status_code = 404
    routes = _routes()
    extra_headers: dict[str, dict[str, str]] = routes.get("headers", {})

    for file in sorted(FIXTURE_SITE.rglob("*")):
        if not file.is_file() or file.name == "routes.json":
            continue
        content_type = _CONTENT_TYPES.get(file.suffix, "application/octet-stream")
        body = file.read_bytes()
        if file.suffix in (".xml", ".txt"):
            body = body.replace(b"<loc>/", f"<loc>{base}/".encode())
            body = body.replace(b"Sitemap: /", f"Sitemap: {base}/".encode())
        path = _url_path(file)
        httpserver.expect_request(path).respond_with_data(
            body, content_type=content_type, headers=extra_headers.get(path, {})
        )
        if len(path) > 1 and path.endswith("/"):
            _redirect(httpserver, path[:-1], f"{base}{path}", status=301)

    for path, target in routes["redirects"].items():
        location = target if target.startswith("http") else f"{base}{target}"
        _redirect(httpserver, path, location, status=302)
    for path, status in routes.get("statuses", {}).items():
        httpserver.expect_request(path).respond_with_data(
            b"<html><title>Error</title></html>", status=status, content_type="text/html"
        )
    for path in routes.get("truncated", []):
        httpserver.expect_request(path).respond_with_handler(_truncated)
    return base


def _redirect(httpserver: HTTPServer, path: str, location: str, *, status: int) -> None:
    httpserver.expect_request(path).respond_with_data(
        b"", status=status, headers={"Location": location}
    )


def _truncated(_request: Request) -> Response:
    """Announce a long body but send a short one, so the client sees a protocol error."""
    response = Response(b"<html>cut", status=200, content_type="text/html")
    response.automatically_set_content_length = False
    response.headers["Content-Length"] = "4096"
    return response
