"""CrawlControl flags."""

from __future__ import annotations

from sitecrawler.crawl import CrawlControl


def flags(control: CrawlControl) -> tuple[bool, bool]:
    """``(paused, stopping)``; read through a call so no type narrowing applies."""
    return control.paused, control.stopping


def test_nothing_requested_by_default() -> None:
    assert flags(CrawlControl()) == (False, False)


def test_pause_and_resume_toggle() -> None:
    control = CrawlControl()
    control.pause()
    assert flags(control) == (True, False)
    control.pause()
    assert flags(control) == (True, False)
    control.resume()
    assert flags(control) == (False, False)
    control.resume()
    assert flags(control) == (False, False)


def test_stop_is_sticky_and_lifts_a_pause() -> None:
    control = CrawlControl()
    control.pause()
    control.stop()
    assert flags(control) == (False, True)
    control.resume()
    assert flags(control) == (False, True)
