from sitecrawler.crawl.frontier import Frontier


def test_accepts_in_scope_once() -> None:
    f = Frontier("example.com")
    assert f.add("https://www.example.com/a/", 0, "start")
    assert not f.add("https://example.com/a", 1, "x")  # duplicate after normalisation
    assert not f.add("https://example.com/a#x", 1, "x")
    assert len(f) == 1
    assert f.seen_count == 1


def test_rejects_out_of_scope() -> None:
    f = Frontier("example.com")
    assert not f.add("https://other.com/", 0, "s")
    assert not f.add("https://example.com/x.pdf", 0, "s")
    assert not f.add("mailto:a@example.com", 0, "s")
    assert len(f) == 0


def test_fifo_order_and_metadata() -> None:
    f = Frontier("example.com")
    f.add("https://example.com/first", 0, "start")
    f.add("https://example.com/second", 1, "https://example.com/first")
    first = f.pop()
    second = f.pop()
    assert first is not None
    assert first.url == "https://example.com/first"
    assert second is not None
    assert second.depth == 1
    assert second.found_on == "https://example.com/first"
    assert f.pop() is None


def test_scheme_is_forced_to_site_scheme() -> None:
    f = Frontier("localhost:8000", scheme="http")
    f.add("https://localhost:8000/x", 0, "s")
    item = f.pop()
    assert item is not None
    assert item.url == "http://localhost:8000/x"


def test_add_returns_the_queued_item() -> None:
    f = Frontier("example.com")
    item = f.add("https://example.com/x", 2, "https://example.com/")
    assert item is not None
    assert item.url == "https://example.com/x"
    assert item.depth == 2


def test_mark_seen_and_restore_for_resume() -> None:
    from sitecrawler.models import QueueItem

    f = Frontier("example.com")
    f.mark_seen(["https://example.com/done"])
    f.restore(QueueItem("https://example.com/pending", 1, "https://example.com/done"))
    assert f.add("https://example.com/done", 0, "s") is None
    assert f.add("https://example.com/pending", 0, "s") is None
    assert len(f) == 1
    assert f.seen_count == 2
