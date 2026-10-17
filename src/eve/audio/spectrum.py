"""Windowed FFT, band energies and spectral flux for one analysis window."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BANDS_HZ = {"low": (20.0, 150.0), "mid": (150.0, 2000.0), "high": (2000.0, 10000.0)}
FLUX_MAX_HZ = 10000.0
LOG_COMPRESSION = 1000.0  # gamma in log(1 + gamma * |X|); makes flux gain-independent


@dataclass(frozen=True, slots=True)
class SpectrumFrame:
    rms: float
    low: float  # band RMS-equivalent amplitudes
    mid: float
    high: float
    flux: float  # mean positive log-magnitude change across bins
    low_flux: float  # same, restricted to the low band


class SpectrumAnalyzer:
    """Stateful: keeps the previous log spectrum for flux. Allocates its work arrays once."""

    def __init__(self, sample_rate: int, fft_size: int) -> None:
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.window = np.hanning(fft_size).astype(np.float32)
        # Normalise so a full-scale sine reports amplitude ~1 regardless of window/FFT size.
        self._amp_scale = 2.0 / float(self.window.sum())
        freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
        self._band_slices = {name: self._slice(freqs, lo, hi) for name, (lo, hi) in BANDS_HZ.items()}
        self._flux_slice = self._slice(freqs, 20.0, FLUX_MAX_HZ)
        self._low_slice = self._band_slices["low"]
        n_bins = freqs.shape[0]
        self._windowed = np.zeros(fft_size, dtype=np.float32)
        self._log_mag = np.zeros(n_bins, dtype=np.float32)
        self._prev_log = np.zeros(n_bins, dtype=np.float32)
        self._diff = np.zeros(n_bins, dtype=np.float32)
        self._has_prev = False

    @staticmethod
    def _slice(freqs: np.ndarray, lo: float, hi: float) -> slice:
        start = int(np.searchsorted(freqs, lo))
        stop = max(start + 1, int(np.searchsorted(freqs, min(hi, freqs[-1]))))
        return slice(start, stop)

    def reset(self) -> None:
        self._has_prev = False
        self._prev_log.fill(0.0)

    def process(self, window_samples: np.ndarray) -> SpectrumFrame:
        rms = float(np.sqrt(np.mean(np.square(window_samples, dtype=np.float32))))
        np.multiply(window_samples, self.window, out=self._windowed)
        mag = np.abs(np.fft.rfft(self._windowed)).astype(np.float32, copy=False)
        mag *= self._amp_scale

        def band(sl: slice) -> float:
            seg = mag[sl]
            return float(np.sqrt(np.mean(seg * seg))) if seg.size else 0.0

        low = band(self._band_slices["low"])
        mid = band(self._band_slices["mid"])
        high = band(self._band_slices["high"])

        np.multiply(mag, LOG_COMPRESSION, out=self._log_mag)
        np.log1p(self._log_mag, out=self._log_mag)
        if self._has_prev:
            np.subtract(self._log_mag, self._prev_log, out=self._diff)
            np.maximum(self._diff, 0.0, out=self._diff)
            flux = float(self._diff[self._flux_slice].mean())
            low_flux = float(self._diff[self._low_slice].mean())
        else:
            flux = low_flux = 0.0
            self._has_prev = True
        self._prev_log[:] = self._log_mag
        return SpectrumFrame(rms, low, mid, high, flux, low_flux)


def hop_and_fft_size(sample_rate: int) -> tuple[int, int]:
    """Hop ≈ 10.7 ms (power of two) and a 4× FFT window, for any sample rate."""
    target = sample_rate * 0.0107
    hop = int(2 ** round(np.log2(max(target, 32.0))))
    return hop, hop * 4
