"""Shared pytest configuration.

GUI/render tests need a display and OpenGL. They run by default on macOS/Windows
desktops; set EVE_SKIP_GUI_TESTS=1 (e.g. on headless CI) to skip them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))


def _gui_available() -> bool:
    if os.environ.get("EVE_SKIP_GUI_TESTS"):
        return False
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _gui_available():
        return
    skip = pytest.mark.skip(reason="no display / EVE_SKIP_GUI_TESTS set")
    for item in items:
        if "gui" in item.keywords or "render" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def eve_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("EVE_HOME", str(tmp_path / "evehome"))
    return tmp_path / "evehome"
