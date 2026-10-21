"""Per-host throttle timing."""

from __future__ import annotations

import asyncio
import itertools
import time

from sitecrawler.crawl.throttle import HostThrottle


async def test_same_host_waits_for_the_delay() -> None:
    throttle = HostThrottle(0.05)
    started = time.monotonic()
    await throttle.acquire("a.test")
    await throttle.acquire("a.test")
    # Windows timers are ~15 ms coarse, so leave slack below the nominal delay.
    assert time.monotonic() - started >= 0.04


async def test_different_hosts_do_not_wait_for_each_other() -> None:
    throttle = HostThrottle(0.2)
    started = time.monotonic()
    await throttle.acquire("a.test")
    await throttle.acquire("b.test")
    assert time.monotonic() - started < 0.1


async def test_zero_delay_never_sleeps() -> None:
    throttle = HostThrottle(0)
    started = time.monotonic()
    for _ in range(50):
        await throttle.acquire("a.test")
    assert time.monotonic() - started < 0.1


async def test_concurrent_callers_are_spaced_out() -> None:
    throttle = HostThrottle(0.03)
    stamps: list[float] = []

    async def hit() -> None:
        await throttle.acquire("a.test")
        stamps.append(time.monotonic())

    await asyncio.gather(hit(), hit(), hit())
    stamps.sort()
    gaps = [b - a for a, b in itertools.pairwise(stamps)]
    assert all(gap >= 0.02 for gap in gaps)
