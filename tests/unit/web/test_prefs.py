"""The settings file the desktop app remembers its crawl folder in."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from sitecrawler.web.prefs import Prefs, default_prefs_file, load_prefs, save_prefs


def test_missing_file_means_defaults(tmp_path: Path) -> None:
    assert load_prefs(tmp_path / "settings.json") == Prefs()


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "settings.json"
    save_prefs(path, Prefs(crawls_dir=tmp_path / "crawls"))
    assert load_prefs(path) == Prefs(crawls_dir=tmp_path / "crawls")
    assert not path.with_name("settings.json.tmp").exists()


@pytest.mark.parametrize(
    "text", ["{not json", "[1, 2]", '{"crawls_dir": 5}', '{"crawls_dir": ""}', ""]
)
def test_unreadable_or_odd_files_mean_defaults(tmp_path: Path, text: str) -> None:
    path = tmp_path / "settings.json"
    path.write_text(text, encoding="utf-8")
    assert load_prefs(path) == Prefs()


def test_saving_keeps_keys_from_other_versions(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"theme": "dark", "crawls_dir": "old"}), encoding="utf-8")
    save_prefs(path, Prefs(crawls_dir=tmp_path / "new"))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"theme": "dark", "crawls_dir": str(tmp_path / "new")}


def test_settings_live_in_appdata_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert default_prefs_file() == tmp_path / "sitecrawler" / "settings.json"


def test_settings_live_in_the_xdg_config_folder_elsewhere(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert default_prefs_file() == tmp_path / "sitecrawler" / "settings.json"
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert default_prefs_file() == Path.home() / ".config" / "sitecrawler" / "settings.json"
