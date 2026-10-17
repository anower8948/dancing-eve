from __future__ import annotations

import pytest

from eve.audio.normalization import AdaptiveNormalizer, ExpSmoother, PeakFollower, db


def test_peak_follower_attacks_instantly_and_decays_to_floor() -> None:
    p = PeakFollower(release=1.0, floor=0.1)
    assert p.update(1.0, 0.01) == pytest.approx(1.0)
    for _ in range(1000):
        p.update(0.0, 0.01)
    assert p.value == pytest.approx(0.1, abs=1e-3)


def test_adaptive_normalizer_output_range_and_gain_independence() -> None:
    a, b = AdaptiveNormalizer(release=5.0, floor=1e-6), AdaptiveNormalizer(release=5.0, floor=1e-6)
    out_a = out_b = 0.0
    for i in range(500):
        x = 0.5 + 0.5 * ((i % 50) / 50)
        out_a = a.update(x, 0.01)
        out_b = b.update(x * 0.01, 0.01)
    assert 0.0 <= out_a <= 1.0
    assert out_a == pytest.approx(out_b, rel=1e-6)


def test_normalizer_floor_prevents_noise_amplification() -> None:
    n = AdaptiveNormalizer(release=1.0, floor=1e-3)
    for _ in range(200):
        value = n.update(1e-6, 0.01)
    assert value < 0.01


def test_exp_smoother_asymmetric_and_dt_independent() -> None:
    fast = ExpSmoother(attack=0.1, release=1.0)
    coarse = ExpSmoother(attack=0.1, release=1.0)
    for _ in range(100):
        fast.update(1.0, 0.001)
    for _ in range(10):
        coarse.update(1.0, 0.01)
    assert fast.value == pytest.approx(coarse.value, rel=1e-6)
    up = fast.value
    fast.update(0.0, 0.1)
    assert up - fast.value < 0.1 * up  # slow release


def test_db() -> None:
    assert db(1.0) == pytest.approx(0.0)
    assert db(0.1) == pytest.approx(-20.0)
    assert db(0.0) == pytest.approx(-240.0)
