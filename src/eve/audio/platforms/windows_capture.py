"""Windows system-output capture through WASAPI loopback (via SoundCard).

Status: implemented, NOT yet verified on real Windows hardware (see
docs/cross-platform-support.md). Loopback captures the mix sent to an output endpoint;
it never opens a microphone.
"""

from __future__ import annotations

import sys
from typing import Any

from eve.audio.capture_interface import AudioSource, SourceKind
from eve.audio.platforms.soundcard_backend import SoundCardBackend


class WasapiLoopbackBackend(SoundCardBackend):
    key = "wasapi"
    display_name = "Windows system audio (WASAPI loopback)"

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        if not sys.platform.startswith("win"):
            return False, "WASAPI is only available on Windows"
        return super().availability()

    def _devices(self, sc: Any) -> list[tuple[AudioSource, Any]]:
        default_name = self._default_marker(sc)
        result = []
        for mic in sc.all_microphones(include_loopback=True):
            if not getattr(mic, "isloopback", False):
                continue  # real microphones are never valid sources
            name = str(mic.name)
            source = AudioSource(
                id=f"{self.key}:{mic.id}",
                name=f"{name} (loopback)",
                kind=SourceKind.SYSTEM_OUTPUT,
                is_default=name == default_name,
                description="Everything played through this output device",
            )
            result.append((source, mic))
        return result
