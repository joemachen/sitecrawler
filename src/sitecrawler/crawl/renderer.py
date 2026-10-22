"""JavaScript rendering in headless Chromium, through Playwright's async API.

The renderer is optional: Playwright is only imported when a crawl asks for
rendering, so a plain crawl never needs a browser installed. It uses the
async API because the crawl loop is an asyncio loop; Playwright's sync API
starts a loop of its own and refuses to run inside one.
"""

from __future__ import annotations

import asyncio
import importlib.util
import time
from types import TracebackType
from typing import TYPE_CHECKING, Literal, cast
from urllib.parse import urlparse

from sitecrawler.crawl.throttle import HostThrottle
from sitecrawler.models import RenderResult

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright, Route

WaitStrategy = Literal["load", "domcontentloaded", "networkidle"]
"""When a navigation counts as finished: Playwright's ``wait_until`` events."""

WAIT_STRATEGIES: tuple[str, ...] = ("load", "domcontentloaded", "networkidle")
"""The values ``wait`` accepts."""

INSTALL_HINT = (
    "JavaScript rendering needs Playwright and Chromium: "
    "run `uv sync --extra render` (or `pip install sitecrawler[render]`) "
    "and then `playwright install chromium`"
)


class RenderUnavailableError(ValueError):
    """Playwright or Chromium is missing, or the browser could not start."""


def playwright_available() -> bool:
    """True when the ``playwright`` package is importable."""
    return importlib.util.find_spec("playwright") is not None


def require_playwright() -> None:
    """Raise :class:`RenderUnavailableError`, with an install hint, unless Playwright imports."""
    if not playwright_available():
        raise RenderUnavailableError(INSTALL_HINT)


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
            ValueError: ``wait`` is not one of :data:`WAIT_STRATEGIES`, or
                ``workers`` is below 1.
        """
        if wait not in WAIT_STRATEGIES:
            msg = f"render_wait must be one of {', '.join(WAIT_STRATEGIES)}, not {wait!r}"
            raise ValueError(msg)
        if workers < 1:
            msg = f"render_workers must be at least 1, not {workers}"
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
        """Start Playwright and launch Chromium.

        Raises:
            RenderUnavailableError: Playwright is not installed or Chromium
                could not be launched (usually ``playwright install chromium``
                has not been run).
        """
        require_playwright()
        from playwright.async_api import Error, async_playwright

        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch()
        except Error as exc:
            await self._playwright.stop()
            self._playwright = None
            msg = f"could not start Chromium: {str(exc).splitlines()[0]}. {INSTALL_HINT}"
            raise RenderUnavailableError(msg) from exc
        self._context = await self._browser.new_context(user_agent=self.user_agent)
        if self.block:
            await self._context.route("**/*", self._route)
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

        Never raises for page errors or timeouts; those come back with
        ``ok=False`` and an ``error`` message.
        """
        if self._context is None or self._slots is None:
            msg = "Renderer must be entered with `async with` before rendering"
            raise RuntimeError(msg)
        from playwright.async_api import Error, TimeoutError

        timeout_ms = self.timeout_seconds * 1000
        async with self._slots:
            if self.throttle is not None:
                await self.throttle.acquire(urlparse(url).netloc.lower())
            started = time.monotonic()
            page = await self._context.new_page()
            try:
                response = await page.goto(url, wait_until=self.wait, timeout=timeout_ms)
                if self.selector:
                    await page.wait_for_selector(self.selector, timeout=timeout_ms)
                html = await page.content()
                return RenderResult(
                    url=url,
                    ok=True,
                    html=html,
                    final_url=page.url,
                    status_code=response.status if response is not None else None,
                    elapsed_ms=_elapsed(started),
                )
            except TimeoutError:
                waited = f"{self.wait}" + (f" and {self.selector!r}" if self.selector else "")
                return RenderResult(
                    url=url,
                    ok=False,
                    elapsed_ms=_elapsed(started),
                    error=f"render timed out after {self.timeout_seconds:g}s waiting for {waited}",
                )
            except Error as exc:
                return RenderResult(
                    url=url,
                    ok=False,
                    elapsed_ms=_elapsed(started),
                    error=f"render failed: {str(exc).splitlines()[0][:200]}",
                )
            finally:
                await page.close()


def _elapsed(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
