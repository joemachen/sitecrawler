"""Local web UI: a FastAPI app over one crawl session, opened by ``sitecrawler serve``."""

from sitecrawler.web.app import create_app
from sitecrawler.web.rows import RowStore, Summary
from sitecrawler.web.tabs import TABS, FilterSpec, TabSpec

__all__ = ["TABS", "FilterSpec", "RowStore", "Summary", "TabSpec", "create_app"]
