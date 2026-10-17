"""Onset detection (adaptive threshold peak picking) and tempo-locked beat tracking.

Onsets are transients — any sharp attack. Beats are tempo-consistent pulses predicted by
the BeatTracker from the tempo estimate and corrected by observed onsets (a phase-locked
loop). A loud peak that does not fit the beat grid is an onset, not a beat.
"""

from __future__ import annotations

import numpy as np

from eve.audio.audio_features import PulseEvent, PulseKind
from eve.audio.normalization import PeakFollower
from eve.audio.tempo_estimator import TempoEstimate


class OnsetDetector:
    def __init__(
        self,
        fps: float,
        window_seconds: float = 1.0,
        threshold_k: float = 1.6,
        min_interval: float = 0.1,
        absolute_floor: float = 0.004,
    ) -> None:
        self.fps = fps
        self._hist = np.zeros(max(8, int(window_seconds * fps)), dtype=np.float64)
        self._idx = 0
        self._filled = 0
        self.threshold_k = threshold_k
        self.min_interval = min_interval
        self.absolute_floor = absolute_floor
        self._prev1 = 0.0  # value at t-1
        self._prev2 = 0.0  # value at t-2
        self._thr_prev1 = 0.0
        self._last_onset = -1e9
        self._peak = PeakFollower(release=4.0, floor=absolute_floor * 4)
        self.threshold = 0.0

    def reset(self) -> None:
        self._hist.fill(0.0)
        self._idx = self._filled = 0
        self._prev1 = self._prev2 = self._thr_prev1 = 0.0
        self._last_onset = -1e9

    def update(self, value: float, t: float, dt: float) -> float | None:
        """Feed one ODF sample at time ``t``. Returns onset strength (0..1) if the
        *previous* sample was an onset peak (one-hop latency), else None."""
        filled = self._hist[: self._filled] if self._filled < self._hist.shape[0] else self._hist
        if filled.shape[0] >= 4:
            med = float(np.median(filled))
            mad = float(np.mean(np.abs(filled - med)))
            thr = med + self.threshold_k * mad + self.absolute_floor
        else:
            thr = float("inf")
        self.threshold = thr
        peak_ref = self._peak.update(value, dt)

        result = None
        candidate = self._prev1
        if (
            candidate > self._thr_prev1
            and candidate >= self._prev2
            and candidate > value
            and (t - dt) - self._last_onset >= self.min_interval
        ):
            self._last_onset = t - dt
            span = max(peak_ref - self._thr_prev1, 1e-9)
            result = float(np.clip((candidate - self._thr_prev1) / span, 0.05, 1.0))

        self._hist[self._idx] = value
        self._idx = (self._idx + 1) % self._hist.shape[0]
        self._filled = min(self._filled + 1, self._hist.shape[0])
        self._prev2, self._prev1, self._thr_prev1 = self._prev1, value, thr
        return result


class BeatTracker:
    """Phase-locked beat prediction. Emits BEAT events only while tempo is trusted."""

    def __init__(
        self,
        min_confidence: float = 0.3,
        correction_gain: float = 0.3,
        capture_window: float = 0.22,
        max_unconfirmed: int = 8,
        realign_interval: float = 2.0,
    ) -> None:
        self.realign_interval = realign_interval
        self.min_confidence = min_confidence
        self.correction_gain = correction_gain
        self.capture_window = capture_window  # fraction of a period
        self.max_unconfirmed = max_unconfirmed
        self.reset()

    def reset(self) -> None:
        self.period = 0.0
        self.next_beat: float | None = None
        self.last_beat: float | None = None
        self._unconfirmed = 0  # consecutive predicted beats without a supporting onset
        self._confirm_strength = 0.0
        self._last_confirmed = False  # an onset supported the most recent emitted beat
        self._next_confirmed = False  # an onset already supported the upcoming beat
        self._since_realign = 0.0
        self._misaligned = 0

    @property
    def realign_due(self) -> bool:
        return not self.locked or self._since_realign >= self.realign_interval

    @property
    def locked(self) -> bool:
        return self.next_beat is not None and self.period > 0

    def phase(self, t: float) -> float:
        if not self.locked or self.next_beat is None:
            return 0.0
        return float(np.clip(1.0 - (self.next_beat - t) / self.period, 0.0, 1.0))

    def update(
        self,
        t: float,
        tempo: TempoEstimate,
        onset_strength: float | None,
        onset_time: float | None = None,
        bass: float = 0.0,
        beat_offset: float | None = None,
        dt: float = 0.0,
    ) -> PulseEvent | None:
        """``beat_offset``: seconds since the comb-aligned beat (TempoEstimator.beat_offset);
        used to lock and periodically re-check the grid phase."""
        if tempo.confidence < self.min_confidence or tempo.period <= 0:
            if tempo.confidence < self.min_confidence * 0.6:
                self.reset()
            return None

        # Follow tempo changes smoothly; re-lock on large changes.
        if self.period <= 0 or abs(tempo.period - self.period) > 0.15 * self.period:
            self.period = tempo.period
            self.next_beat = None
        else:
            self.period += 0.2 * (tempo.period - self.period)

        if self.next_beat is None and beat_offset is not None:
            # Lock the grid to the comb-aligned phase (strongest periodic pulses).
            self.last_beat = t - beat_offset
            self.next_beat = self.last_beat + self.period
            self._unconfirmed = 0
            self._confirm_strength = max(self._confirm_strength, 0.5)
            self._last_confirmed = True
            self._next_confirmed = False
            self._since_realign = 0.0
        elif self.next_beat is not None:
            self._since_realign += dt
            if beat_offset is not None and self._since_realign >= self.realign_interval:
                self._since_realign = 0.0
                aligned_last = t - beat_offset
                error = (aligned_last - (self.next_beat - self.period)) / self.period
                error -= round(error)
                if abs(error) > 0.25:
                    self._misaligned += 1
                    if self._misaligned >= 2:  # consistently on the wrong pulse: re-lock
                        self.next_beat = aligned_last + self.period * (1 + int((t - aligned_last) // self.period))
                        self._misaligned = 0
                else:
                    self._misaligned = 0

        if onset_strength is not None:
            when = t if onset_time is None else onset_time
            if self.next_beat is None:
                return None  # not locked yet: wait for comb alignment
            candidates = [self.next_beat] if self.last_beat is None else [self.next_beat, self.last_beat]
            nearest = min(candidates, key=lambda b: abs(when - b))
            error = when - nearest
            if abs(error) < self.capture_window * self.period:
                self.next_beat += self.correction_gain * error  # shift the grid toward the onset
                if nearest == self.last_beat:
                    self._last_confirmed = True
                else:
                    self._next_confirmed = True
                self._confirm_strength = 0.6 * self._confirm_strength + 0.4 * onset_strength

        if self.next_beat is not None and t >= self.next_beat:
            if self.last_beat is not None:
                self._unconfirmed = 0 if self._last_confirmed else self._unconfirmed + 1
            if self._unconfirmed > self.max_unconfirmed:
                self.reset()
                return None
            beat_time = self.next_beat
            confirmed = self._next_confirmed
            self._last_confirmed = confirmed
            self._next_confirmed = False
            self.last_beat = beat_time
            self.next_beat = beat_time + self.period
            strength = float(np.clip(self._confirm_strength * (1.0 if confirmed else 0.7), 0.15, 1.0))
            return PulseEvent(PulseKind.BEAT, beat_time, strength, bass, confirmed)
        return None
