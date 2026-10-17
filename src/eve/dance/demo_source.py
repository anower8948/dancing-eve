"""A scripted 'virtual song' that drives the dance without any audio (``--demo``).

Used to develop and test choreography independently of audio capture. It is clearly
labelled in the UI as demo mode and is never presented as listening to real music.
"""

from __future__ import annotations

from dataclasses import dataclass

from eve.audio.audio_features import AudioFeatures, PulseEvent, PulseKind


@dataclass(frozen=True)
class Section:
    seconds: float
    intensity: float
    energy: float
    playing: bool = True
    surge: bool = False


DEFAULT_SONG = (
    Section(10.0, 0.22, 0.45),
    Section(16.0, 0.55, 0.65),
    Section(16.0, 0.9, 0.95, surge=True),
    Section(10.0, 0.25, 0.4),
    Section(6.0, 0.0, 0.0, playing=False),
)


class DemoMusicSource:
    def __init__(self, bpm: float = 112.0, song: tuple[Section, ...] = DEFAULT_SONG) -> None:
        self.bpm = bpm
        self.period = 60.0 / bpm
        self.song = song
        self.length = sum(s.seconds for s in song)
        self.t = 0.0
        self._next_beat = 0.0
        self._half_done = False
        self._activity = 0.0
        self._section_index = -1

    def section_at(self, t: float) -> tuple[int, Section]:
        t %= self.length
        for i, section in enumerate(self.song):
            if t < section.seconds:
                return i, section
            t -= section.seconds
        return len(self.song) - 1, self.song[-1]

    def update(self, dt: float) -> tuple[AudioFeatures, list[PulseEvent]]:
        self.t += dt
        index, section = self.section_at(self.t)
        events: list[PulseEvent] = []
        if index != self._section_index:
            self._section_index = index
            if section.surge:
                events.append(PulseEvent(PulseKind.SURGE, self.t, 0.9, 0.8))
        target = 1.0 if section.playing else 0.0
        rate = 4.0 if target > self._activity else 1.0
        self._activity += (target - self._activity) * min(1.0, dt * rate)
        if section.playing:
            while self.t >= self._next_beat:
                strength = 0.5 + 0.5 * section.intensity
                events.append(PulseEvent(PulseKind.BEAT, self._next_beat, strength, 0.8, True))
                self._next_beat += self.period
                self._half_done = False
            if not self._half_done and self.t >= self._next_beat - self.period / 2:
                self._half_done = True
                if section.intensity > 0.4:
                    events.append(PulseEvent(PulseKind.ONSET, self.t, 0.4 * section.intensity, 0.2))
        else:
            self._next_beat = self.t + self.period
        phase = 1.0 - (self._next_beat - self.t) / self.period
        features = AudioFeatures(
            time=self.t,
            sample_rate=0,
            rms=0.1 * section.energy,
            level_db=-20.0 if section.playing else -120.0,
            energy=section.energy if section.playing else 0.0,
            low=section.energy,
            mid=section.energy * 0.8,
            high=section.intensity,
            flux=section.intensity,
            onset_strength=section.intensity,
            bass_pulse=max(0.0, 1.0 - phase * 4.0) if section.playing else 0.0,
            onset_rate=4.0 * section.intensity,
            intensity=section.intensity if section.playing else 0.0,
            tempo_bpm=self.bpm if section.playing else 0.0,
            tempo_confidence=0.9 if section.playing else 0.0,
            beat_phase=min(max(phase, 0.0), 1.0),
            beat_period=self.period if section.playing else 0.0,
            music_activity=self._activity,
            is_silent=not section.playing,
            energy_change=1.0,
        )
        return features, events
