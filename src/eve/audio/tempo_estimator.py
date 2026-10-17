"""Tempo estimation from the onset-strength envelope (autocorrelation + tempo prior).

Confidence is deliberately conservative: it needs a clear autocorrelation peak *and* a
stable estimate over consecutive updates. Callers must treat low confidence as "no tempo"
rather than trusting the BPM number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

_SMOOTH = np.array([0.0625, 0.25, 0.375, 0.25, 0.0625])
MIN_ENVELOPE_STD = 0.02  # onset envelope variation below this means "no rhythm"


@dataclass(frozen=True, slots=True)
class TempoEstimate:
    bpm: float
    confidence: float  # 0..1
    period: float  # seconds per beat


class TempoEstimator:
    def __init__(
        self,
        fps: float,
        history_seconds: float = 8.0,
        min_bpm: float = 60.0,
        max_bpm: float = 190.0,
        update_interval: float = 0.5,
        prior_center_bpm: float = 115.0,
        prior_octaves: float = 0.9,
        min_history_seconds: float = 3.0,
    ) -> None:
        self.fps = fps
        self._n = int(history_seconds * fps)
        self._env = np.zeros(self._n, dtype=np.float64)
        self._idx = 0
        self._count = 0
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        self.update_interval = update_interval
        self.min_history = int(min_history_seconds * fps)
        self._since_update = 0.0
        self._prior_center = prior_center_bpm
        self._prior_octaves = prior_octaves
        self._lag_min = max(2, int(math.floor(fps * 60.0 / max_bpm)))
        self._lag_max = min(self._n // 2, int(math.ceil(fps * 60.0 / min_bpm)))
        lags = np.arange(self._lag_max + 1, dtype=np.float64)
        with np.errstate(divide="ignore"):
            bpms = np.where(lags > 0, 60.0 * fps / np.maximum(lags, 1e-9), 0.0)
            self._prior = np.exp(-0.5 * (np.log2(np.maximum(bpms, 1e-9) / prior_center_bpm) / prior_octaves) ** 2)
        self._prior[: self._lag_min] = 0.0
        self._stable = 0
        self._last_bpm = 0.0
        self.current = TempoEstimate(0.0, 0.0, 0.0)

    def reset(self) -> None:
        self._env.fill(0.0)
        self._idx = 0
        self._count = 0
        self._stable = 0
        self._last_bpm = 0.0
        self._since_update = 0.0
        self.current = TempoEstimate(0.0, 0.0, 0.0)

    def push(self, value: float, dt: float) -> TempoEstimate | None:
        """Add one onset-envelope sample. Returns a new estimate when one was computed."""
        self._env[self._idx] = value
        self._idx = (self._idx + 1) % self._n
        self._count = min(self._count + 1, self._n)
        self._since_update += dt
        if self._since_update < self.update_interval:
            return None
        self._since_update = 0.0
        self.current = self._estimate()
        return self.current

    def _ordered(self) -> np.ndarray:
        if self._count < self._n:
            return self._env[: self._count]
        return np.concatenate((self._env[self._idx :], self._env[: self._idx]))

    def _estimate(self) -> TempoEstimate:
        if self._count < self.min_history:
            return TempoEstimate(0.0, 0.0, 0.0)
        x = self._ordered()
        # Light smoothing: sharp one-frame onset peaks at fractional lags would otherwise
        # correlate poorly with integer lags and bias the estimate toward half-tempo.
        x = np.convolve(x, _SMOOTH, mode="same")
        x = x - x.mean()
        if float(np.std(x)) < MIN_ENVELOPE_STD:
            # A steady signal (sustained tone, constant noise floor) has no rhythm; without
            # this gate the scale-invariant ACF would find "tempo" in numerical noise.
            self._stable = 0
            return TempoEstimate(0.0, 0.0, 0.0)
        n = x.shape[0]
        spectrum = np.fft.rfft(x, 2 * n)
        acf = np.fft.irfft(spectrum * np.conj(spectrum))[:n]
        acf /= acf[0]
        lag_max = min(self._lag_max, n // 2)
        if lag_max <= self._lag_min + 2:
            return TempoEstimate(0.0, 0.0, 0.0)
        # Unbiased ACF so long lags are not penalised by the shrinking overlap.
        lags = np.arange(lag_max + 1)
        unbiased = acf[: lag_max + 1] * (n / np.maximum(n - lags, 1))
        # Harmonic enhancement: true beat periods also correlate at 2x the lag.
        score = unbiased.copy()
        double = np.minimum(lags * 2, n - 1)
        score += 0.5 * np.clip(acf[double] * (n / np.maximum(n - double, 1)), 0.0, None)
        score *= self._prior[: lag_max + 1]
        window = score[self._lag_min : lag_max + 1]
        best = int(np.argmax(window)) + self._lag_min
        # Parabolic interpolation for sub-frame accuracy.
        lag = float(best)
        if self._lag_min < best < lag_max:
            a, b, c = score[best - 1], score[best], score[best + 1]
            denom = a - 2 * b + c
            if abs(denom) > 1e-12:
                lag = best + 0.5 * (a - c) / denom
        bpm = 60.0 * self.fps / lag
        window_acf = unbiased[self._lag_min : lag_max + 1]
        baseline = float(np.median(window_acf))
        spread = float(np.std(window_acf)) + 1e-9

        def confidence_at(lag_index: int) -> float:
            # How far the chosen peak stands out from the ACF's own spread (z-score).
            # Measured: clear beats z ≥ 3, white noise z ≤ 1.7 (docs/audio-capture.md).
            peak_value = float(unbiased[lag_index])
            z = (peak_value - baseline) / spread
            return float(np.clip((z - 2.2) / 1.4, 0.0, 1.0) * np.clip(peak_value / 0.5, 0.0, 1.0))

        raw_conf = confidence_at(best)

        if self._last_bpm > 0:
            ratio = bpm / self._last_bpm
            if abs(ratio - 1.0) < 0.04:
                self._stable += 1
            elif abs(ratio - 2.0) < 0.08 or abs(ratio - 0.5) < 0.04:
                # Octave jump: keep the previous tempo only if it still scores nearly as well
                # (prevents half/double flip-flopping without locking in a wrong first guess).
                prev_lag = int(round(60.0 * self.fps / self._last_bpm))
                if self._lag_min <= prev_lag <= lag_max and score[prev_lag] >= 0.9 * score[best]:
                    bpm = self._last_bpm
                    raw_conf = confidence_at(prev_lag)
                    self._stable = max(0, self._stable - 1)
                else:
                    self._stable = 0
            else:
                self._stable = 0
        self._last_bpm = bpm
        stability = min(1.0, 0.35 + 0.22 * self._stable)
        confidence = raw_conf * stability
        return TempoEstimate(bpm, confidence, 60.0 / bpm)

    def beat_offset(self, period: float, seconds: float = 3.0) -> float | None:
        """Seconds since the most recent beat position that best explains the recent
        onset envelope (comb alignment). Picks the strong pulses (e.g. kicks) rather than
        whichever onset happened to come first. None without enough history."""
        lag = period * self.fps
        span = int(seconds * self.fps)
        if lag < 2 or self._count < max(span, int(2 * lag)):
            return None
        x = self._ordered()[-span:]
        n = x.shape[0]
        offsets = np.arange(int(lag))
        scores = np.zeros(offsets.shape[0])
        k = 0
        while True:
            positions = n - 1 - offsets - np.round(k * lag).astype(int)
            valid = positions >= 0
            if not valid.any():
                break
            scores[valid] += x[positions[valid]]
            k += 1
        best = int(np.argmax(scores))
        return best / self.fps
