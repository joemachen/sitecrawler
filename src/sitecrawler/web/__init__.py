"""Local web UI: a FastAPI app over one stored crawl, opened by ``sitecrawler serve``."""

from sitecrawler.web.app import create_app
from sitecrawler.web.data import CrawlSnapshot, Overview, load_snapshot, to_rows

__all__ = ["CrawlSnapshot", "Overview", "create_app", "load_snapshot", "to_rows"]
