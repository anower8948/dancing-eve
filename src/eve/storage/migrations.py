"""Versioned settings migrations.

Each migration converts the raw dict of version N to version N+1. Add a new function and
register it in ``MIGRATIONS`` whenever ``SETTINGS_VERSION`` increases; never edit an old
migration once released.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from eve.config import SETTINGS_VERSION

Migration = Callable[[dict[str, Any]], dict[str, Any]]


def _v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """v0 = pre-release files without a version field (development builds).

    Renames ``volume_sensitivity`` -> ``sensitivity`` and ``size`` -> ``character_size``.
    """
    out = dict(data)
    if "volume_sensitivity" in out and "sensitivity" not in out:
        out["sensitivity"] = out.pop("volume_sensitivity")
    if "size" in out and "character_size" not in out:
        out["character_size"] = out.pop("size")
    out["version"] = 1
    return out


MIGRATIONS: dict[int, Migration] = {0: _v0_to_v1}


class MigrationError(Exception):
    pass


def migrate(data: dict[str, Any]) -> tuple[dict[str, Any], list[int]]:
    """Upgrade ``data`` to SETTINGS_VERSION. Returns (data, versions migrated from)."""
    version = data.get("version", 0)
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise MigrationError(f"invalid settings version {version!r}")
    if version > SETTINGS_VERSION:
        raise MigrationError(f"settings version {version} is newer than this app ({SETTINGS_VERSION})")
    applied = []
    while version < SETTINGS_VERSION:
        step = MIGRATIONS.get(version)
        if step is None:
            raise MigrationError(f"no migration from settings version {version}")
        data = step(data)
        applied.append(version)
        version = data["version"]
    return data, applied
