"""JavaScript rendering in headless Chromium, through Playwright's async API.

The renderer is optional: Playwright is only imported when a crawl asks for
rendering, so a plain crawl never needs a browser installed. It launches the
Chromium that ``playwright install chromium`` downloads, and falls back to
the installed Microsoft Edge when that is missing, which is how the
standalone exe renders (ADR-0015). It uses the
async API because the crawl loop is an asyncio loop; Playwright's sync API
starts a loop of its own and refuses to run inside one.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import logging
import sys
import time
from types import TracebackType
from typing import TYPE_CHECKING, Literal, cast
from urllib.parse import urlparse

from sitecrawler.crawl.throttle import HostThrottle
from sitecrawler.models import RenderResult

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright, Route

log = logging.getLogger(__name__)

WaitStrategy = Literal["load", "domcontentloaded", "networkidle"]
"""When a navigation counts as finished: Playwright's ``wait_until`` events."""

WAIT_STRATEGIES: tuple[str, ...] = ("load", "domcontentloaded", "networkidle")
"""The values ``wait`` accepts."""

RETRIES = 1
"""Extra attempts after a ``net::ERR_*`` navigation failure (a transient socket error)."""

RETRY_DELAY_SECONDS = 0.5

INSTALL_HINT = (
    "JavaScript rendering needs Playwright and Chromium: "
    "run `uv sync --extra render` (or `pip install sitecrawler[render]`) "
    "and then `playwright install chromium`"
)

FROZEN_HINT = (
    "the standalone sitecrawler.exe renders with Microsoft Edge: "
    "install Edge from https://www.microsoft.com/edge, or untick Render JavaScript"
)
"""Shown instead of :data:`INSTALL_HINT` in the PyInstaller exe, where pip and uv do not apply."""

EDGE_CHANNEL = "msedge"
"""Playwright's name for the installed Microsoft Edge, tried when its own Chromium is missing."""


class RenderUnavailableError(ValueError):
    """Playwright or Chromium is missing, or the browser could not start."""


def playwright_available() -> bool:
    """True when the ``playwright`` package is importable."""
    return importlib.util.find_spec("playwright") is not None


def install_hint() -> str:
    """How to get rendering working: :data:`FROZEN_HINT` in the exe, else :data:`INSTALL_HINT`."""
    return FROZEN_HINT if getattr(sys, "frozen", False) else INSTALL_HINT


def render_unavailable_reason() -> str | None:
    """Why a crawl cannot render here, or None when Playwright imports.

    Chromium itself is only found when the browser launches, so None does not
    promise that rendering will start.
    """
    return None if playwright_available() else install_hint()


def require_playwright() -> None:
    """Raise :class:`RenderUnavailableError`, with an install hint, unless Playwright imports."""
    reason = render_unavailable_reason()
    if reason is not None:
        raise RenderUnavailableError(reason)


def _first_line(exc: Exception) -> str:
    """Playwright's errors run to a page of call log; the first line says what failed."""
    text = str(exc)
    return text.splitlines()[0] if text else type(exc).__name__


