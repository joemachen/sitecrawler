"""Structured data rules: JSON-LD, microdata and RDFa that search engines cannot use.

All six read the crawl's structured data index (``crawl.structured``,
ADR-0013), which checks each parsed HTML page's items against the bundled
schema.org vocabulary and Google's rich-result requirements. A page gets one
issue per rule; the message lists every finding of that kind on the page.
"""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable

from sitecrawler.audit.rule import HtmlPageRule
from sitecrawler.audit.structured import FindingKind
from sitecrawler.audit.view import CrawlView
from sitecrawler.models import Issue, PageRecord, Severity

CATEGORY = "Structured data"


class _StructuredRule(HtmlPageRule):
    """One issue per page that has findings of :attr:`kind`."""

    @property
    @abstractmethod
    def kind(self) -> FindingKind:
        """The finding kind this rule reports."""

    def check_html(self, page: PageRecord, crawl: CrawlView) -> Iterable[Issue]:
        """Flag the page with its findings of this kind, joined."""
        found = crawl.structured.findings_for(page.url, self.kind)
        if found:
            yield self.issue(page, "; ".join(dict.fromkeys(f.message for f in found)))


class InvalidJson(_StructuredRule):
    """A JSON-LD block that does not parse."""

    id = "schema.invalid_json"
    kind = "invalid_json"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "JSON-LD block is not valid JSON"
    why = (
        "A JSON-LD block with a syntax error, such as a missing comma, a trailing "
        "comma or an unescaped quote, is thrown away whole: none of the items in it "
        "count, so the page loses every rich result the block was meant to earn. "
        "The message gives the parser's complaint and the page line."
    )
    fix = (
        "Fix the syntax at the line given. Generate the block with a JSON encoder "
        "(json_encode, JSON.stringify) rather than by pasting strings into a template."
    )


class MissingRequired(_StructuredRule):
    """A rich-result type without a property Google requires."""

    id = "schema.missing_required"
    kind = "missing_required"
    severity = Severity.HIGH
    category = CATEGORY
    summary = "Structured data lacks a property Google requires for its rich result"
    why = (
        "Google only shows a rich result (product price and rating, event dates, "
        "recipe card, breadcrumb trail, video thumbnail) when the item has every "
        "required property; without one the item is ineligible. Checked for "
        "Product, Article, BreadcrumbList, Organization, LocalBusiness, Recipe, "
        "Event and VideoObject and their subtypes. A nested requirement such as "
        "offers.price applies to every offer."
    )
    fix = (
        "Add the property named in the message, with a real value from the page. "
        "Check the result in Google's Rich Results Test."
    )


class UnknownType(_StructuredRule):
    """An ``@type`` that schema.org does not define."""

    id = "schema.unknown_type"
    kind = "unknown_type"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Structured data uses a type that is not in schema.org"
    why = (
        "A misspelt or invented type (Prodcut, BlogPost) means nothing to search "
        "engines, so the item and everything in it is ignored. Types from other "
        "vocabularies, written with their full IRI, are not checked."
    )
    fix = (
        "Use the schema.org type name exactly as it is spelt on schema.org, including its capitals."
    )


class Conflicting(_StructuredRule):
    """Two items that describe the same thing differently."""

    id = "schema.conflicting"
    kind = "conflicting"
    severity = Severity.MEDIUM
    category = CATEGORY
    summary = "Structured data items describe the same thing with different values"
    why = (
        "When two items of one type name the same entity (the same @id or url), "
        "typically a theme's microdata and a plugin's JSON-LD, and disagree on a "
        "property such as the name or price, search engines have to guess which is "
        "right, and may use neither."
    )
    fix = (
        "Keep one source of structured data per entity, or make both say the same "
        "thing. Removing the older markup is usually simplest."
    )


class UnknownProperty(_StructuredRule):
    """A property that schema.org does not define for the item's type."""

    id = "schema.unknown_property"
    kind = "unknown_property"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Structured data uses a property its type does not have"
    why = (
        "A property that is misspelt (authr) or belongs to another type (price on a "
        "Product rather than its Offer) is ignored, so whatever it was meant to say "
        "is lost. Inherited properties count: name is fine on every type."
    )
    fix = (
        "Check the type's page on schema.org for the right property, or move the "
        "value onto the nested item it belongs to."
    )


class MissingRecommended(_StructuredRule):
    """A rich-result type without properties Google recommends."""

    id = "schema.missing_recommended"
    kind = "missing_recommended"
    severity = Severity.LOW
    category = CATEGORY
    summary = "Structured data lacks properties Google recommends for its rich result"
    why = (
        "Recommended properties are not needed for eligibility, but they decide how "
        "much the rich result shows (ratings, availability, dates, author) and "
        "whether it is chosen over a competitor's."
    )
    fix = "Add the properties listed in the message where the page has the information."
