"""Operating-system detection for the first-time setup.

Standard library only. Must stay importable on any Python 3.8+ so the bootstrap can
explain problems even when it runs on an unsupported interpreter.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

MACOS = "macos"
WINDOWS = "windows"
LINUX = "linux"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlatformInfo:
    system: str  # one of MACOS / WINDOWS / LINUX / UNKNOWN
    release: str  # e.g. "15.1", "10.0.22631", "6.8.0-45-generic"
    machine: str  # e.g. "arm64", "AMD64", "x86_64"
    distro_id: str = ""  # Linux only, e.g. "ubuntu"
    distro_version: str = ""  # Linux only, e.g. "24.04"
    session_type: str = ""  # Linux only: "wayland", "x11", "tty" or ""
    python_version: Tuple[int, int, int] = (0, 0, 0)
    extra: Dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        if self.system == MACOS:
            return "macOS {} ({})".format(self.release, self.machine)
        if self.system == WINDOWS:
            return "Windows {} ({})".format(self.release, self.machine)
        if self.system == LINUX:
            distro = "{} {}".format(self.distro_id or "Linux", self.distro_version).strip()
            session = " / {}".format(self.session_type) if self.session_type else ""
            return "{} ({}{})".format(distro, self.machine, session)
        return "Unknown OS ({})".format(sys.platform)

    def macos_version(self) -> Tuple[int, ...]:
        return parse_version(self.release) if self.system == MACOS else ()


def parse_version(text: str) -> Tuple[int, ...]:
    parts = []
    for piece in text.split("."):
        digits = ""
        for ch in piece:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def parse_os_release(text: str) -> Dict[str, str]:
    """Parse /etc/os-release style KEY=value lines."""
    values: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def detect_session_type(env: Optional[Dict[str, str]] = None) -> str:
    env = dict(os.environ) if env is None else env
    session = env.get("XDG_SESSION_TYPE", "").lower()
    if session in ("wayland", "x11", "tty"):
        return session
    if env.get("WAYLAND_DISPLAY"):
        return "wayland"
    if env.get("DISPLAY"):
        return "x11"
    return ""


def detect_platform(
    sys_platform: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    os_release_text: Optional[str] = None,
) -> PlatformInfo:
    sys_platform = sys_platform or sys.platform
    py = tuple(sys.version_info[:3])
    machine = platform.machine() or "unknown"

    if sys_platform == "darwin":
        release = platform.mac_ver()[0] or platform.release()
        return PlatformInfo(MACOS, release, machine, python_version=py)  # type: ignore[arg-type]
    if sys_platform.startswith("win"):
        release = platform.version() or platform.release()
        return PlatformInfo(WINDOWS, release, machine, python_version=py)  # type: ignore[arg-type]
    if sys_platform.startswith("linux"):
        if os_release_text is None:
            os_release_text = ""
            for candidate in ("/etc/os-release", "/usr/lib/os-release"):
                try:
                    with open(candidate, encoding="utf-8") as handle:
                        os_release_text = handle.read()
                    break
                except OSError:
                    continue
        info = parse_os_release(os_release_text)
        return PlatformInfo(
            LINUX,
            platform.release(),
            machine,
            distro_id=info.get("ID", "").lower(),
            distro_version=info.get("VERSION_ID", ""),
            session_type=detect_session_type(env),
            python_version=py,  # type: ignore[arg-type]
        )
    return PlatformInfo(UNKNOWN, platform.release(), machine, python_version=py)  # type: ignore[arg-type]
