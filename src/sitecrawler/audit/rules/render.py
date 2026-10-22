"""Rendering rules: what JavaScript changes, and pages the browser could not render.

Both only fire on crawls run with ``--render``; a page that was never
rendered has no diff and no error.
"""

from __future__ import annotations

from collections.abc import Iterable

from sitecrawler.audit.rule import HtmlPageRule
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Rendering"


class Differs(HtmlPageRule):
    """The rendered DOM disagrees with the raw HTML on something the audit reads."""

    id = "render.differs"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Title, canonical, meta or links change when JavaScript runs"
    why = (
        "Google does run JavaScript, but in a second pass that can lag the raw crawl "
        "by days, and most other crawlers, social previews and AI agents never run it. "
        "A title, canonical, robots directive or navigation link that only exists after "
        "rendering is seen late or not at all, and one that the script changes leaves "
        "two versions of the page competing for the same URL."
    )
    fix = (
        "Put the title, canonical, meta tags and the links that matter in the "
        "server-rendered HTML, and let JavaScript enhance the page rather than define "
        "it. If the framework cannot, use server-side rendering or pre-rendering for "
        "crawlers."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag a rendered page whose diff lists any change; the message names them."""
        if page.render is not None and page.render.changed:
            yield self.issue(page, page.render.describe())


class Failed(HtmlPageRule):
    """The raw fetch worked but the browser did not deliver a DOM."""

    id = "render.failed"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Page could not be rendered in headless Chromium"
    why = (
        "The HTML was fetched, but the browser did not deliver a usable DOM: the page "
        "did not finish loading within the render timeout, the second request got an "
        "HTTP error, the response started a download, or a script sent the browser to "
        "another site. What JavaScript adds to this URL is unknown. Googlebot gives up "
        "on slow pages too, and indexes whatever it had by then."
    )
    fix = (
        "Open the page with the browser's network panel: long-polling, slow third-party "
        "scripts or endless retries keep it from going idle. Fix the page, or crawl "
        "with --render-wait load or a longer --render-timeout. An HTTP error on the "
        "second request usually means the site throttles repeat visits; raise --delay."
    )

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag a page with a render error; the message is the error."""
        if page.render_error:
            yield self.issue(page, page.render_error)
