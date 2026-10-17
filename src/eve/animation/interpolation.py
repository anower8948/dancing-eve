"""Easing curves and angle helpers. All curves map 0..1 -> 0..1 unless noted."""

from __future__ import annotations

import math


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smoothstep(t: float) -> float:
    t = clamp(t)
    return t * t * (3.0 - 2.0 * t)


def smootherstep(t: float) -> float:
    """Quintic: zero first and second derivatives at both ends (no visible 'kick')."""
    t = clamp(t)
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def ease_in_out_cubic(t: float) -> float:
    t = clamp(t)
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_cubic(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_cubic(t: float) -> float:
    t = clamp(t)
    return t * t * t


def ease_out_back(t: float, overshoot: float = 1.4) -> float:
    """Overshoots past 1 then settles — a controlled 'pop'."""
    t = clamp(t)
    c3 = overshoot + 1
    return 1 + c3 * (t - 1) ** 3 + overshoot * (t - 1) ** 2


def bell(t: float) -> float:
    """0 at both ends, 1 in the middle, smooth (sin²)."""
    t = clamp(t)
    s = math.sin(math.pi * t)
    return s * s


def window(t: float, start: float, end: float) -> float:
    """Local 0..1 progress of ``t`` inside [start, end] (clamped)."""
    if end <= start:
        return 1.0 if t >= end else 0.0
    return clamp((t - start) / (end - start))


def anticipate(t: float, amount: float = 0.15, split: float = 0.25) -> float:
    """A move that first goes slightly backwards (-amount) then eases to 1.

    Used for spins/turns/bounces: the small counter-movement reads as preparation.
    """
    t = clamp(t)
    if t < split:
        return -amount * bell(t / split * 0.5)  # ease into the wind-up
    u = (t - split) / (1 - split)
    return lerp(-amount, 1.0, ease_in_out_cubic(u)) if u < 1 else 1.0


def skewed_wave(phase: float, peak_at: float = 0.6) -> float:
    """Beat-synchronous bob: -1 exactly on the beat (phase 0), +1 at ``peak_at``.

    Rises slowly after the beat and drops quickly into the next one, which reads as the
    weight landing *on* the beat (with a natural lift beforehand).
    """
    p = phase % 1.0
    if p < peak_at:
        s = 0.5 * p / peak_at
    else:
        s = 0.5 + 0.5 * (p - peak_at) / (1 - peak_at)
    return -math.cos(2 * math.pi * s)


def wrap_degrees(a: float) -> float:
    """Wrap to (-180, 180]."""
    a = math.fmod(a + 180.0, 360.0)
    if a <= 0:
        a += 360.0
    return a - 180.0


def lerp_angle(a: float, b: float, t: float) -> float:
    """Interpolate along the shortest arc (degrees)."""
    return a + wrap_degrees(b - a) * t
