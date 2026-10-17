"""Linux system-output capture from PulseAudio / PipeWire-Pulse monitor sources.

Every output sink has a ".monitor" source carrying what the sink plays. SoundCard talks to
libpulse, which PipeWire also serves through pipewire-pulse (default on Ubuntu 22.10+).
Pure-ALSA systems without a sound server have no monitor sources and are unsupported.

Status: implemented, NOT yet verified on a real Ubuntu machine.
"""

from __future__ import annotations

import sys
from typing import Any

from eve.audio.capture_interface import AudioSource, SourceKind
from eve.audio.platforms.soundcard_backend import SoundCardBackend


class PulseMonitorBackend(SoundCardBackend):
    key = "pulse"
    display_name = "Linux output monitor (PulseAudio / PipeWire)"

    @classmethod
    def availability(cls) -> tuple[bool, str]:
        if not sys.platform.startswith("linux"):
            return False, "PulseAudio monitor capture is only available on Linux"
        ok, reason = super().availability()
        if not ok:
            return False, reason + " — is PulseAudio or pipewire-pulse running, and is libpulse0 installed?"
        return True, ""

    def _default_marker(self, sc: Any) -> str:
        try:
            return str(sc.default_speaker().id)
        except Exception:
            return ""

    def _devices(self, sc: Any) -> list[tuple[AudioSource, Any]]:
        default_sink = self._default_marker(sc)
        result = []
        for mic in sc.all_microphones(include_loopback=True):
            if not getattr(mic, "isloopback", False):
                continue  # only monitor sources, never microphones
            mic_id = str(mic.id)
            source = AudioSource(
                id=f"{self.key}:{mic_id}",
                name=str(mic.name),
                kind=SourceKind.MONITOR,
                is_default=bool(default_sink) and mic_id == default_sink + ".monitor",
                description="Monitor of an output device",
            )
            result.append((source, mic))
        return result
