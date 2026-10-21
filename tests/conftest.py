"""Shared fixtures: a local HTTP server that serves tests/fixtures/site."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest_httpserver import HTTPServer

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
    routes = json.loads((FIXTURE_SITE / "routes.json").read_text())
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
        _redirect(httpserver, path, f"{base}{target}", status=302)
    return base


def _redirect(httpserver: HTTPServer, path: str, location: str, *, status: int) -> None:
    httpserver.expect_request(path).respond_with_data(
        b"", status=status, headers={"Location": location}
    )