class Renderer:
    """Loads pages in one headless Chromium and hands back their rendered DOM.

    Use as an async context manager; the browser starts on entry and closes
    on exit::

        async with Renderer(agent, workers=2) as renderer:
            result = await renderer.render(url)

    At most ``workers`` tabs are open at once. Navigation waits for ``wait``
    (``load``, ``domcontentloaded`` or ``networkidle``), then optionally for
    ``selector`` to appear, each bounded by ``timeout_seconds``. Resource
    types listed in ``block`` are never requested. When a ``throttle`` is
    given, navigations respect the same per-host delay as the HTTP fetcher.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        workers: int = 2,
        wait: str = "networkidle",
        selector: str = "",
        timeout_seconds: float = 30.0,
        block: tuple[str, ...] = ("image", "font", "media"),
        throttle: HostThrottle | None = None,
    ) -> None:
        """Validate the options; nothing starts until the context is entered.

        Raises:
            ValueError: ``wait`` is not one of :data:`WAIT_STRATEGIES`,
                ``workers`` is below 1, or ``timeout_seconds`` is not positive
                (Playwright reads a timeout of 0 as "wait forever").
        """
        if wait not in WAIT_STRATEGIES:
            msg = f"render_wait must be one of {', '.join(WAIT_STRATEGIES)}, not {wait!r}"
            raise ValueError(msg)
        if workers < 1:
            msg = f"render_workers must be at least 1, not {workers}"
            raise ValueError(msg)
        if timeout_seconds <= 0:
            msg = f"render_timeout must be above 0 seconds, not {timeout_seconds:g}"
            raise ValueError(msg)
        self.user_agent = user_agent
        self.workers = workers
        self.wait = cast(WaitStrategy, wait)
        self.selector = selector
        self.timeout_seconds = timeout_seconds
        self.block = frozenset(block)
        self.throttle = throttle
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._slots: asyncio.Semaphore | None = None

    async def __aenter__(self) -> Renderer:
        """Start Playwright and launch Chromium, or the installed Edge without it.

        Raises:
            RenderUnavailableError: Playwright is not installed, or neither
                Playwright's Chromium (``playwright install chromium``) nor
                Microsoft Edge could be launched.
        """
        require_playwright()
        from playwright.async_api import Error, async_playwright

        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch()
        except Error as chromium_exc:
            log.info("Chromium did not start, trying Microsoft Edge: %s", _first_line(chromium_exc))
            try:
                self._browser = await self._playwright.chromium.launch(channel=EDGE_CHANNEL)
            except Error as edge_exc:
                await self._playwright.stop()
                self._playwright = None
                msg = (
                    f"could not start Chromium ({_first_line(chromium_exc)}) "
                    f"or Microsoft Edge ({_first_line(edge_exc)}). {install_hint()}"
                )
                raise RenderUnavailableError(msg) from edge_exc
        try:
            self._context = await self._browser.new_context(user_agent=self.user_agent)
            if self.block:
                await self._context.route("**/*", self._route)
        except Error:
            # Nothing may be left running when the crawl never starts.
            await self.aclose()
            raise
        self._slots = asyncio.Semaphore(self.workers)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the browser and stop Playwright."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close whatever is open; safe to call twice."""
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._slots = None

    def should_block(self, resource_type: str) -> bool:
        """True when a request for ``resource_type`` (``image``, ``font``, ...) is dropped."""
        return resource_type in self.block

    async def _route(self, route: Route) -> None:
        if self.should_block(route.request.resource_type):
            await route.abort()
        else:
            await route.continue_()

    async def render(self, url: str) -> RenderResult:
        """Load ``url`` in a fresh tab and return the DOM once the page has settled.

        Never raises for page errors, timeouts or a lost browser; those come
        back with ``ok=False`` and an ``error`` message. A navigation that
        ends on an HTTP error (status 400 or above) is a failure too: its DOM
        is the server's error page, not the page being audited.
        """
        if self._context is None or self._slots is None:
            msg = "Renderer must be entered with `async with` before rendering"
            raise RuntimeError(msg)
        from playwright.async_api import Error, Page, TimeoutError

        timeout_ms = self.timeout_seconds * 1000
        async with self._slots:
            started = time.monotonic()
            for attempt in range(1, RETRIES + 2):
                if self.throttle is not None:
                    await self.throttle.acquire(urlparse(url).netloc.lower())
                page: Page | None = None
                try:
                    page = await self._context.new_page()
                    response = await page.goto(url, wait_until=self.wait, timeout=timeout_ms)
                    status = response.status if response is not None else None
                    if status is not None and status >= 400:
                        return RenderResult(
                            url=url,
                            ok=False,
                            status_code=status,
                            elapsed_ms=_elapsed(started),
                            error=f"render returned HTTP {status}",
                        )
                    if self.selector:
                        await page.wait_for_selector(self.selector, timeout=timeout_ms)
                    html = await page.content()
                    return RenderResult(
                        url=url,
                        ok=True,
                        html=html,
                        final_url=page.url,
                        status_code=status,
                        elapsed_ms=_elapsed(started),
                    )
                except TimeoutError:
                    waited = f"{self.wait}" + (f" and {self.selector!r}" if self.selector else "")
                    timed_out = (
                        f"render timed out after {self.timeout_seconds:g}s waiting for {waited}"
                    )
                    return RenderResult(
                        url=url, ok=False, elapsed_ms=_elapsed(started), error=timed_out
                    )
                except Error as exc:
                    # Covers a page that could not load and a browser that has gone away.
                    reason = str(exc).splitlines()[0][:200]
                    if "net::ERR_" in reason and attempt <= RETRIES:
                        # A socket-level failure (reset, buffer space, empty response) is
                        # usually transient; one more try avoids a false render.failed.
                        log.info("retrying render of %s after %s", url, reason)
                        await asyncio.sleep(RETRY_DELAY_SECONDS)
                        continue
                    return RenderResult(
                        url=url,
                        ok=False,
                        elapsed_ms=_elapsed(started),
                        error=f"render failed: {reason}",
                    )
                finally:
                    if page is not None:
                        with contextlib.suppress(Error):  # the browser may already be gone
                            await page.close()
        raise AssertionError("unreachable: the last attempt always returns")  # pragma: no cover


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
