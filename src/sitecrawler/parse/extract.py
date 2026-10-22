r"""Custom extraction and custom search over one page's HTML.

An *extractor* pulls named values off a page with a CSS selector, an XPath
expression or a regular expression; a *search* flags whether a pattern
occurs anywhere in the HTML source. Both are configured as text, on the
command line or in a TOML file, compiled once per crawl and run on every
parsable HTML page by the crawler. Nothing here does I/O.

Command-line grammar::

    NAME=KIND[MODIFIERS]:EXPRESSION      an extractor
    [NAME=]PATTERN                       a search

``KIND`` is ``css``, ``xpath`` or ``regex``. ``MODIFIERS`` is an optional
comma-separated list of ``text`` (default), ``html``, ``attr=NAME`` and
``all``. Examples::

    price=css:.price                     text of the first .price element
    img=css[attr=src,all]:img            src of every image
    sku=xpath://*[@data-sku]/@data-sku   an attribute, straight from XPath
    body=xpath[html]://article           inner HTML of the first article
    ga=regex:G-[A-Z0-9]{6,}              the first Google Analytics id
    gtag=gtag\\('config'                 a search named gtag

TOML form, one table per extractor or search under ``[extract]`` and
``[search]``; a plain string uses the command-line grammar after the name::

    [extract.price]
    css = ".price"
    [extract.img]
    css = "img"
    attr = "src"
    all = true
    [extract]
    sku = "xpath://*[@data-sku]/@data-sku"
    [search]
    gtag = "gtag\\\\('config'"
"""

from __future__ import annotations

import html as html_escape
import logging
import re
import tomllib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import get_args

from cssselect import SelectorError
from lxml import etree
from lxml.cssselect import CSSSelector

from sitecrawler.models import Extraction, ExtractMode, ExtractorKind, ExtractorSpec, SearchSpec
from sitecrawler.parse.html import parse_document, text_of

log = logging.getLogger(__name__)

KINDS: tuple[str, ...] = get_args(ExtractorKind)
MODES: tuple[str, ...] = get_args(ExtractMode)

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_HEAD = re.compile(r"(?P<kind>[a-z]+)(?:\[(?P<mods>[^\]]*)\])?:(?P<expr>.*)", re.DOTALL)
_SEARCH_NAMED = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_-]*)=(?P<pattern>.*)", re.DOTALL)
_GRAMMAR = "NAME=KIND:EXPRESSION, with KIND one of css, xpath or regex"
_TOML_KEYS = frozenset({*KINDS, "mode", "attr", "all"})


# ----------------------------------------------------------------- grammar
def parse_extractor(text: str) -> ExtractorSpec:
    """Parse ``NAME=KIND[MODIFIERS]:EXPRESSION`` and check the expression compiles.

    Raises:
        ValueError: with the offending part named, for anything the grammar
            or the expression's own parser rejects.
    """
    head, sep, rest = text.partition("=")
    name = head.strip()
    if not sep or not _NAME.fullmatch(name):
        msg = f"extractor {text!r}: expected {_GRAMMAR} (NAME is letters, digits, _ and -)"
        raise ValueError(msg)
    match = _HEAD.fullmatch(rest.lstrip())
    if match is None:
        msg = f"extractor {name!r}: expected {_GRAMMAR} after the ="
        raise ValueError(msg)
    kind = match["kind"]
    if kind not in KINDS:
        msg = f"extractor {name!r}: unknown kind {kind!r}; use css, xpath or regex"
        raise ValueError(msg)
    mode, attr, keep_all = _modifiers(name, match["mods"] or "")
    expr = match["expr"] if kind == "regex" else match["expr"].strip()
    return make_extractor(name, kind, expr, mode=mode, attr=attr, all=keep_all)


def _modifiers(name: str, text: str) -> tuple[ExtractMode, str, bool]:
    mode: ExtractMode = "text"
    attr = ""
    keep_all = False
    for raw in text.split(","):
        token = raw.strip()
        if not token:
            continue
        if token in ("text", "html"):
            mode = "text" if token == "text" else "html"
        elif token.startswith("attr="):
            attr = token.removeprefix("attr=").strip()  # make_extractor turns this into mode attr
            if not attr:
                msg = f"extractor {name!r}: mode attr needs the attribute name (attr=NAME)"
                raise ValueError(msg)
        elif token == "all":
            keep_all = True
        elif token == "first":
            keep_all = False
        else:
            msg = (
                f"extractor {name!r}: unknown modifier {token!r}; "
                "use text, html, attr=NAME, all or first"
            )
            raise ValueError(msg)
    return mode, attr, keep_all


