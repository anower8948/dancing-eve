"""Data published by the analyzer and consumed by the dance controller."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PulseKind(Enum):
    ONSET = "onset"  # transient / percussive attack (not necessarily on the beat)
    BEAT = "beat"  # tempo-consistent beat from the beat tracker
    SURGE = "surge"  # sudden rise in loudness (e.g. a drop or chorus entry)


@dataclass(frozen=True, slots=True)
class PulseEvent:
    kind: PulseKind
    time: float  # analysis time in seconds (audio clock)
    strength: float  # 0..1
    bass: float = 0.0  # 0..1 low-frequency share of the pulse
    confirmed: bool = True  # BEAT: an onset was observed near the predicted time


@dataclass(frozen=True, slots=True)
class AudioFeatures:
    """One analysis frame. All "normalized" values are 0..1 and volume-independent."""

    time: float = 0.0  # analysis clock (seconds of audio processed)
    sample_rate: int = 0
    rms: float = 0.0  # raw linear RMS of the current window
    level_db: float = -120.0  # dBFS of the current window
    energy: float = 0.0  # loudness relative to the recent loudness peak
    low: float = 0.0  # 20–150 Hz presence
    mid: float = 0.0  # 150–2000 Hz presence
    high: float = 0.0  # 2–10 kHz presence
    flux: float = 0.0  # normalized spectral flux
    onset_strength: float = 0.0  # normalized onset detection function
    bass_pulse: float = 0.0  # normalized low-band flux (kick drums)
    onset_rate: float = 0.0  # onsets per second over the last few seconds
    intensity: float = 0.0  # rhythmic drive: onset density + flux, volume-independent
    tempo_bpm: float = 0.0  # 0 when unknown
    tempo_confidence: float = 0.0
    beat_phase: float = 0.0  # 0 at a beat, rising to 1 just before the next
    beat_period: float = 0.0  # seconds; 0 when unknown
    music_activity: float = 0.0  # smoothed 0..1 "music is playing" indicator
    is_silent: bool = True
    energy_change: float = 1.0  # short-term / long-term loudness ratio

    @property
    def has_tempo(self) -> bool:
        return self.tempo_bpm > 0.0 and self.beat_period > 0.0


SILENT_FEATURES = AudioFeatures()
