"""Time-step-aware smoothing and adaptive normalization.

All time constants are in seconds and every ``update`` takes ``dt`` so behaviour does not
depend on the hop size or frame rate.
"""

from __future__ import annotations

import math


def _alpha(dt: float, tau: float) -> float:
    """One-pole coefficient for time constant ``tau`` (0 tau = no smoothing)."""
    if tau <= 0.0:
        return 1.0
    return 1.0 - math.exp(-dt / tau)


class ExpSmoother:
    """Asymmetric exponential smoother (separate rise/fall time constants)."""

    def __init__(self, attack: float, release: float, initial: float = 0.0) -> None:
        self.attack = attack
        self.release = release
        self.value = initial

    def update(self, target: float, dt: float) -> float:
        tau = self.attack if target > self.value else self.release
        self.value += (target - self.value) * _alpha(dt, tau)
        return self.value

    def reset(self, value: float = 0.0) -> None:
        self.value = value


class PeakFollower:
    """Instant attack, exponential release toward ``floor`` — a running loudness reference."""

    def __init__(self, release: float, floor: float, initial: float | None = None) -> None:
        self.release = release
        self.floor = floor
        self.value = floor if initial is None else max(initial, floor)

    def update(self, x: float, dt: float) -> float:
        decayed = self.floor + (self.value - self.floor) * math.exp(-dt / self.release)
        self.value = max(x, decayed, self.floor)
        return self.value


class AdaptiveNormalizer:
    """Maps a non-negative signal to 0..1 relative to its own recent peak.

    ``headroom`` < 1 lets typical peaks reach 1.0 even though the reference decays slowly.
    The floor prevents silence/noise from being amplified into full-scale values.
    """

    def __init__(self, release: float = 8.0, floor: float = 1e-4, headroom: float = 0.85) -> None:
        self.peak = PeakFollower(release, floor)
        self.headroom = headroom

    def update(self, x: float, dt: float, gain: float = 1.0) -> float:
        reference = self.peak.update(x, dt) * self.headroom
        return min(1.0, max(0.0, gain * x / reference))

    def reset(self) -> None:
        self.peak.value = self.peak.floor


def db(x: float) -> float:
    return 20.0 * math.log10(max(x, 1e-12))