def make_extractor(
    name: str,
    kind: str,
    expr: str,
    *,
    mode: str = "text",
    attr: str = "",
    all: bool = False,
) -> ExtractorSpec:
    """Build and validate an :class:`~sitecrawler.models.ExtractorSpec` from loose parts.

    Raises:
        ValueError: a bad name, kind or mode, an attribute mode without an
            attribute, a modifier a regex cannot honour, or an expression its
            parser rejects.
    """
    if not _NAME.fullmatch(name):
        msg = f"extractor {name!r}: names are letters, digits, _ and -, starting with a letter or _"
        raise ValueError(msg)
    if kind not in KINDS:
        msg = f"extractor {name!r}: unknown kind {kind!r}; use css, xpath or regex"
        raise ValueError(msg)
    if mode not in MODES:
        msg = f"extractor {name!r}: unknown mode {mode!r}; use text, html or attr"
        raise ValueError(msg)
    if attr and mode == "text":
        mode = "attr"  # ``attr=NAME`` alone is enough; a stated ``text`` is the default
    if attr and mode != "attr":
        msg = f"extractor {name!r}: mode {mode!r} and attr {attr!r} contradict each other"
        raise ValueError(msg)
    if mode == "attr" and not attr:
        msg = f"extractor {name!r}: mode attr needs the attribute name (attr=NAME)"
        raise ValueError(msg)
    if kind == "regex" and mode != "text":
        msg = (
            f"extractor {name!r}: a regex extractor returns the match (or its first group); "
            f"{mode} does not apply"
        )
        raise ValueError(msg)
    if not expr.strip():
        msg = f"extractor {name!r}: the {kind} expression is empty"
        raise ValueError(msg)
    spec = ExtractorSpec(
        name,
        kind,  # type: ignore[arg-type]  # checked against KINDS above
        expr,
        mode,  # type: ignore[arg-type]  # checked against MODES above
        attr,
        all,
    )
    _compile_extractor(spec)
    return spec


def parse_search(text: str, *, default_name: str = "search") -> SearchSpec:
    """Parse ``[NAME=]PATTERN``; an unnamed search is called ``default_name``.

    Raises:
        ValueError: an empty pattern or one :mod:`re` rejects.
    """
    match = _SEARCH_NAMED.fullmatch(text)
    if match is not None:
        name, pattern = match["name"], match["pattern"]
    else:
        name, pattern = default_name, text
    return make_search(name, pattern)


def make_search(name: str, pattern: str) -> SearchSpec:
    """Build and validate a :class:`~sitecrawler.models.SearchSpec`.

    Raises:
        ValueError: a bad name, an empty pattern or one :mod:`re` rejects.
    """
    if not _NAME.fullmatch(name):
        msg = f"search {name!r}: names are letters, digits, _ and -, starting with a letter or _"
        raise ValueError(msg)
    if not pattern:
        msg = f"search {name!r}: the pattern is empty"
        raise ValueError(msg)
    try:
        re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        msg = f"search {name!r}: invalid regular expression {pattern!r}: {exc}"
        raise ValueError(msg) from None
    return SearchSpec(name, pattern)


def parse_searches(texts: Iterable[str]) -> tuple[SearchSpec, ...]:
    """Parse several ``--search`` values.

    Unnamed searches are called ``search``, ``search2``, ``search3`` and so on.
    """
    specs: list[SearchSpec] = []
    unnamed = 0
    for text in texts:
        if _SEARCH_NAMED.fullmatch(text) is None:
            unnamed += 1
        default = "search" if unnamed <= 1 else f"search{unnamed}"
        specs.append(parse_search(text, default_name=default))
    return tuple(specs)


