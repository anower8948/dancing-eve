"""What the current desktop environment can actually do for a floating companion window.

Transparency, always-on-top, click-through, tray icons and free window positioning differ
between macOS, Windows, X11 and Wayland. The UI reads these flags to hide or explain
features instead of pretending they work.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DesktopCapabilities:
    platform: str  # "macos" | "windows" | "linux" | other
    session: str  # Linux: "wayland" | "x11" | ""
    qt_platform: str  # Qt platform plugin in use ("cocoa", "windows", "xcb", "wayland"...)
    translucency: bool
    always_on_top: bool
    click_through: bool
    system_tray: bool
    window_positioning: bool
    notes: list[str] = field(default_factory=list)


def preferred_qt_platform(env: dict[str, str] | None = None) -> str | None:
    """On a Wayland session with XWayland available, prefer xcb: Wayland forbids
    always-on-top and window positioning for normal clients, and Panda3D's offscreen GL
    pipe needs an X display. Returns the value for QT_QPA_PLATFORM, or None to keep Qt's
    default. Users can override with QT_QPA_PLATFORM themselves."""
    env = dict(os.environ) if env is None else env
    if not sys.platform.startswith("linux") or env.get("QT_QPA_PLATFORM"):
        return None
    wayland = env.get("XDG_SESSION_TYPE", "").lower() == "wayland" or bool(env.get("WAYLAND_DISPLAY"))
    if wayland and env.get("DISPLAY"):
        return "xcb"
    return None


def detect_capabilities(qt_platform: str, tray_available: bool) -> DesktopCapabilities:
    notes: list[str] = []
    if sys.platform == "darwin":
        return DesktopCapabilities("macos", "", qt_platform, True, True, True, tray_available, True, notes)
    if sys.platform.startswith("win"):
        return DesktopCapabilities("windows", "", qt_platform, True, True, True, tray_available, True, notes)
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if qt_platform == "wayland":
        notes.append(
            "Native Wayland: always-on-top, click-through and window positioning are controlled "
            "by the compositor and are unavailable."
        )
        caps = DesktopCapabilities("linux", "wayland", qt_platform, True, False, False, tray_available, False, notes)
    else:
        if session == "wayland":
            notes.append(
                "Running through XWayland so always-on-top and positioning work; "
                "some compositors may still restrict them."
            )
        notes.append("Transparency on X11 needs a compositing window manager (default on GNOME and KDE).")
        caps = DesktopCapabilities(
            "linux", session or "x11", qt_platform, True, True, True, tray_available, True, notes
        )
    if not tray_available:
        caps.notes.append("No system tray detected (on GNOME, the AppIndicator extension provides one).")
    return caps
