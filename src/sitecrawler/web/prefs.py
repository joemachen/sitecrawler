"""Settings the desktop app remembers between launches, in one small JSON file."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Prefs:
    """What the user chose last time; None means "use the default"."""

    crawls_dir: Path | None = None
    """Where new crawls are written, as last chosen in Settings."""


def default_prefs_file() -> Path:
    r"""``%APPDATA%\sitecrawler\settings.json`` on Windows, the XDG config folder elsewhere.

    Outside the exe's folder on purpose, so the choice survives moving,
    copying or rebuilding the exe.
    """
    if sys.platform == "win32" and (appdata := os.environ.get("APPDATA")):
        return Path(appdata) / "sitecrawler" / "settings.json"
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "sitecrawler" / "settings.json"


def _read(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("ignoring unreadable settings file %s: %s", path, exc)
        return {}
    return raw if isinstance(raw, dict) else {}


def load_prefs(path: Path) -> Prefs:
    """The prefs saved at ``path``; defaults when it is missing or unreadable."""
    crawls_dir = _read(path).get("crawls_dir")
    return Prefs(
        crawls_dir=Path(crawls_dir) if isinstance(crawls_dir, str) and crawls_dir else None
    )


def save_prefs(path: Path, prefs: Prefs) -> None:
    """Write ``prefs`` to ``path``, keeping any keys this version does not know.

    Raises:
        OSError: the file or its folder could not be written.
    """
    data = _read(path)
    data["crawls_dir"] = str(prefs.crawls_dir) if prefs.crawls_dir else None
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".tmp")
    partial.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    partial.replace(path)  # a crash mid-write never leaves half a file
