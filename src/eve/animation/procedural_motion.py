"""Smooth deterministic noise for organic, non-repeating micro-motion.

Value noise with quintic interpolation: continuous with continuous derivatives, so it
never produces jitter. Seeded so tests are reproducible.
"""

from __future__ import annotations

import math

import numpy as np


class SmoothNoise:
    def __init__(self, seed: int = 0, size: int = 512) -> None:
        rng = np.random.default_rng(seed)
        self._values = rng.uniform(-1.0, 1.0, size)
        self._size = size

    def __call__(self, t: float) -> float:
        i = math.floor(t)
        f = t - i
        a = self._values[i % self._size]
        b = self._values[(i + 1) % self._size]
        u = f * f * f * (f * (f * 6 - 15) + 10)
        return float(a + (b - a) * u)

    def fractal(self, t: float, octaves: int = 2, gain: float = 0.5) -> float:
        total = 0.0
        amp = 1.0
        norm = 0.0
        freq = 1.0
        for o in range(octaves):
            total += amp * self(t * freq + o * 37.1)
            norm += amp
            amp *= gain
            freq *= 2.03
        return total / norm
