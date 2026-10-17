"""OS detection (setup), storage paths and desktop capability decisions."""

from __future__ import annotations

from pathlib import Path

from setup.platform_detector import (
    LINUX,
    MACOS,
    WINDOWS,
    detect_platform,
    detect_session_type,
    parse_os_release,
    parse_version,
)

from eve.desktop.platform_capabilities import preferred_qt_platform
from eve.storage.paths import resolve_paths

UBUNTU = 'NAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\n# comment\nPRETTY_NAME="Ubuntu 24.04.1 LTS"\n'


def test_parse_os_release() -> None:
    info = parse_os_release(UBUNTU)
    assert info["ID"] == "ubuntu" and info["VERSION_ID"] == "24.04"


def test_detect_linux_with_session() -> None:
    p = detect_platform("linux", env={"XDG_SESSION_TYPE": "wayland"}, os_release_text=UBUNTU)
    assert p.system == LINUX and p.distro_id == "ubuntu" and p.distro_version == "24.04"
    assert p.session_type == "wayland"
    assert "ubuntu 24.04" in p.label


def test_detect_macos_and_windows() -> None:
    assert detect_platform("darwin").system == MACOS
    assert detect_platform("win32").system == WINDOWS


def test_session_type_fallbacks() -> None:
    assert detect_session_type({"WAYLAND_DISPLAY": "wayland-0"}) == "wayland"
    assert detect_session_type({"DISPLAY": ":0"}) == "x11"
    assert detect_session_type({}) == ""


def test_parse_version() -> None:
    assert parse_version("14.2.1") == (14, 2, 1)
    assert parse_version("15.0beta") == (15, 0)
    assert parse_version("") == ()


def test_storage_paths_per_os(tmp_path: Path) -> None:
    mac = resolve_paths("darwin", env={})
    assert "Library/Application Support/ProjectEVE" in mac.config_dir.as_posix()
    assert "Library/Logs/ProjectEVE" in mac.log_dir.as_posix()
    win = resolve_paths(
        "win32", env={"APPDATA": "C:/Users/u/AppData/Roaming", "LOCALAPPDATA": "C:/Users/u/AppData/Local"}
    )
    assert win.config_dir.as_posix().endswith("Roaming/ProjectEVE")
    assert win.log_dir.as_posix().endswith("Local/ProjectEVE/Logs")
    linux = resolve_paths("linux", env={"XDG_CONFIG_HOME": "/x/config", "XDG_STATE_HOME": "/x/state"})
    assert linux.config_dir == Path("/x/config/ProjectEVE")
    assert linux.log_dir == Path("/x/state/ProjectEVE/log")
    override = resolve_paths("linux", env={"EVE_HOME": str(tmp_path)})
    assert override.settings_file == tmp_path / "config" / "settings.json"


def test_settings_never_inside_source_tree() -> None:
    project = Path(__file__).resolve().parents[2]
    paths = resolve_paths()
    for folder in (paths.config_dir, paths.log_dir):
        assert project not in folder.resolve().parents


def test_wayland_prefers_xwayland_when_available(monkeypatch) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    assert preferred_qt_platform({"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}) == "xcb"
    assert preferred_qt_platform({"XDG_SESSION_TYPE": "wayland"}) is None
    assert preferred_qt_platform({"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0", "QT_QPA_PLATFORM": "wayland"}) is None
    assert preferred_qt_platform({"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}) is None
