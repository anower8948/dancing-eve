"""Deterministic synthetic audio for analysis tests.

These signals exercise the analysis pipeline only. They are NOT a substitute for testing
real operating-system audio capture (see docs/testing.md).
"""

from __future__ import annotations

import numpy as np

SR = 48000


def silence(seconds: float, sr: int = SR) -> np.ndarray:
    return np.zeros(int(seconds * sr), dtype=np.float32)


def tone(seconds: float, freq: float = 440.0, amp: float = 0.3, sr: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def noise(seconds: float, amp: float = 0.05, sr: int = SR, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (amp * rng.standard_normal(int(seconds * sr))).astype(np.float32)


def kick(sr: int = SR, length: float = 0.18, amp: float = 0.8) -> np.ndarray:
    """A synthetic kick drum: pitch-swept sine with an exponential decay."""
    t = np.arange(int(length * sr)) / sr
    freq = 50 + 90 * np.exp(-t * 30)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    env = np.exp(-t * 18)
    click = np.exp(-t * 400) * 0.3
    fade = np.minimum(1.0, (length - t) / 0.03)  # no step at the tail (would be a fake onset)
    return (amp * (np.sin(phase) * env + click) * fade).astype(np.float32)


def hat(sr: int = SR, length: float = 0.05, amp: float = 0.15, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(length * sr)) / sr
    fade = np.minimum(1.0, (length - t) / 0.01)
    return (amp * rng.standard_normal(t.shape[0]) * np.exp(-t * 80) * fade).astype(np.float32)


def beat_track(
    seconds: float,
    bpm: float = 120.0,
    amp: float = 0.8,
    sr: int = SR,
    with_hats: bool = True,
    pad_level: float = 0.04,
) -> np.ndarray:
    """Kick on every beat, hi-hats on the off-beats, a quiet sustained pad underneath."""
    n = int(seconds * sr)
    out = np.zeros(n, dtype=np.float32)
    period = 60.0 / bpm
    k = kick(sr, amp=amp)
    h = hat(sr, amp=0.15 * amp / 0.8)
    t = 0.0
    while t < seconds:
        i = int(t * sr)
        seg = out[i : i + k.shape[0]]
        seg += k[: seg.shape[0]]
        if with_hats:
            j = int((t + period / 2) * sr)
            if j < n:
                seg2 = out[j : j + h.shape[0]]
                seg2 += h[: seg2.shape[0]]
        t += period
    if pad_level > 0:
        tt = np.arange(n) / sr
        out += (pad_level * amp / 0.8 * (np.sin(2 * np.pi * 220 * tt) + 0.5 * np.sin(2 * np.pi * 330 * tt))).astype(
            np.float32
        )
    return out


def energy_step(quiet_seconds: float, loud_seconds: float, sr: int = SR) -> np.ndarray:
    """Quiet groove followed by a much louder section (a 'drop')."""
    quiet = beat_track(quiet_seconds, amp=0.1, sr=sr)
    loud = beat_track(loud_seconds, amp=0.9, sr=sr)
    return np.concatenate((quiet, loud))
