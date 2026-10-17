"""Bounded, thread-safe mono sample ring buffer between capture and analysis.

The capture thread writes; the analyzer worker reads fixed-size hops. When the reader
falls behind, the oldest samples are discarded (counted as overruns) — the buffer never
grows, and the reader always sees the most recent audio.
"""

from __future__ import annotations

import threading

import numpy as np


class SampleBuffer:
    def __init__(self, capacity_seconds: float = 2.0, sample_rate: int = 48000) -> None:
        self._capacity_seconds = capacity_seconds
        self._cond = threading.Condition()
        self._reset_locked(sample_rate)
        self.overruns = 0  # number of writes that discarded unread samples
        self.dropped_samples = 0

    def _reset_locked(self, sample_rate: int) -> None:
        self.sample_rate = int(sample_rate)
        self._capacity = max(4096, int(self._capacity_seconds * self.sample_rate))
        self._data = np.zeros(self._capacity, dtype=np.float32)
        self._write = 0  # absolute sample counters (monotonic)
        self._read = 0
        self.generation = getattr(self, "generation", 0) + 1

    @property
    def capacity(self) -> int:
        return self._capacity

    def reset(self, sample_rate: int | None = None) -> None:
        with self._cond:
            self._reset_locked(sample_rate or self.sample_rate)
            self._cond.notify_all()

    def available(self) -> int:
        with self._cond:
            return self._write - self._read

    def write(self, samples: np.ndarray, sample_rate: int) -> None:
        """Append mono float32 samples. A sample-rate change resets the buffer."""
        n = int(samples.shape[0])
        if n == 0:
            return
        with self._cond:
            if sample_rate != self.sample_rate:
                self._reset_locked(sample_rate)
            if n >= self._capacity:
                samples = samples[-self._capacity :]
                n = self._capacity
            start = self._write % self._capacity
            first = min(n, self._capacity - start)
            self._data[start : start + first] = samples[:first]
            if first < n:
                self._data[: n - first] = samples[first:]
            self._write += n
            unread = self._write - self._read
            if unread > self._capacity:
                lost = unread - self._capacity
                self._read += lost
                self.overruns += 1
                self.dropped_samples += lost
            self._cond.notify_all()

    def read_into(self, out: np.ndarray, timeout: float | None = None) -> bool:
        """Fill ``out`` with the next ``len(out)`` samples. False on timeout (out untouched)."""
        n = out.shape[0]
        with self._cond:
            if self._write - self._read < n and not self._cond.wait_for(lambda: self._write - self._read >= n, timeout):
                return False
            start = self._read % self._capacity
            first = min(n, self._capacity - start)
            out[:first] = self._data[start : start + first]
            if first < n:
                out[first:] = self._data[: n - first]
            self._read += n
            return True

    def wake(self) -> None:
        """Wake a blocked reader (used during shutdown)."""
        with self._cond:
            self._cond.notify_all()


def to_mono(samples: np.ndarray) -> np.ndarray:
    """Downmix (frames, channels) to float32 mono without copying mono input."""
    if samples.ndim == 1:
        return samples if samples.dtype == np.float32 else samples.astype(np.float32)
    if samples.shape[1] == 1:
        return np.ascontiguousarray(samples[:, 0], dtype=np.float32)
    return samples.mean(axis=1, dtype=np.float32)


def to_float32(samples: np.ndarray) -> np.ndarray:
    """Convert integer PCM to float32 in ±1; float input passes through."""
    if samples.dtype == np.float32:
        return samples
    if samples.dtype == np.int16:
        return samples.astype(np.float32) / 32768.0
    if samples.dtype == np.int32:
        return samples.astype(np.float32) / 2147483648.0
    if samples.dtype == np.uint8:
        return (samples.astype(np.float32) - 128.0) / 128.0
    return samples.astype(np.float32)
