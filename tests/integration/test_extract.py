"""Custom extraction and search over the fixture site's product pages.

The three product pages carry a price in ``.price``, a SKU in a ``data-sku``
attribute and, on two of them, a Google Analytics tag; the third is the page
``--search`` must list as missing it. The browser-marked test at the end
checks that extraction reads the rendered DOM under ``--render``.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from sitecrawler.cli.main import app
from sitecrawler.crawl import Crawler
from sitecrawler.models import CrawlConfig, ExtractorSpec, PageRecord, SearchSpec
from sitecrawler.parse import parse_extractor, parse_search
from sitecrawler.store import open_store
from sitecrawler.web import create_app
from tests.integration.test_web_live import settled, start, wait

PRICE = "price=css:.price"
SKU = "sku=xpath://*[@data-sku]/@data-sku"
GA = r"ga=regex:gtag\('config',\s*'(G-[A-Z0-9]+)'\)"
SEARCH = "gtag=G-[A-Z0-9]{6,}"
GA_ID = "G-7F3K9Q2M1X"
PRODUCTS = {"/products/widget", "/products/gadget", "/products/gizmo"}


def _config(site: str, **options: object) -> CrawlConfig:
    return CrawlConfig(
        start_url=site,
        delay_seconds=0,
        workers=1,
        extract=tuple(parse_extractor(s) for s in (PRICE, SKU, GA)),
        search=(parse_search(SEARCH),),
        **options,  # type: ignore[arg-type]
    )


@pytest.fixture
def crawled(site: str) -> dict[str, PageRecord]:
    records = Crawler(_config(site)).run()
    return {r.url.removeprefix(site): r for r in records}


def _cells(record: PageRecord) -> dict[str, object]:
    return {e.name: (e.matched if e.kind == "search" else e.value) for e in record.extractions}


def test_price_sku_and_ga_tag_come_off_the_product_pages(
    crawled: dict[str, PageRecord],
) -> None:
    assert _cells(crawled["/products/widget"]) == {
        "price": "$19.99",
        "sku": "WID-001",
        "ga": GA_ID,
        "gtag": True,
    }
    assert _cells(crawled["/products/gadget"]) == {
        "price": "$49.00",
        "sku": "GAD-002",
        "ga": GA_ID,
        "gtag": True,
    }
    assert _cells(crawled["/products/gizmo"]) == {
        "price": "$5.50",
        "sku": "GIZ-003",
        "ga": "",
        "gtag": False,
    }
    gizmo = {e.name: e.count for e in crawled["/products/gizmo"].extractions}
    assert gizmo == {"price": 1, "sku": 1, "ga": 0, "gtag": 0}
    assert [e.name for e in crawled["/"].extractions] == ["price", "sku", "ga", "gtag"]


def test_search_lists_the_pages_missing_the_ga_tag(crawled: dict[str, PageRecord]) -> None:
    checked = {path: _cells(r)["gtag"] for path, r in crawled.items() if r.extractions}
    with_tag = {path for path, found in checked.items() if found}
    assert with_tag == {"/products/widget", "/products/gadget"}
    missing = {path for path, found in checked.items() if not found}
    assert "/products/gizmo" in missing
    assert "/" in missing
    assert len(missing) > 3, "every other HTML page lacks the tag too"


def test_pages_that_are_not_html_get_no_extractions(crawled: dict[str, PageRecord]) -> None:
    for path in ("/missing", "/blocked/secret", "/loop-a", "/audit/server-error"):
        assert crawled[path].extractions == (), path
    # a redirect source carries its target's content, and so its extractions
    assert [e.name for e in crawled["/redirect-start"].extractions] == [
        "price",
        "sku",
        "ga",
        "gtag",
    ]


def test_bad_extractor_fails_before_the_first_request() -> None:
    broken = ExtractorSpec("p", "css", "p[")  # built by hand: parse_extractor would refuse it
    with pytest.raises(ValueError, match="invalid CSS selector"):
        Crawler(CrawlConfig(start_url="https://x.test/", extract=(broken,)))
    with pytest.raises(ValueError, match="used by more than one"):
        Crawler(
            CrawlConfig(
                start_url="https://x.test/",
                extract=(ExtractorSpec("x", "css", "p"),),
                search=(SearchSpec("x", "p"),),
            )
        )


# --------------------------------------------------------------------- CLI
def test_cli_extracts_stores_and_exports(site: str, tmp_path: Path) -> None:
    db = tmp_path / "crawl.db"
    runner = CliRunner()
    crawl = runner.invoke(
        app,
        [
            "crawl",
            site,
            "--db",
            str(db),
            "--delay",
            "0",
            "--workers",
            "1",
            "--extract",
            PRICE,
            "--extract",
            SKU,
            "--extract",
            GA,
            "--search",
            SEARCH,
        ],
    )
    assert crawl.exit_code == 0, crawl.output
    flat = " ".join(crawl.output.split())
    assert "search gtag: 2 of" in flat
    assert "HTML pages contain it" in flat

    with open_store(db) as store:
        assert store.extraction_columns() == [
            "extract_price",
            "extract_sku",
            "extract_ga",
            "search_gtag",
        ]
        widget = next(r for r in store.iter_pages() if r.url.endswith("/products/widget"))
        assert _cells(widget) == {"price": "$19.99", "sku": "WID-001", "ga": GA_ID, "gtag": True}
        config = json.loads(store.crawl().config_json)
        assert config["extract"][0] == {
            "name": "price",
            "kind": "css",
            "expr": ".price",
            "mode": "text",
            "attr": "",
            "all": False,
        }
        assert config["search"] == [{"name": "gtag", "pattern": "G-[A-Z0-9]{6,}"}]

    out = tmp_path / "pages.csv"
    export = runner.invoke(app, ["export", str(db), "-o", str(out)])
    assert export.exit_code == 0, export.output
    with out.open(newline="", encoding="utf-8") as handle:
        rows = {row["url"].removeprefix(site): row for row in csv.DictReader(handle)}
    assert list(rows["/"].keys())[-4:] == [
        "extract_price",
        "extract_sku",
        "extract_ga",
        "search_gtag",
    ]
    assert rows["/products/gadget"]["extract_price"] == "$49.00"
    assert rows["/products/gadget"]["search_gtag"] == "True"
    assert rows["/products/gizmo"]["search_gtag"] == "False"
    assert rows["/missing"]["search_gtag"] == ""

    out_json = tmp_path / "pages.json"
    export = runner.invoke(app, ["export", str(db), "--format", "json", "-o", str(out_json)])
    assert export.exit_code == 0, export.output
    data = json.loads(out_json.read_text(encoding="utf-8"))
    gizmo = next(p for p in data["pages"] if p["url"].endswith("/products/gizmo"))
    assert (gizmo["extract_sku"], gizmo["extract_ga"], gizmo["search_gtag"]) == (
        "GIZ-003",
        "",
        False,
    )
    missing = next(p for p in data["pages"] if p["url"].endswith("/missing"))
    assert missing["search_gtag"] is None
    found = [e for e in data["extractions"] if e["url"].endswith("/products/widget")]
    assert found == [
        {
            "url": f"{site}/products/widget",
            "name": "price",
            "kind": "css",
            "count": 1,
            "value": "$19.99",
        },
        {
            "url": f"{site}/products/widget",
            "name": "sku",
            "kind": "xpath",
            "count": 1,
            "value": "WID-001",
        },
        {
            "url": f"{site}/products/widget",
            "name": "ga",
            "kind": "regex",
            "count": 1,
            "value": GA_ID,
        },
        {
            "url": f"{site}/products/widget",
            "name": "gtag",
            "kind": "search",
            "count": 2,
            "value": GA_ID,
        },
    ]


def test_cli_reads_extractors_from_a_toml_file_and_writes_the_csv(
    site: str, tmp_path: Path
) -> None:
    toml = tmp_path / "extract.toml"
    toml.write_text(
        "[extract.price]\ncss = '.price'\n"
        "[extract]\nsku = 'xpath://*[@data-sku]/@data-sku'\n"
        "[search]\ngtag = 'G-[A-Z0-9]{6,}'\n",
        encoding="utf-8",
    )
    out = tmp_path / "pages.csv"
    result = CliRunner().invoke(
        app,
        [
            "crawl",
            site,
            "-o",
            str(out),
            "--delay",
            "0",
            "--workers",
            "1",
            "--extract-file",
            str(toml),
            "--extract",
            "h1=css:h1",
        ],
    )
    assert result.exit_code == 0, result.output
    with out.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = {row["url"].removeprefix(site): row for row in reader}
        assert reader.fieldnames is not None
        assert reader.fieldnames[-4:] == [
            "extract_price",
            "extract_sku",
            "extract_h1",
            "search_gtag",
        ]
    assert rows["/products/widget"]["extract_h1"] == "Widget"
    assert rows["/products/widget"]["search_gtag"] == "True"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--extract", "css:.price"], "expected NAME=KIND:EXPRESSION"),
        (["--extract", "p=css:p["], "invalid CSS selector"),
        (["--search", "("], "invalid regular expression"),
        (["--extract", "x=css:p", "--search", "x=p"], "used by more than one"),
        (["--extract-file", "nope.toml"], "is not a file"),
    ],
)
def test_cli_rejects_bad_extractors_before_crawling(args: list[str], message: str) -> None:
    result = CliRunner().invoke(app, ["crawl", "https://example.test/", *args])
    assert result.exit_code == 2
    assert message in " ".join(result.output.split())


def test_list_mode_extracts_too(site: str, tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text(f"{site}/products/gizmo\n", encoding="utf-8")
    out = tmp_path / "pages.csv"
    result = CliRunner().invoke(
        app, ["list", str(urls), "-o", str(out), "--delay", "0", "--extract", PRICE]
    )
    assert result.exit_code == 0, result.output
    with out.open(newline="", encoding="utf-8") as handle:
        (row,) = list(csv.DictReader(handle))
    assert row["extract_price"] == "$5.50"


# --------------------------------------------------------------------- web
@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(crawls_dir=tmp_path / "crawls")) as c:
        yield c


def test_web_custom_tab_shows_the_columns_and_filters(client: TestClient, site: str) -> None:
    before = next(t for t in client.get("/api/tabs").json() if t["id"] == "custom")
    assert before["columns"] == ["url", "status_code", "indexable"]

    start(client, site, extract=[PRICE, SKU, GA], search=[SEARCH])
    crawl = wait(client, settled)
    assert crawl["status"] == "done", crawl

    custom = next(t for t in client.get("/api/tabs").json() if t["id"] == "custom")
    assert custom["columns"] == [
        "url",
        "extract_price",
        "extract_sku",
        "extract_ga",
        "search_gtag",
        "status_code",
        "indexable",
    ]
    assert custom["titles"] == {
        "extract_price": "price",
        "extract_sku": "sku",
        "extract_ga": "ga",
        "search_gtag": "gtag",
    }
    assert [f["id"] for f in custom["filters"]] == [
        "all",
        "has:price",
        "not:price",
        "has:sku",
        "not:sku",
        "has:ga",
        "not:ga",
        "has:gtag",
        "not:gtag",
    ]

    rows = {r["url"].removeprefix(site): r for r in client.get("/api/rows").json()["rows"]}
    widget = rows["/products/widget"]
    assert (widget["extract_price"], widget["extract_sku"], widget["extract_ga"]) == (
        "$19.99",
        "WID-001",
        GA_ID,
    )
    assert (widget["search_gtag"], widget["search_gtag_n"]) == (True, 2)
    assert rows["/products/gizmo"]["search_gtag"] is False
    assert "search_gtag" not in rows["/missing"]

    counts = client.get("/api/summary").json()["tabs"]["custom"]
    assert counts["has:gtag"] == 2
    assert counts["not:gtag"] == counts["has:price"] + counts["not:price"] - 2
    assert counts["has:price"] == 3
    assert counts["has:ga"] == 2

    html = client.get("/").text
    assert '"extract_price"' in html, "the shell renders the crawl's specs"
    pane = client.get("/detail/custom", params={"url": f"{site}/products/gizmo"}).text
    assert 'data-name="price"' in pane
    assert "$5.50" in pane
    assert "does not contain" in pane
    none = client.get("/detail/custom", params={"url": f"{site}/missing"}).text
    assert 'data-custom="none"' in none


def test_web_rejects_a_bad_extractor_with_400(client: TestClient, site: str) -> None:
    response = client.post(
        "/api/crawl/start", json={"url": site, "extract": ["p=css:p["], "search": []}
    )
    assert response.status_code == 400
    assert "invalid CSS selector" in response.json()["detail"]
    assert client.get("/api/crawl").json()["status"] == "idle"


def test_web_opens_a_stored_crawl_with_its_custom_columns(site: str, tmp_path: Path) -> None:
    db = tmp_path / "crawl.db"
    with open_store(db) as store:
        Crawler(_config(site), sink=store).run()
    with TestClient(create_app(db)) as client:
        custom = next(t for t in client.get("/api/tabs").json() if t["id"] == "custom")
        assert custom["columns"][1:5] == [
            "extract_price",
            "extract_sku",
            "extract_ga",
            "search_gtag",
        ]
        rows = {r["url"].removeprefix(site): r for r in client.get("/api/rows").json()["rows"]}
        assert rows["/products/gadget"]["extract_sku"] == "GAD-002"
        assert client.get("/api/summary").json()["tabs"]["custom"]["not:gtag"] >= 1


# ------------------------------------------------------------------ render
@pytest.mark.browser
def test_extraction_reads_the_rendered_dom_under_render(site: str) -> None:
    config = CrawlConfig(
        seed_urls=(f"{site}/js-injected",),
        follow_links=False,
        delay_seconds=0,
        render=True,
        render_timeout_seconds=15,
        extract=(
            parse_extractor("title=css:title"),
            parse_extractor('canonical=xpath://link[@rel="canonical"]/@href'),
            parse_extractor("nav=css[attr=href,all]:#nav a"),
        ),
        # the raw HTML has the rendered title inside its script; only the DOM has the <link> tag
        search=(parse_search('rendered=<link rel="canonical"'),),
    )
    (page,) = Crawler(config).run()
    assert page.render is not None, page.render_error
    assert _cells(page) == {
        "title": "Rendered title set by JavaScript on load",
        "canonical": "/js-injected",  # attributes come back as written, not resolved
        "nav": "/about | /blog/ | /audit/",
        "rendered": True,
    }
    (raw,) = Crawler(
        CrawlConfig(
            seed_urls=(f"{site}/js-injected",),
            follow_links=False,
            delay_seconds=0,
            extract=config.extract,
            search=config.search,
        )
    ).run()
    assert _cells(raw) == {
        "title": "Raw title before JavaScript runs on this page",
        "canonical": "",
        "nav": "",
        "rendered": False,
    }
