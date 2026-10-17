"""User settings model with validation and sensible defaults.

Settings are plain data. Validation clamps out-of-range numbers and replaces values of
the wrong type with defaults, so a hand-edited or partially corrupted file never crashes
the app. Persistence lives in eve.storage.settings_store.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from typing import Any

SETTINGS_VERSION = 1

# (min, max) for numeric settings.
LIMITS: dict[str, tuple[float, float]] = {
    "sensitivity": (0.25, 3.0),
    "dance_intensity": (0.0, 1.5),
    "character_size": (140, 560),
    "target_fps": (15, 120),
}


@dataclass
class Settings:
    version: int = SETTINGS_VERSION
    listen_on_start: bool = True
    audio_source_id: str | None = None  # None = best default source
    sensitivity: float = 1.0
    dance_intensity: float = 1.0
    reduced_motion: bool = False
    character_size: int = 260  # window height in logical pixels
    always_on_top: bool = True
    click_through: bool = False
    power_saving: bool = False  # 30 FPS cap
    target_fps: int = 60
    show_tray_icon: bool = True
    show_shadow: bool = True
    debug_mode: bool = False
    window_x: int | None = None
    window_y: int | None = None
    window_screen: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def effective_fps(self) -> int:
        return min(30, self.target_fps) if self.power_saving else self.target_fps


_DEFAULTS = Settings()


def _coerce(name: str, value: Any, default: Any) -> Any:
    """Return ``value`` converted to the type of ``default`` (or the default if invalid)."""
    if name in ("audio_source_id", "window_screen"):
        return value if isinstance(value, str) and value else None
    if isinstance(value, float) and not math.isfinite(value):
        return None if name in ("window_x", "window_y") else default
    if name in ("window_x", "window_y"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return int(value)
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        value = int(round(value))
    elif isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        value = float(value)
    else:
        return value if isinstance(value, type(default)) else default
    if name in LIMITS:
        lo, hi = LIMITS[name]
        value = type(default)(min(hi, max(lo, value)))
    return value


def validate(data: dict[str, Any]) -> tuple[Settings, list[str]]:
    """Build Settings from a dict. Returns (settings, list of human-readable fixes)."""
    problems: list[str] = []
    values: dict[str, Any] = {}
    for f in fields(Settings):
        default = getattr(_DEFAULTS, f.name)
        if f.name not in data:
            values[f.name] = default
            continue
        raw = data[f.name]
        fixed = _coerce(f.name, raw, default)
        if fixed != raw:
            problems.append(f"{f.name}: {raw!r} -> {fixed!r}")
        values[f.name] = fixed
    unknown = set(data) - {f.name for f in fields(Settings)}
    for key in sorted(unknown):
        problems.append(f"ignored unknown setting {key!r}")
    values["version"] = SETTINGS_VERSION
    return Settings(**values), problems
