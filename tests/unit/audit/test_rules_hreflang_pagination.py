from sitecrawler.audit.rules import hreflang, pagination
from sitecrawler.models import HreflangRef
from tests.unit.audit.helpers import SITE, flagged, page


def alts(*pairs: tuple[str, str]) -> tuple[HreflangRef, ...]:
    return tuple(HreflangRef(lang, f"{SITE}{href}") for lang, href in pairs)


def test_lang_codes() -> None:
    bad = page("/bad", hreflang=alts(("english", "/bad"), ("en_GB", "/bad"), ("EN-gb", "/bad")))
    ok = page(
        "/ok",
        hreflang=alts(
            ("en", "/ok"), ("zh-Hant-TW", "/ok"), ("es-419", "/ok"), ("x-default", "/ok")
        ),
    )
    hits = flagged(hreflang.InvalidLang(), [bad, ok, page("/none")])
    assert set(hits) == {"/bad"}
    assert hits["/bad"].message == "en_GB, english"


def test_self_and_x_default() -> None:
    pages = [
        page("/noself", hreflang=alts(("en", "/other"), ("x-default", "/other"))),
        page("/nodefault", hreflang=alts(("en", "/nodefault"), ("fr", "/fr"))),
        page("/fine", hreflang=alts(("en", "/fine/"), ("x-default", "/fine"))),
        page("/none"),
    ]
    assert set(flagged(hreflang.MissingSelf(), pages)) == {"/noself"}
    assert set(flagged(hreflang.MissingXDefault(), pages)) == {"/nodefault"}


def test_return_links_and_targets() -> None:
    en = page(
        "/en",
        hreflang=alts(
            ("en", "/en"), ("fr", "/fr"), ("de", "/de"), ("es", "/gone"), ("it", "/canon")
        ),
    )
    fr = page("/fr", hreflang=alts(("fr", "/fr"), ("en", "/en")))
    de = page("/de", hreflang=alts(("de", "/de")))
    gone = page("/gone", 404)
    canon = page("/canon", canonical=f"{SITE}/elsewhere")
    pages = [en, fr, de, gone, canon]

    back = flagged(hreflang.MissingReturnLink(), pages)
    assert set(back) == {"/en"}
    assert back["/en"].message == f"no return link from {SITE}/de, {SITE}/canon"

    dead = flagged(hreflang.ToNon200(), pages)
    assert set(dead) == {"/en"}
    assert dead["/en"].message == f"{SITE}/gone (404)"

    non_canon = flagged(hreflang.ToNonCanonical(), pages)
    assert set(non_canon) == {"/en"}
    assert non_canon["/en"].message == f"{SITE}/canon -> {SITE}/elsewhere"


def test_return_link_ignores_uncrawled_and_non_html_targets() -> None:
    en = page("/en", hreflang=alts(("fr", "/unknown"), ("de", "/pdf")))
    pdf = page("/pdf", content_type="application/pdf")
    assert flagged(hreflang.MissingReturnLink(), [en, pdf]) == {}


def test_pagination_rules() -> None:
    p1 = page("/p1", rel_next=f"{SITE}/p2")
    p2 = page("/p2", rel_prev=f"{SITE}/p1", rel_next=f"{SITE}/p3")
    p3 = page("/p3", rel_prev=f"{SITE}/p2")
    bad1 = page("/b1", rel_next=f"{SITE}/gone")
    bad2 = page("/b2", rel_prev=f"{SITE}/b1", rel_next=f"{SITE}/b3", canonical=f"{SITE}/b1")
    bad3 = page("/b3", rel_prev=f"{SITE}/p1")
    moved = page("/moved", final_url=f"{SITE}/new")
    to_moved = page("/tm", rel_prev=f"{SITE}/moved")
    gone = page("/gone", 404)
    orphan_next = page("/on", rel_next=f"{SITE}/unknown")
    pages = [p1, p2, p3, bad1, bad2, bad3, moved, to_moved, gone, orphan_next]

    dead = flagged(pagination.ToNon200(), pages)
    assert set(dead) == {"/b1", "/tm"}
    assert dead["/b1"].message == f"next {SITE}/gone (404)"
    assert set(flagged(pagination.CanonicalToFirstPage(), pages)) == {"/b2"}
    broken = flagged(pagination.BrokenSequence(), pages)
    assert set(broken) == {"/b2"}
    assert broken["/b2"].message == f"next {SITE}/b3 has prev {SITE}/p1"


def test_broken_sequence_reports_missing_prev() -> None:
    a = page("/a", rel_next=f"{SITE}/b")
    b = page("/b")
    hits = flagged(pagination.BrokenSequence(), [a, b])
    assert hits["/a"].message == f"next {SITE}/b has prev nothing"
