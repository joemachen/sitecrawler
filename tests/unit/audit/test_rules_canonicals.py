from sitecrawler.audit.rules import canonicals
from tests.unit.audit.helpers import SITE, flagged, links, page


def test_missing_and_header_canonical_counts() -> None:
    pages = [
        page("/none", canonical=""),
        page("/header", canonical="", canonical_header=f"{SITE}/header"),
        page("/ok"),
    ]
    assert set(flagged(canonicals.Missing(), pages)) == {"/none"}


def test_to_non_200_judges_crawled_targets_only() -> None:
    pages = [
        page("/to-404", canonical=f"{SITE}/gone"),
        page("/gone", 404),
        page("/to-redirect", canonical=f"{SITE}/moved"),
        page("/moved", final_url=f"{SITE}/new"),
        page("/to-unknown", canonical=f"{SITE}/never-crawled"),
        page("/to-ok", canonical=f"{SITE}/ok"),
        page("/ok"),
        page("/self"),
    ]
    hits = flagged(canonicals.ToNon200(), pages)
    assert set(hits) == {"/to-404", "/to-redirect"}
    assert hits["/to-404"].message == f"{SITE}/gone returns 404"
    assert hits["/to-redirect"].message == f"{SITE}/moved redirects to {SITE}/new"


def test_off_site_and_not_self_and_linked() -> None:
    home = page("/", links=links("/linked", "/unlinked-ok"))
    pages = [
        home,
        page("/linked", canonical=f"{SITE}/other"),
        page("/orphaned", canonical=f"{SITE}/other"),
        page("/off", canonical="https://other.test/x"),
        page("/header-wins", canonical=f"{SITE}/header-wins", canonical_header=f"{SITE}/h"),
        page("/unlinked-ok"),
    ]
    assert set(flagged(canonicals.OffSite(), pages)) == {"/off"}
    assert set(flagged(canonicals.NotSelfReferencing(), pages)) == {
        "/linked",
        "/orphaned",
        "/off",
        "/header-wins",
    }
    linked = flagged(canonicals.CanonicalisedButLinked(), pages)
    assert set(linked) == {"/linked"}
    assert linked["/linked"].message == f"canonical {SITE}/other; linked from {SITE}/"


def test_chain() -> None:
    pages = [
        page("/a", canonical=f"{SITE}/b"),
        page("/b", canonical=f"{SITE}/c"),
        page("/c"),
        page("/d", canonical=f"{SITE}/not-crawled"),
        page("/e", canonical=f"{SITE}/c"),
    ]
    hits = flagged(canonicals.Chain(), pages)
    assert set(hits) == {"/a"}
    assert hits["/a"].message == f"{SITE}/b canonicalises to {SITE}/c"


def test_og_url_and_conflict() -> None:
    pages = [
        page("/og-bad", og_url=f"{SITE}/og-bad-social"),
        page("/og-ok", og_url="https://www.site.test/og-ok/"),
        page("/no-og"),
        page("/conflict", canonical=f"{SITE}/conflict", canonical_header=f"{SITE}/elsewhere"),
        page("/agree", canonical=f"{SITE}/agree", canonical_header=f"{SITE}/agree/"),
        page("/header-only", canonical="", canonical_header=f"{SITE}/x"),
    ]
    assert set(flagged(canonicals.OgUrlMismatch(), pages)) == {"/og-bad"}
    hits = flagged(canonicals.Conflict(), pages)
    assert set(hits) == {"/conflict"}
    assert hits["/conflict"].message == f"html {SITE}/conflict vs header {SITE}/elsewhere"