# -------------------------------------------------------------------- TOML
def load_extract_toml(text: str) -> tuple[tuple[ExtractorSpec, ...], tuple[SearchSpec, ...]]:
    """Read extractors and searches from TOML text (see the module docstring for the shape).

    Raises:
        ValueError: invalid TOML, an unknown key, a missing or doubled kind,
            a wrong value type, or anything :func:`make_extractor` rejects.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        msg = f"extract file: invalid TOML: {exc}"
        raise ValueError(msg) from None
    unknown = set(data) - {"extract", "search"}
    if unknown:
        msg = f"extract file: unknown top-level keys {sorted(unknown)}; use [extract] and [search]"
        raise ValueError(msg)
    extractors = tuple(
        _toml_extractor(name, value) for name, value in _table(data, "extract").items()
    )
    searches = tuple(_toml_search(name, value) for name, value in _table(data, "search").items())
    return extractors, searches


def _table(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        msg = f"extract file: [{key}] must be a table of NAME = ... entries"
        raise ValueError(msg)
    return value


def _toml_extractor(name: str, value: object) -> ExtractorSpec:
    if isinstance(value, str):
        return parse_extractor(f"{name}={value}")
    if not isinstance(value, dict):
        msg = f"extract file: [extract.{name}] must be a table or a KIND:EXPRESSION string"
        raise ValueError(msg)
    unknown = set(value) - _TOML_KEYS
    if unknown:
        msg = f"extract file: [extract.{name}] has unknown keys {sorted(unknown)}"
        raise ValueError(msg)
    kinds = [kind for kind in KINDS if kind in value]
    if len(kinds) != 1:
        msg = f"extract file: [extract.{name}] needs exactly one of css, xpath or regex"
        raise ValueError(msg)
    kind = kinds[0]
    expr = value[kind]
    mode = value.get("mode", "text")
    attr = value.get("attr", "")
    keep_all = value.get("all", False)
    if (
        not isinstance(expr, str)
        or not isinstance(mode, str)
        or not isinstance(attr, str)
        or not isinstance(keep_all, bool)
    ):
        msg = (
            f"extract file: [extract.{name}]: {kind}, mode and attr must be strings "
            "and all a boolean"
        )
        raise ValueError(msg)
    return make_extractor(name, kind, expr, mode=mode, attr=attr, all=keep_all)


def _toml_search(name: str, value: object) -> SearchSpec:
    if isinstance(value, str):
        return make_search(name, value)
    if (
        not isinstance(value, dict)
        or set(value) != {"pattern"}
        or not isinstance(value["pattern"], str)
    ):
        msg = f"extract file: [search.{name}] must be a pattern string or a table with pattern"
        raise ValueError(msg)
    return make_search(name, value["pattern"])


# ----------------------------------------------------------------- running
@dataclass(slots=True, frozen=True)
class _Compiled:
    spec: ExtractorSpec
    xpath: etree.XPath | None = None
    """The compiled selector or expression; None for a regex extractor."""
    pattern: re.Pattern[str] | None = None


_PROBE = parse_document("<html><body><p>probe</p></body></html>")
"""A tiny document every XPath is evaluated against once at compile time.

