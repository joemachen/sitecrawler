"""Hreflang rules: language codes, return links, self reference, x-default and targets."""

from __future__ import annotations

import re
from collections.abc import Iterable

from sitecrawler.audit.rule import HtmlPageRule
from sitecrawler.audit.rules._common import describe_target
from sitecrawler.audit.rules.canonicals import effective_canonical
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Hreflang"
LANG_CODE = re.compile(r"^[a-z]{2,3}(-[a-z]{4})?(-[a-z]{2}|-\d{3})?$", re.IGNORECASE)
"""ISO 639-1/2 language, optional ISO 15924 script, optional ISO 3166-1 region or UN M.49 area."""


def _valid_lang(code: str) -> bool:
    return code.lower() == "x-default" or bool(LANG_CODE.match(code))


class InvalidLang(HtmlPageRule):
    """Language code Google will not recognise."""

    id = "hreflang.invalid_lang"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "hreflang uses an invalid language or region code"
    why = (
        "Hreflang values must be ISO 639-1 language codes, optionally with an ISO "
        "3166-1 region (``en-GB``) or script, or ``x-default``. Anything else "
        "(``en-UK``, ``english``, ``uk``) is ignored, silently."
    )
    fix = "Use the ISO codes: language in lowercase, region in uppercase, joined by a hyphen."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag each invalid code once per page."""
        bad = sorted({h.lang for h in page.hreflang if not _valid_lang(h.lang)})
        if bad:
            yield self.issue(page, ", ".join(bad))


class MissingSelf(HtmlPageRule):
    """Hreflang set that does not include the page itself."""

    id = "hreflang.missing_self"
    severity = Severity.LOW
    category = CATEGORY
    summary = "hreflang set does not reference the page itself"
    why = (
        "Each page in a language cluster must list every version including its own; "
        "without the self reference the annotations on this page may be discarded."
    )
    fix = "Add an hreflang link whose href is this page's own canonical URL."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with hreflang links but none pointing at themselves."""
        if page.hreflang and not any(crawl.same_page(h.href, page.url) for h in page.hreflang):
            yield self.issue(page)


class MissingXDefault(HtmlPageRule):
    """No fallback for unmatched languages."""

    id = "hreflang.missing_x_default"
    severity = Severity.LOW
    category = CATEGORY
    summary = "hreflang set has no x-default"
    why = (
        "``x-default`` tells search engines which version to show users whose language "
        "matches none of the alternates. Without it they pick one, often the wrong one."
    )
    fix = 'Add <link rel="alternate" hreflang="x-default" href=...> pointing at the fallback page.'

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag pages with hreflang links but no x-default."""
        if page.hreflang and not any(h.lang.lower() == "x-default" for h in page.hreflang):
            yield self.issue(page)


class MissingReturnLink(HtmlPageRule):
    """Alternate page that does not link back."""

    id = "hreflang.missing_return_link"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "hreflang alternate does not link back to this page"
    why = (
        "Hreflang only works when both pages confirm the relationship. If the "
        "alternate does not list this page, Google ignores the annotation on both."
    )
    fix = "Add the matching hreflang link on every alternate page."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag crawled alternates whose hreflang set omits this page."""
        missing: list[str] = []
        for alt in page.hreflang:
            if crawl.same_page(alt.href, page.url):
                continue
            target = crawl.page_for(alt.href)
            if target is None or not crawl.is_html_page(target):
                continue
            if not any(crawl.same_page(back.href, page.url) for back in target.hreflang):
                missing.append(alt.href)
        if missing:
            yield self.issue(page, "no return link from " + ", ".join(missing))


class ToNon200(HtmlPageRule):
    """Alternate that is not a live page."""

    id = "hreflang.to_non_200"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "hreflang points at a URL that is not a 200 page"
    why = (
        "An alternate that is missing, errors or redirects breaks the whole cluster "
        "for that language and wastes crawl budget."
    )
    fix = "Point hreflang at the final, live URL of each language version."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag crawled alternates that are not a plain 200."""
        bad: list[str] = []
        for alt in page.hreflang:
            target = crawl.page_for(alt.href)
            if target is None:
                continue
            problem = describe_target(crawl, target)
            if problem:
                bad.append(f"{alt.href} {problem}")
        if bad:
            yield self.issue(page, ", ".join(bad))


class ToNonCanonical(HtmlPageRule):
    """Alternate that canonicalises elsewhere."""

    id = "hreflang.to_non_canonical"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "hreflang points at a URL whose canonical is a different page"
    why = (
        "Hreflang must reference canonical URLs. Pointing at a page that defers to "
        "another URL sends search engines a contradiction, and the alternate is dropped."
    )
    fix = "Use each alternate's canonical URL in the hreflang link."

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag crawled alternates whose effective canonical is not themselves."""
        bad: list[str] = []
        for alt in page.hreflang:
            target = crawl.page_for(alt.href)
            if target is None:
                continue
            canonical = effective_canonical(target)
            if canonical and not crawl.same_page(canonical, target.url):
                bad.append(f"{alt.href} -> {canonical}")
        if bad:
            yield self.issue(page, ", ".join(bad))
