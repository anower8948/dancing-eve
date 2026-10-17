"""macOS fallback: capture from a virtual loopback device such as BlackHole.

Only devices whose names identify them as loopback drivers are offered. Physical
microphones are never listed, so this can never silently become microphone capture.
The user must route system output into the virtual device (e.g. a Multi-Output Device in
Audio MIDI Setup) — see docs/audio-capture.md.
"""

from __future__ import annotations

import re
import sys
from typing import Any

from eve.audio.capture_interface import AudioSource, SourceKind
from eve.audio.platforms.soundcard_backend import SoundCardBackend

VIRTUAL_DEVICE_PATTERN = re.compile(
    r"blackhole|loopback audio|soundflower|background music|vb-cable|vb-audio|ishowu|eve loopback",
    re.IGNORECASE,
)


def is_virtual_loopback_name(name: str) -> bool:
    return bool(VIRTUAL_DEVICE_PATTERN.search(name))


class VirtualDeviceBackend(SoundCardBackend):
    key = "vdev"
    display_name = "Virtual loopback device (BlackHole etc.)"
    follows_default = False

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        if sys.platform != "darwin":
            return False, "virtual-device fallback is only used on macOS"
        return super().availability()

    def _devices(self, sc: Any) -> list[tuple[AudioSource, Any]]:
        result = []
        for mic in sc.all_microphones():
            name = str(mic.name)
            if not is_virtual_loopback_name(name):
                continue
            source = AudioSource(
                id=f"{self.key}:{name}",
                name=name,
                kind=SourceKind.VIRTUAL_DEVICE,
                is_default=False,
                description="Virtual loopback device (route system output into it)",
            )
            result.append((source, mic))
        return result
