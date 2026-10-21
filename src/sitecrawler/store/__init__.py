"""SQLite persistence for crawls: one file per crawl."""

from sitecrawler.store.store import Store, open_store

__all__ = ["Store", "open_store"]
