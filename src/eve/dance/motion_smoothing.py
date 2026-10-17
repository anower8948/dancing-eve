"""Smoothing of control signals (music features -> dance parameters).

Pose smoothing itself is done by the spring layer; these filters condition the *inputs*
so state decisions and amplitudes do not twitch with every analysis frame.
"""

from __future__ import annotations

import math

from eve.audio.normalization import ExpSmoother

__all__ = ["ExpSmoother", "OneEuroFilter", "SlewLimiter"]


class SlewLimiter:
    """Limits how fast a value may change (units per second)."""

    def __init__(self, rate_up: float, rate_down: float | None = None, initial: float = 0.0) -> None:
        self.rate_up = rate_up
        self.rate_down = rate_up if rate_down is None else rate_down
        self.value = initial

    def update(self, target: float, dt: float) -> float:
        delta = target - self.value
        limit = (self.rate_up if delta > 0 else self.rate_down) * dt
        self.value += max(-limit, min(limit, delta))
        return self.value


class OneEuroFilter:
    """Casiez et al. 1€ filter: smooth when slow, responsive when fast."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.5, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x: float | None = None
        self._dx = 0.0

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def update(self, x: float, dt: float) -> float:
        if self._x is None or dt <= 0:
            self._x = x
            return x
        dx = (x - self._x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx += a_d * (dx - self._dx)
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        a = self._alpha(cutoff, dt)
        self._x += a * (x - self._x)
        return self._x
