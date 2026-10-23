"""PyInstaller entry point for the standalone sitecrawler.exe (see sitecrawler.spec)."""

import sys

from sitecrawler.web.desktop import main

sys.exit(main())
