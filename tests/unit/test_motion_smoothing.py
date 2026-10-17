"""Springs, easing, limits and the layered animation controller."""

from __future__ import annotations

import numpy as np
import pytest

from eve.animation import interpolation as ip
from eve.animation.animation_controller import AnimationController
from eve.animation.idle_animation import IdleAnimator
from eve.animation.spring_dynamics import Spring, SpringBank
from eve.character.character_rig import N_CHANNELS, Ch
from eve.dance import motion_parameters as mp
from eve.dance.dance_controller import DanceOutput
from eve.dance.motion_smoothing import OneEuroFilter, SlewLimiter


def test_spring_converges_without_overshoot_when_critically_damped() -> None:
    s = Spring(2.0, 1.0)
    values = [s.update(1.0, 1 / 60) for _ in range(240)]
    assert values[-1] == pytest.approx(1.0, abs=1e-3)
    assert max(values) <= 1.0 + 1e-6


def test_underdamped_spring_overshoots_a_little() -> None:
    s = Spring(2.0, 0.5)
    values = [s.update(1.0, 1 / 60) for _ in range(240)]
    assert 1.05 < max(values) < 1.3


def test_spring_is_frame_rate_independent() -> None:
    a, b = Spring(3.0, 0.6), Spring(3.0, 0.6)
    for _ in range(60):
        a.update(1.0, 1 / 60)
    for _ in range(30):
        b.update(1.0, 1 / 30)
    assert a.value == pytest.approx(b.value, abs=0.01)


def test_velocity_limit_is_enforced() -> None:
    bank = SpringBank([10.0], [0.3], [1.0])
    target = np.array([100.0])
    for _ in range(30):
        bank.step(target, 1 / 60)
        assert abs(bank.v[0]) <= 1.0 + 1e-9


def test_angular_channel_takes_shortest_path() -> None:
    bank = SpringBank([3.0], [1.0], angular=[True], initial=[170.0])
    target = np.array([-170.0])  # 20° away through ±180, not 340°
    xs = []
    for _ in range(120):
        xs.append(float(bank.step(target, 1 / 60)[0]))
    travelled = sum(abs(((b - a) + 180) % 360 - 180) for a, b in zip(xs, xs[1:], strict=False))
    assert travelled < 25.0


def test_easing_endpoints_and_monotonic() -> None:
    for fn in (ip.smoothstep, ip.smootherstep, ip.ease_in_out_cubic, ip.ease_out_cubic, ip.ease_in_cubic):
        assert fn(0.0) == pytest.approx(0.0)
        assert fn(1.0) == pytest.approx(1.0)
        samples = [fn(t) for t in np.linspace(0, 1, 50)]
        assert all(b >= a - 1e-12 for a, b in zip(samples, samples[1:], strict=False))
    assert ip.ease_out_back(0.7) > 1.0  # controlled overshoot
    assert ip.anticipate(0.1) < 0.0 and ip.anticipate(1.0) == pytest.approx(1.0)
    assert ip.skewed_wave(0.0) == pytest.approx(-1.0) and ip.skewed_wave(0.6) == pytest.approx(1.0)
    assert ip.wrap_degrees(190.0) == pytest.approx(-170.0)
    assert ip.lerp_angle(170.0, -170.0, 0.5) == pytest.approx(180.0)


def test_slew_limiter_and_one_euro() -> None:
    s = SlewLimiter(rate_up=1.0)
    assert s.update(10.0, 0.5) == pytest.approx(0.5)
    f = OneEuroFilter(min_cutoff=1.0, beta=0.0)
    f.update(0.0, 0.01)
    assert 0.0 < f.update(1.0, 0.01) < 0.2


def test_motion_parameters_cover_every_channel_and_clamp() -> None:
    values = np.full(N_CHANNELS, 1e6)
    clamped = mp.clamp_pose(values)
    assert clamped[Ch.BODY_R] == mp.SPECS[Ch.BODY_R].hi
    assert clamped[Ch.EYE_OPEN] == 1.0
    assert len(mp.FREQUENCIES) == N_CHANNELS


def test_animation_controller_respects_limits_under_extreme_targets() -> None:
    anim = AnimationController(seed=1)
    extreme = DanceOutput(targets=np.full(N_CHANNELS, 500.0), weight=1.0)
    for _ in range(600):
        pose = anim.update(1 / 60, extreme)
    lo, hi = mp.LOWER, mp.UPPER
    finite = [ch for ch in Ch if ch != Ch.ROOT_H]
    margin = 0.25 * (hi - lo)  # springs may overshoot slightly past the target
    assert np.all(pose[finite] <= hi[finite] + margin[finite])
    assert np.all(pose[finite] >= lo[finite] - margin[finite])


def test_idle_blinks_and_stays_subtle() -> None:
    idle = IdleAnimator(seed=2)
    blinks = 0
    was_closed = False
    peak = np.zeros(N_CHANNELS)
    for _ in range(int(30 / (1 / 60))):
        out = idle.update(1 / 60)
        peak = np.maximum(peak, np.abs(out))
        closed = idle.blink_amount > 0.8
        if closed and not was_closed:
            blinks += 1
        was_closed = closed
    assert 3 <= blinks <= 16  # every few seconds
    assert peak[Ch.ROOT_Z] < 0.06 and peak[Ch.ROOT_X] < 0.06 and peak[Ch.BODY_R] < 4.0


def test_reduced_motion_lowers_velocity_limits() -> None:
    anim = AnimationController(reduced_motion=True)
    assert anim.springs.max_velocity[Ch.BODY_R] < mp.SPECS[Ch.BODY_R].max_vel
    assert anim.springs.max_velocity[Ch.EYE_OPEN] == mp.SPECS[Ch.EYE_OPEN].max_vel
