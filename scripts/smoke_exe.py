"""Smoke-test a built sitecrawler.exe: open it, crawl the fixture site with rendering, close it.

Run with ``uv run python scripts/smoke_exe.py [EXE]`` on Windows after building
(EXE defaults to ``dist/sitecrawler.exe``). The release workflow runs it before
publishing. The exe runs from a temporary folder with empty settings and no
Playwright Chromium, as on a user's PC, so rendering has to go through the
installed Edge (ADR-0015). It drives the exe through the HTTP API its window
shows, finding the port by process name, so the copy gets a name of its own
and a sitecrawler.exe you have open is never touched.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from pytest_httpserver import HTTPServer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.conftest import serve_site  # noqa: E402  (needs ROOT on sys.path)

ACTIVE = {"running", "paused", "stopping", "finishing"}
RENDERED_TITLE = "Rendered title set by JavaScript on load"
IMAGE = "sitecrawler-smoke-test.exe"
"""The copy's file name; a one-file exe re-launches itself, so both processes carry it."""


def listening_port(image: str) -> int | None:
    """The loopback port a process called ``image`` listens on, if any."""
    tasks = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    pids = {row[1] for row in csv.reader(io.StringIO(tasks)) if len(row) > 1}
    netstat = subprocess.run(
        ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, check=True
    ).stdout
    for line in netstat.splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[3] == "LISTENING" and parts[4] in pids:
            host, _, port = parts[1].rpartition(":")
            if host == "127.0.0.1":
                return int(port)
    return None


def call(url: str, body: dict[str, object] | None = None) -> dict[str, object]:
    """GET ``url``, or POST ``body`` to it as JSON, and decode the JSON reply."""
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result: dict[str, object] = json.load(response)
        return result


def smoke(exe: Path, work: Path) -> None:
    """Run the checks; raises AssertionError or TimeoutError on the first failure."""
    copy = work / IMAGE
    shutil.copy2(exe, copy)
    env = {
        **os.environ,
        "APPDATA": str(work / "appdata"),
        "PLAYWRIGHT_BROWSERS_PATH": str(work / "no-browsers"),
    }
    site = HTTPServer(host="127.0.0.1", port=0)
    site.start()
    process = subprocess.Popen([str(copy)], env=env)
    try:
        base = serve_site(site)
        deadline = time.monotonic() + 90
        port = None
        while port is None:
            if time.monotonic() > deadline:
                raise TimeoutError("the exe never started listening")
            time.sleep(0.5)
            port = listening_port(IMAGE)
        api = f"http://127.0.0.1:{port}/api"
        print(f"exe listening on port {port}")  # noqa: T201

        call(f"{api}/crawl/start", {"url": f"{base}/", "render": True, "delay_seconds": 0})
        deadline = time.monotonic() + 180
        crawl = call(f"{api}/crawl")
        while crawl["status"] in ACTIVE:
            if time.monotonic() > deadline:
                raise TimeoutError(f"the crawl did not finish: {crawl}")
            time.sleep(1)
            crawl = call(f"{api}/crawl")
        print(f"crawl {crawl['status']}: {crawl['done']} pages, error {crawl['error']!r}")  # noqa: T201
        assert crawl["status"] == "done", crawl

        rows = call(f"{api}/rows")["rows"]
        assert isinstance(rows, list)
        page = next(row for row in rows if str(row["url"]).endswith("/js-injected"))
        assert page["render_status"] == "rendered", page
        assert page["title"] == RENDERED_TITLE, page
        rendered = sum(row["render_status"] == "rendered" for row in rows)
        print(f"{rendered} pages rendered with Edge; the JavaScript-set title came through")  # noqa: T201
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/IM", IMAGE], capture_output=True)
        process.wait(timeout=30)
        site.stop()


def main() -> int:
    """Smoke-test the exe named on the command line, or ``dist/sitecrawler.exe``."""
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # one line per fixture request
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "sitecrawler.exe"
    if not exe.is_file():
        print(f"no exe at {exe}; build it with pyinstaller first", file=sys.stderr)  # noqa: T201
        return 2
    with tempfile.TemporaryDirectory() as work:
        try:
            smoke(exe, Path(work))
        except (AssertionError, TimeoutError) as exc:
            print(f"smoke test failed: {exc}", file=sys.stderr)  # noqa: T201
            return 1
        # Windows releases the exe file a moment after the process ends.
        time.sleep(3)
    print("smoke test passed")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