lxml compiles XPath lazily: an unknown function (``lower-case()`` is XPath 2.0)
or a type error only surfaces on evaluation, which must not happen on the
first crawled page.
"""


def _compile_extractor(spec: ExtractorSpec) -> _Compiled:
    try:
        if spec.kind == "css":
            return _Compiled(spec, xpath=CSSSelector(spec.expr))
        if spec.kind == "xpath":
            xpath = etree.XPath(spec.expr)
            xpath(_PROBE)
            return _Compiled(spec, xpath=xpath)
        return _Compiled(spec, pattern=re.compile(spec.expr))
    except (SelectorError, etree.XPathError, re.error) as exc:
        label = {"css": "CSS selector", "xpath": "XPath expression", "regex": "regex"}[spec.kind]
        msg = f"extractor {spec.name!r}: invalid {label} {spec.expr!r}: {exc}"
        raise ValueError(msg) from None


class ExtractorSet:
    """Every extractor and search of one crawl, compiled once and run per page.

    Build with :func:`compile_extractors`; ``bool(extractors)`` is False when
    there is nothing to run.
    """

    def __init__(self, extractors: Sequence[ExtractorSpec], searches: Sequence[SearchSpec]) -> None:
        """Compile every spec. Raises ``ValueError`` on a bad expression or a repeated name."""
        names: set[str] = set()
        specs: list[ExtractorSpec | SearchSpec] = [*extractors, *searches]
        for spec in specs:
            if spec.name in names:
                msg = f"the name {spec.name!r} is used by more than one extractor or search"
                raise ValueError(msg)
            names.add(spec.name)
        self._extractors = [_compile_extractor(spec) for spec in extractors]
        self._searches = [(spec, re.compile(spec.pattern, re.IGNORECASE)) for spec in searches]
        self._needs_dom = any(c.xpath is not None for c in self._extractors)

    def __bool__(self) -> bool:
        """True when at least one extractor or search is configured."""
        return bool(self._extractors or self._searches)

    @property
    def columns(self) -> tuple[str, ...]:
        """The ``extract_<name>`` and ``search_<name>`` columns, in config order."""
        return (
            *(c.spec.column for c in self._extractors),
            *(spec.column for spec, _ in self._searches),
        )

    def run(self, html: str) -> tuple[Extraction, ...]:
        """Run everything over one page's HTML; one result per extractor, then per search."""
        doc = parse_document(html) if self._needs_dom else None
        results: list[Extraction] = []
        for compiled in self._extractors:
            spec = compiled.spec
            if compiled.pattern is not None:
                values = _regex_values(compiled.pattern, html)
            elif compiled.xpath is not None and doc is not None:
                values = _evaluate(compiled.xpath, doc, spec)
            else:  # pragma: no cover - every compiled extractor has one or the other
                values = []
            kept = values if spec.all else values[:1]
            results.append(Extraction(spec.name, spec.kind, tuple(kept), len(values)))
        for search, pattern in self._searches:
            first = ""
            count = 0
            for match in pattern.finditer(html):
                count += 1
                first = first or match.group(0)
            results.append(Extraction(search.name, "search", (first,) if count else (), count))
        return tuple(results)


def compile_extractors(
    extractors: Sequence[ExtractorSpec] = (), searches: Sequence[SearchSpec] = ()
) -> ExtractorSet:
    """Compile ``extractors`` and ``searches`` into one runnable set.

    Raises:
        ValueError: an expression its parser rejects, or a name used twice.
    """
    return ExtractorSet(extractors, searches)


def _evaluate(xpath: etree.XPath, doc: etree._Element, spec: ExtractorSpec) -> list[str]:
    """Run one compiled selector or expression; a page that trips it counts as no match."""
    try:
        return _node_values(xpath(doc), spec)
    except etree.XPathError as exc:
        # Compile-time probing catches unknown functions; this is the rare page-specific
        # failure (a type error on this document). One extractor must never fail the page.
        log.warning("extractor %r failed on this page: %s", spec.name, exc)
        return []


def _regex_values(pattern: re.Pattern[str], html: str) -> list[str]:
    values: list[str] = []
    for match in pattern.finditer(html):
        value = match.group(1) if pattern.groups else match.group(0)
        if value:
            values.append(value)
    return values


def _node_values(result: object, spec: ExtractorSpec) -> list[str]:
    """Turn an XPath result (elements, strings, a number or a bool) into the values to keep."""
    items = result if isinstance(result, list) else [result]
    values: list[str] = []
    for item in items:
        value = _value_of(item, spec)
        if value:
            values.append(value)
    return values


def _value_of(item: object, spec: ExtractorSpec) -> str:
    if isinstance(item, etree._Element):
        if not isinstance(item.tag, str):  # a comment or processing instruction
            return ""  # type: ignore[unreachable]  # the stubs type every tag as str
        if spec.mode == "attr":
            attr = item.get(spec.attr)
            return attr.strip() if attr is not None else ""
        if spec.mode == "html":
            return _inner_html(item)
        return text_of(item)
    if isinstance(item, bool):
        return "true" if item else "false"
    if isinstance(item, float):
        return str(int(item)) if item.is_integer() else repr(item)
    return " ".join(str(item).split())


def _inner_html(element: etree._Element) -> str:
    text = html_escape.escape(element.text or "", quote=False)
    children = "".join(
        etree.tostring(child, encoding="unicode", method="html") for child in element
    )
    return (text + children).strip()
