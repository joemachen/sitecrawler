"""The start request maps onto a CrawlConfig."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from sitecrawler.models import CrawlConfig
from sitecrawler.web.app import StartRequest


def test_defaults_match_the_crawl_config_defaults() -> None:
    config = StartRequest(url=" https://example.com ").to_config()
    default = CrawlConfig(start_url="https://example.com")
    assert config == default


def test_options_are_passed_through() -> None:
    config = StartRequest(
        url="https://example.com",
        max_pages=10,
        delay_seconds=1.5,
        workers=2,
        timeout_seconds=5,
        use_sitemap=False,
        keep_query=True,
        respect_robots=False,
        render=True,
    ).to_config()
    assert (config.max_pages, config.delay_seconds, config.workers) == (10, 1.5, 2)
    assert config.timeout_seconds == 5
    assert (config.use_sitemap, config.keep_query, config.respect_robots) == (False, True, False)
    assert config.render is True
    assert StartRequest(url="https://example.com").to_config().render is False


def test_out_of_range_options_are_rejected() -> None:
    with pytest.raises(ValidationError):
        StartRequest(url="https://example.com", workers=0)
    with pytest.raises(ValidationError):
        StartRequest(url="https://example.com", delay_seconds=-1)
