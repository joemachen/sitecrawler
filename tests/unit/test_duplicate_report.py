from sitecrawler.analysis import duplicate_report, member_status
from sitecrawler.audit.duplicates import MIN_WORDS, NEAR_DUPLICATE_DISTANCE
from sitecrawler.parse import fingerprint_text
from tests.unit.audit.helpers import SITE, long_text, page, view

LONG = long_text(MIN_WORDS + 20)
LONG_NEAR = LONG.replace("word100 word101", "changed words")
OTHER = long_text(MIN_WORDS + 20, prefix="other")
SHORT = "a short page"


def _site() -> list:  # type: ignore[type-arg]
    return [
        page("/", fingerprint=fingerprint_text(OTHER)),
        page("/a", fingerprint=fingerprint_text(LONG)),
        page("/b", fingerprint=fingerprint_text(LONG)),
        page("/c", fingerprint=fingerprint_text(LONG_NEAR), canonical=f"{SITE}/a"),
        page("/s1", fingerprint=fingerprint_text(SHORT)),
        page("/s2", fingerprint=fingerprint_text(SHORT), meta_robots="noindex"),
        page("/twin1", fingerprint=fingerprint_text(OTHER + " twin")),
        page("/twin2", fingerprint=fingerprint_text(OTHER + " twin")),
        page("/gone", 404),
    ]


def test_report_counts_groups_clusters_and_low_content() -> None:
    report = duplicate_report(view(_site()))
    assert report.pages == 8
    assert report.compared == 6
    assert [c.urls for c in report.exact] == [
        (f"{SITE}/a", f"{SITE}/b"),
        (f"{SITE}/s1", f"{SITE}/s2"),
        (f"{SITE}/twin1", f"{SITE}/twin2"),
    ]
    # /twin1 and /twin2 are within 10 bits of / (one extra word): one near cluster
    # with two distinct texts; /a, /b, /c form the other
    assert [c.urls for c in report.near] == [
        (f"{SITE}/", f"{SITE}/twin1", f"{SITE}/twin2"),
        (f"{SITE}/a", f"{SITE}/b", f"{SITE}/c"),
    ]
    assert report.low_content == 1  # /s1; /s2 is noindex
    assert report.max_distance == NEAR_DUPLICATE_DISTANCE
    assert report.min_words == MIN_WORDS
    assert report.summary() == (
        "Duplicates: 8 pages fingerprinted; 6 in 3 group(s) of identical content; "
        f"6 in 2 near-duplicate cluster(s) within {NEAR_DUPLICATE_DISTANCE} of 64 bits "
        f"among the 6 pages of {MIN_WORDS}+ words; 1 indexable page(s) under {MIN_WORDS} words."
    )


def test_report_with_another_distance_and_exact_only_clusters() -> None:
    crawl = view(_site())
    strict = duplicate_report(crawl, max_distance=0)
    assert strict.max_distance == 0
    assert strict.near == ()  # /a and /b alone would be a cluster of one text: not near
    assert strict.exact == duplicate_report(crawl).exact
    assert duplicate_report(crawl, NEAR_DUPLICATE_DISTANCE).near == duplicate_report(crawl).near
    assert duplicate_report(view([])).summary().startswith("Duplicates: 0 pages fingerprinted")


def test_member_status() -> None:
    crawl = view(_site())
    assert member_status(crawl, crawl.pages[1]) == "indexable"
    assert member_status(crawl, crawl.page_for(f"{SITE}/c")) == f"canonicalised to {SITE}/a"  # type: ignore[arg-type]
    assert member_status(crawl, crawl.page_for(f"{SITE}/gone")) == "status 404"  # type: ignore[arg-type]
