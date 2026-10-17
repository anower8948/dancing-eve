"""Per-user storage locations.

Standard-library only on purpose: the first-time setup code (``setup/``) imports this
module before any third-party package is installed, so both agree on where logs live.

Locations (``APP_DIR_NAME`` = "ProjectEVE"):

========  ===============================================  ==========================================
OS        Settings / data                                  Logs
========  ===============================================  ==========================================
macOS     ~/Library/Application Support/ProjectEVE         ~/Library/Logs/ProjectEVE
Windows   %APPDATA%\\ProjectEVE                             %LOCALAPPDATA%\\ProjectEVE\\Logs
Linux     $XDG_CONFIG_HOME/ProjectEVE (~/.config/...)      $XDG_STATE_HOME/ProjectEVE/log
========  ===============================================  ==========================================

Set ``EVE_HOME`` to redirect everything into one folder (used by tests and portable runs).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "ProjectEVE"


@dataclass(frozen=True)
class AppPaths:
    config_dir: Path
    log_dir: Path
    cache_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def lock_file(self) -> Path:
        return self.config_dir / "eve.lock"

    def ensure(self) -> AppPaths:
        for path in (self.config_dir, self.log_dir, self.cache_dir):
            path.mkdir(parents=True, exist_ok=True)
        return self


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def resolve_paths(
    platform: str | None = None,
    env: dict[str, str] | None = None,
) -> AppPaths:
    """Return the storage paths for ``platform`` ("darwin", "win32", "linux"...)."""
    env = dict(os.environ) if env is None else env
    platform = platform or sys.platform

    override = env.get("EVE_HOME")
    if override:
        root = Path(override)
        return AppPaths(root / "config", root / "logs", root / "cache")

    if platform == "darwin":
        lib = _home() / "Library"
        return AppPaths(
            lib / "Application Support" / APP_DIR_NAME,
            lib / "Logs" / APP_DIR_NAME,
            lib / "Caches" / APP_DIR_NAME,
        )
    if platform.startswith("win"):
        roaming = Path(env.get("APPDATA") or (_home() / "AppData" / "Roaming"))
        local = Path(env.get("LOCALAPPDATA") or (_home() / "AppData" / "Local"))
        return AppPaths(
            roaming / APP_DIR_NAME,
            local / APP_DIR_NAME / "Logs",
            local / APP_DIR_NAME / "Cache",
        )
    # Linux and other POSIX systems: XDG base directories.
    config = Path(env.get("XDG_CONFIG_HOME") or (_home() / ".config"))
    state = Path(env.get("XDG_STATE_HOME") or (_home() / ".local" / "state"))
    cache = Path(env.get("XDG_CACHE_HOME") or (_home() / ".cache"))
    return AppPaths(config / APP_DIR_NAME, state / APP_DIR_NAME / "log", cache / APP_DIR_NAME)
