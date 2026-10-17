"""Platform-specific capture backends, ordered by preference per OS."""

from __future__ import annotations

import sys

from eve.audio.capture_interface import AudioCaptureBackend


def default_backend_classes(platform: str | None = None) -> list[type[AudioCaptureBackend]]:
    """Backends to try on this OS, best first. Imports are lazy so missing native
    bindings for *other* platforms never break startup."""
    platform = platform or sys.platform
    if platform == "darwin":
        from eve.audio.platforms.macos_capture import ScreenCaptureKitBackend
        from eve.audio.platforms.virtual_device import VirtualDeviceBackend

        return [ScreenCaptureKitBackend, VirtualDeviceBackend]
    if platform.startswith("win"):
        from eve.audio.platforms.windows_capture import WasapiLoopbackBackend

        return [WasapiLoopbackBackend]
    if platform.startswith("linux"):
        from eve.audio.platforms.linux_capture import PulseMonitorBackend

        return [PulseMonitorBackend]
    return []
