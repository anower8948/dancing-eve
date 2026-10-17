"""RMS, frequency bands, silence and volume independence of the analysis features."""

from __future__ import annotations

import numpy as np
import pytest

from eve.audio.analyzer import AudioAnalyzer
from eve.audio.sample_buffer import SampleBuffer, to_float32, to_mono
from eve.audio.silence_detector import SilenceDetector
from eve.audio.spectrum import SpectrumAnalyzer, hop_and_fft_size
from tests.fixtures import synthetic_audio as sa


def test_rms_of_sine_matches_theory() -> None:
    spectrum = SpectrumAnalyzer(48000, 2048)
    frame = spectrum.process(sa.tone(2048 / 48000, freq=1000.0, amp=0.5))
    assert frame.rms == pytest.approx(0.5 / np.sqrt(2), rel=0.02)


@pytest.mark.parametrize(
    ("freq", "dominant"),
    [(60.0, "low"), (800.0, "mid"), (5000.0, "high")],
)
def test_band_energy_follows_frequency(freq: float, dominant: str) -> None:
    spectrum = SpectrumAnalyzer(48000, 2048)
    frame = spectrum.process(sa.tone(2048 / 48000, freq=freq, amp=0.5))
    bands = {"low": frame.low, "mid": frame.mid, "high": frame.high}
    assert max(bands, key=bands.get) == dominant


def test_flux_is_zero_for_steady_tone_and_positive_for_attack() -> None:
    spectrum = SpectrumAnalyzer(48000, 2048)
    tone = sa.tone(2048 / 48000, freq=440.0, amp=0.3)
    spectrum.process(tone)
    steady = spectrum.process(tone)
    spectrum.reset()
    spectrum.process(np.zeros(2048, dtype=np.float32))
    attack = spectrum.process(tone)
    assert steady.flux == pytest.approx(0.0, abs=1e-4)
    assert attack.flux > 0.02  # mean over all bins; a pure tone excites only a few
    assert attack.flux > 100 * max(steady.flux, 1e-6)


@pytest.mark.parametrize("sr", [22050, 44100, 48000, 96000])
def test_hop_size_adapts_to_sample_rate(sr: int) -> None:
    hop, fft = hop_and_fft_size(sr)
    assert 0.005 < hop / sr < 0.016
    assert fft == hop * 4
    assert hop & (hop - 1) == 0  # power of two


def test_silence_is_detected_with_hysteresis() -> None:
    det = SilenceDetector(enter_db=-60, exit_db=-52, enter_hold=0.5, exit_hold=0.05)
    assert det.update(-30, 0.03) is True  # starts silent; sound must last exit_hold
    assert det.update(-30, 0.03) is False
    assert det.update(-56, 0.3) is False  # inside the band: no flicker
    assert det.update(-70, 0.3) is False
    assert det.update(-70, 0.3) is True


def test_analyzer_reports_silence_then_music_activity() -> None:
    analyzer = AudioAnalyzer(48000)
    frames, _ = analyzer.process_block(sa.silence(2.0))
    assert frames[-1].is_silent and frames[-1].music_activity < 0.05
    frames, _ = analyzer.process_block(sa.beat_track(4.0, bpm=120))
    assert not frames[-1].is_silent
    assert frames[-1].music_activity > 0.9
    frames, _ = analyzer.process_block(sa.silence(4.0))
    assert frames[-1].is_silent
    assert frames[-1].music_activity < 0.1


def test_energy_normalization_is_volume_independent() -> None:
    """The same music at -26 dB (≈ 5% volume) should produce similar normalized features."""
    loud, quiet = AudioAnalyzer(48000), AudioAnalyzer(48000)
    signal = sa.beat_track(10.0, bpm=120, amp=0.8)
    f_loud, _ = loud.process_block(signal)
    f_quiet, _ = quiet.process_block(signal * 0.05)
    tail = slice(len(f_loud) // 2, None)
    mean_loud = np.mean([f.energy for f in f_loud[tail]])
    mean_quiet = np.mean([f.energy for f in f_quiet[tail]])
    assert mean_quiet == pytest.approx(mean_loud, rel=0.25)
    int_loud = f_loud[-1].intensity
    int_quiet = f_quiet[-1].intensity
    assert int_quiet == pytest.approx(int_loud, abs=0.15)


def test_sample_rate_change_is_handled() -> None:
    analyzer = AudioAnalyzer(44100)
    frames, _ = analyzer.process_block(sa.beat_track(3.0, bpm=110, sr=44100))
    assert frames[-1].sample_rate == 44100
    analyzer.configure(48000)
    frames, _ = analyzer.process_block(sa.beat_track(3.0, bpm=110, sr=48000))
    assert frames[-1].sample_rate == 48000
    assert all(np.isfinite(f.energy) for f in frames)


def test_abrupt_volume_change_does_not_break_features() -> None:
    analyzer = AudioAnalyzer(48000)
    frames, _ = analyzer.process_block(sa.energy_step(6.0, 6.0))
    values = np.array([[f.energy, f.low, f.mid, f.high, f.flux, f.intensity] for f in frames])
    assert np.isfinite(values).all()
    assert values.min() >= 0.0 and values.max() <= 1.0


def test_sample_buffer_is_bounded_and_counts_overruns() -> None:
    buf = SampleBuffer(capacity_seconds=0.1, sample_rate=48000)
    for _ in range(10):
        buf.write(np.ones(4800, dtype=np.float32), 48000)
    assert buf.available() <= buf.capacity
    assert buf.overruns > 0
    out = np.zeros(1000, dtype=np.float32)
    assert buf.read_into(out, timeout=0.01)
    assert np.all(out == 1.0)


def test_sample_buffer_preserves_order_across_wraparound() -> None:
    buf = SampleBuffer(capacity_seconds=0.1, sample_rate=48000)  # capacity 4800
    data = np.arange(12000, dtype=np.float32)
    out = np.zeros(1000, dtype=np.float32)
    received = []
    for start in range(0, 12000, 1000):
        buf.write(data[start : start + 1000], 48000)
        assert buf.read_into(out, timeout=0.01)
        received.append(out.copy())
    assert np.array_equal(np.concatenate(received), data)


def test_sample_buffer_resets_on_rate_change_and_times_out() -> None:
    buf = SampleBuffer(sample_rate=48000)
    generation = buf.generation
    buf.write(np.ones(100, dtype=np.float32), 44100)
    assert buf.sample_rate == 44100 and buf.generation == generation + 1
    out = np.zeros(1000, dtype=np.float32)
    assert buf.read_into(out, timeout=0.01) is False


def test_mono_and_format_conversion() -> None:
    stereo = np.stack([np.ones(10), -np.ones(10)], axis=1).astype(np.float32)
    assert np.allclose(to_mono(stereo), 0.0)
    ints = np.array([0, 16384, -32768], dtype=np.int16)
    assert np.allclose(to_float32(ints), [0.0, 0.5, -1.0])
    mono = np.zeros(5, dtype=np.float32)
    assert to_mono(mono) is mono  # no copy for mono float input
