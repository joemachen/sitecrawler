"""Issues, rules, redirects and page detail over the stored fixture crawl."""

from __future__ import annotations

import html as html_mod
import re
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from sitecrawler.audit import load_rules
from sitecrawler.web import create_app
from tests.integration.test_audit import TRIGGERS


@pytest.fixture
def client(audited_db: Path) -> Iterator[TestClient]:
    with TestClient(create_app(audited_db)) as c:
        yield c


def test_issues_tab_lists_every_rule_that_fired_with_a_rule_link(client: TestClient) -> None:
    html = client.get("/issues").text
    fired = {rule for rule, paths in TRIGGERS.items() if paths}
    assert set(re.findall(r'data-rule="([^"]+)"', html)) == fired
    for rule in fired:
        assert f'href="/rules/{rule}"' in html
        assert f'hx-get="/issues/{rule}"' in html
    # most severe first, as the audit command prints them
    order = re.findall(r'class="sev sev-(\w+)"', html)
    ranks = ["critical", "high", "medium", "low", "info"]
    assert [ranks.index(s) for s in order] == sorted(ranks.index(s) for s in order)


@pytest.mark.parametrize("rule", sorted(TRIGGERS))
def test_issue_urls_fragment_matches_the_triggers_table(
    client: TestClient, site: str, rule: str
) -> None:
    response = client.get(f"/issues/{rule}")
    assert response.status_code == 200
    urls = set(re.findall(r'data-url="([^"]+)"', response.text))
    assert {u.removeprefix(site) or "/" for u in urls} == TRIGGERS[rule]


def test_api_issues_counts_match_the_triggers_table(client: TestClient) -> None:
    rows = client.get("/api/issues").json()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["rule_id"]] = counts.get(row["rule_id"], 0) + 1
    assert counts == {rule: len(paths) for rule, paths in TRIGGERS.items() if paths}


def test_every_rule_has_an_explanation_page(client: TestClient) -> None:
    for rule in load_rules():
        html = html_mod.unescape(client.get(f"/rules/{rule.id}").text)
        assert rule.summary in html
        assert rule.why.split(".")[0] in html
        assert rule.fix.split(".")[0] in html
    assert client.get("/rules/response.4xx").text.count('data-count="1"') == 1


def test_unknown_rule_and_page_render_the_404_page(client: TestClient) -> None:
    for path in ("/rules/nope", "/issues/nope", "/page?url=https://elsewhere.test/"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert "<h1>Not found</h1>" in response.text


def test_redirects_tab_and_its_json(client: TestClient, site: str) -> None:
    assert 'data-grid="/api/redirects"' in client.get("/redirects").text
    rows = client.get("/api/redirects").json()
    chain = [r for r in rows if r["url"] == f"{site}/redirect-start"]
    assert [r["hop_no"] for r in chain] == list(range(1, len(chain) + 1))
    assert all(r["status_code"] in (301, 302) for r in rows)


def test_page_detail_shows_verdict_issues_and_inlinks(client: TestClient, site: str) -> None:
    html = client.get("/page", params={"url": f"{site}/missing"}).text
    assert "non-indexable" in html
    assert "status 404" in html
    assert 'data-rule="response.4xx"' in html
    assert f'data-src="{site}/"' in html  # the home page links to /missing

    ok = client.get(f"/page?url={quote(site + '/blog/post-1', safe='')}").text
    assert "indexable" in ok
    assert "non-indexable" not in ok
    assert "<h2>Outlinks" in ok


def test_page_detail_accepts_any_url_form(client: TestClient, site: str) -> None:
    with_slash = client.get("/page", params={"url": f"{site}/blog/"})
    without = client.get("/page", params={"url": f"{site}/blog"})
    assert with_slash.status_code == without.status_code == 200
    assert f"{site}/blog" in with_slash.text
