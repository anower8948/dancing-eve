"""Damped spring systems — the source of inertia, overshoot and follow-through.

Each channel follows its target as a mass on a damped spring:

    a = ω² (target − x) − 2ζω v

ω = 2π·frequency sets responsiveness, ζ the damping ratio (<1 overshoots, 1 = critical).
Integration is semi-implicit Euler with fixed sub-steps (≤ 1/240 s), so the motion is
stable and frame-rate independent. Velocity limits cap the speed of heavy parts.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike

MAX_SUBSTEP = 1.0 / 240.0


class SpringBank:
    """Vectorised springs; channel ``i`` has its own frequency, damping and speed limit."""

    def __init__(
        self,
        frequency_hz: Sequence[float],
        damping: Sequence[float],
        max_velocity: ArrayLike | None = None,
        angular: ArrayLike | None = None,
        initial: ArrayLike | None = None,
    ) -> None:
        n = len(frequency_hz)
        if len(damping) != n:
            raise ValueError("frequency and damping lengths differ")
        self.omega = 2.0 * math.pi * np.asarray(frequency_hz, dtype=np.float64)
        self.zeta = np.asarray(damping, dtype=np.float64)
        self.max_velocity = np.full(n, np.inf) if max_velocity is None else np.asarray(max_velocity, dtype=np.float64)
        self.angular = np.zeros(n, dtype=bool) if angular is None else np.asarray(angular, dtype=bool)
        self.x = np.zeros(n) if initial is None else np.asarray(initial, dtype=np.float64).copy()
        self.v = np.zeros(n)
        self._k = self.omega**2
        self._c = 2.0 * self.zeta * self.omega
        self._err = np.zeros(n)
        self._acc = np.zeros(n)

    def __len__(self) -> int:
        return self.x.shape[0]

    def reset(self, values: Sequence[float] | None = None) -> None:
        self.x[:] = 0.0 if values is None else values
        self.v[:] = 0.0

    def impulse(self, index: int, delta_v: float) -> None:
        """Instantly change a channel's velocity (a 'kick'); the spring does the rest."""
        self.v[index] += delta_v

    def step(self, target: np.ndarray, dt: float) -> np.ndarray:
        if dt <= 0:
            return self.x
        steps = max(1, math.ceil(dt / MAX_SUBSTEP))
        h = dt / steps
        err, acc = self._err, self._acc
        for _ in range(steps):
            np.subtract(target, self.x, out=err)
            if self.angular.any():
                # Shortest-arc error for angles so a target that wraps 180 -> -180
                # (or a completed 360° spin snapping back to 0) causes no visible motion.
                err[self.angular] = (err[self.angular] + 180.0) % 360.0 - 180.0
            np.multiply(self._k, err, out=acc)
            acc -= self._c * self.v
            self.v += acc * h
            np.clip(self.v, -self.max_velocity, self.max_velocity, out=self.v)
            self.x += self.v * h
        if self.angular.any():
            self.x[self.angular] = (self.x[self.angular] + 180.0) % 360.0 - 180.0
        return self.x


class Spring:
    """Scalar convenience wrapper around a one-channel SpringBank."""

    def __init__(self, frequency_hz: float, damping: float, initial: float = 0.0, max_velocity: float = math.inf):
        self._bank = SpringBank([frequency_hz], [damping], [max_velocity], initial=[initial])
        self._target = np.zeros(1)

    @property
    def value(self) -> float:
        return float(self._bank.x[0])

    @property
    def velocity(self) -> float:
        return float(self._bank.v[0])

    def impulse(self, delta_v: float) -> None:
        self._bank.impulse(0, delta_v)

    def update(self, target: float, dt: float) -> float:
        self._target[0] = target
        self._bank.step(self._target, dt)
        return self.value
