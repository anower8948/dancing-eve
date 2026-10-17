"""Streaming music analysis.

``AudioAnalyzer`` is pure and deterministic: feed it hop-sized blocks of mono samples and
it returns one ``AudioFeatures`` frame plus any pulse events. ``AnalyzerWorker`` runs it on
a dedicated thread, pulling from the bounded ``SampleBuffer`` so analysis never blocks
rendering, and publishes the latest frame + a bounded event queue.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

import numpy as np

from eve.audio.audio_features import SILENT_FEATURES, AudioFeatures, PulseEvent, PulseKind
from eve.audio.beat_detector import BeatTracker, OnsetDetector
from eve.audio.normalization import AdaptiveNormalizer, ExpSmoother, db
from eve.audio.sample_buffer import SampleBuffer
from eve.audio.silence_detector import SilenceDetector
from eve.audio.spectrum import SpectrumAnalyzer, hop_and_fft_size
from eve.audio.tempo_estimator import TempoEstimator

log = logging.getLogger(__name__)

ONSET_RATE_WINDOW = 4.0  # seconds
SURGE_RATIO = 1.7
SURGE_COOLDOWN = 4.0
SILENCE_RESET_SECONDS = 2.5
SURGE_MIN_MUSIC_SECONDS = 4.0  # music must already be playing (a song start is not a surge)


class AudioAnalyzer:
    def __init__(self, sample_rate: int = 48000, sensitivity: float = 1.0) -> None:
        self.sensitivity = sensitivity
        self.configure(sample_rate)

    # -- setup ---------------------------------------------------------------------------
    def configure(self, sample_rate: int) -> None:
        self.sample_rate = int(sample_rate)
        self.hop, self.fft_size = hop_and_fft_size(self.sample_rate)
        self.dt = self.hop / self.sample_rate
        self.fps = 1.0 / self.dt
        self._window = np.zeros(self.fft_size, dtype=np.float32)
        self.spectrum = SpectrumAnalyzer(self.sample_rate, self.fft_size)
        self.onsets = OnsetDetector(self.fps)
        self.tempo = TempoEstimator(self.fps)
        self.beats = BeatTracker()
        self.silence = SilenceDetector()
        self._energy_norm = AdaptiveNormalizer(release=10.0, floor=10 ** (-50 / 20))
        self._low_norm = AdaptiveNormalizer(release=12.0, floor=1e-4)
        self._mid_norm = AdaptiveNormalizer(release=12.0, floor=1e-4)
        self._high_norm = AdaptiveNormalizer(release=12.0, floor=5e-5)
        self._flux_norm = AdaptiveNormalizer(release=6.0, floor=0.004)
        self._odf_norm = AdaptiveNormalizer(release=6.0, floor=0.006)
        self._bass_norm = AdaptiveNormalizer(release=6.0, floor=0.004)
        self._energy_smooth = ExpSmoother(0.03, 0.18)
        self._flux_smooth = ExpSmoother(0.4, 1.2)
        self._intensity = ExpSmoother(0.6, 1.8)
        self._activity = ExpSmoother(0.25, 1.0)
        self._short_level = ExpSmoother(0.25, 0.25)
        self._long_level = 0.0  # running mean, then 6 s exponential (see process_hop)
        self._onset_times: deque[float] = deque(maxlen=256)
        self._last_surge = -1e9
        self._silent_for = 0.0
        self._playing_for = 0.0
        self.t = 0.0
        self.frames = 0

    def set_sensitivity(self, sensitivity: float) -> None:
        self.sensitivity = float(np.clip(sensitivity, 0.1, 4.0))
        self.onsets.threshold_k = 1.6 / max(0.4, self.sensitivity) ** 0.5

    # -- processing ----------------------------------------------------------------------
    def process_hop(self, hop_samples: np.ndarray) -> tuple[AudioFeatures, list[PulseEvent]]:
        n = self.hop
        if hop_samples.shape[0] != n:
            raise ValueError(f"expected {n} samples, got {hop_samples.shape[0]}")
        w = self._window
        w[:-n] = w[n:]
        w[-n:] = hop_samples
        dt = self.dt
        self.t += dt
        self.frames += 1
        t = self.t
        events: list[PulseEvent] = []

        frame = self.spectrum.process(w)
        level_db = db(frame.rms)
        silent = self.silence.update(level_db, dt)
        activity = self._activity.update(0.0 if silent else 1.0, dt)

        energy = self._energy_smooth.update(self._energy_norm.update(frame.rms, dt, self.sensitivity), dt)
        low = self._low_norm.update(frame.low, dt)
        mid = self._mid_norm.update(frame.mid, dt)
        high = self._high_norm.update(frame.high, dt)
        flux_n = self._flux_norm.update(frame.flux, dt)
        bass_pulse = self._bass_norm.update(frame.low_flux, dt)

        # Onset detection function: broadband flux with extra weight on the bass band.
        odf = frame.flux + 0.6 * frame.low_flux
        odf_n = self._odf_norm.update(odf, dt)
        onset = None if silent else self.onsets.update(odf, t, dt)
        if silent:
            self.onsets.update(0.0, t, dt)  # keep history moving so thresholds re-adapt
        onset_time = t - dt
        if onset is not None:
            self._onset_times.append(onset_time)
            events.append(PulseEvent(PulseKind.ONSET, onset_time, onset, bass_pulse))
        while self._onset_times and self._onset_times[0] < t - ONSET_RATE_WINDOW:
            self._onset_times.popleft()
        onset_rate = len(self._onset_times) / ONSET_RATE_WINDOW

        # Tempo and beats (only meaningful while music is playing).
        self._playing_for = 0.0 if silent else self._playing_for + dt
        if silent:
            self._silent_for += dt
            if self._silent_for > SILENCE_RESET_SECONDS and self.tempo.current.bpm > 0:
                self.tempo.reset()
                self.beats.reset()
        else:
            self._silent_for = 0.0
        self.tempo.push(0.0 if silent else odf_n, dt)
        estimate = self.tempo.current
        beat = None
        if silent:
            self.beats.reset()  # never flywheel beats through silence
        else:
            offset = None
            if estimate.confidence >= self.beats.min_confidence and self.beats.realign_due:
                offset = self.tempo.beat_offset(estimate.period)
            beat = self.beats.update(
                t, estimate, onset, onset_time if onset is not None else None, bass_pulse, offset, dt
            )
        if beat is not None:
            events.append(beat)

        flux_s = self._flux_smooth.update(flux_n, dt)
        drive = 0.55 * min(onset_rate / 4.0, 1.0) + 0.45 * flux_s
        intensity = self._intensity.update(0.0 if silent else drive, dt)

        short = self._short_level.update(frame.rms, dt)
        if not silent:
            # Expanding mean for the first seconds of a song, then a 6 s exponential average,
            # so the reference is meaningful as soon as surges are allowed.
            tau = min(6.0, max(self._playing_for, dt))
            self._long_level += (frame.rms - self._long_level) * min(1.0, dt / tau)
        change = short / max(self._long_level, 1e-6)
        if (
            not silent
            and change > SURGE_RATIO
            and energy > 0.5
            and activity > 0.8
            and self._playing_for > SURGE_MIN_MUSIC_SECONDS
            and t - self._last_surge > SURGE_COOLDOWN
        ):
            self._last_surge = t
            events.append(PulseEvent(PulseKind.SURGE, t, float(min(1.0, change / 3.0)), bass_pulse))

        tempo_ok = estimate.confidence >= self.beats.min_confidence and self.beats.locked
        features = AudioFeatures(
            time=t,
            sample_rate=self.sample_rate,
            rms=frame.rms,
            level_db=level_db,
            energy=0.0 if silent else energy,
            low=low,
            mid=mid,
            high=high,
            flux=flux_n,
            onset_strength=odf_n,
            bass_pulse=bass_pulse,
            onset_rate=onset_rate,
            intensity=intensity,
            tempo_bpm=estimate.bpm if tempo_ok else 0.0,
            tempo_confidence=estimate.confidence,
            beat_phase=self.beats.phase(t) if tempo_ok else 0.0,
            beat_period=self.beats.period if tempo_ok else 0.0,
            music_activity=activity,
            is_silent=silent,
            energy_change=change,
        )
        return features, events

    def process_block(self, samples: np.ndarray) -> tuple[list[AudioFeatures], list[PulseEvent]]:
        """Convenience for tests/offline use: process any whole number of hops."""
        frames: list[AudioFeatures] = []
        events: list[PulseEvent] = []
        for start in range(0, samples.shape[0] - self.hop + 1, self.hop):
            f, e = self.process_hop(samples[start : start + self.hop])
            frames.append(f)
            events.extend(e)
        return frames, events


class AnalyzerWorker:
    """Runs AudioAnalyzer on its own thread. Thread-safe accessors for the UI/main loop."""

    def __init__(self, buffer: SampleBuffer, sensitivity: float = 1.0, max_events: int = 128) -> None:
        self.buffer = buffer
        self._sensitivity = sensitivity
        self._events: deque[PulseEvent] = deque(maxlen=max_events)
        self._latest: AudioFeatures = SILENT_FEATURES
        self._latest_wall = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.hops_processed = 0
        self.avg_process_ms = 0.0
        self.analyzer: AudioAnalyzer | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="eve-analyzer", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        self.buffer.wake()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive():
                log.warning("analyzer thread did not stop within %.1fs", timeout)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def set_sensitivity(self, value: float) -> None:
        self._sensitivity = value
        if self.analyzer is not None:
            self.analyzer.set_sensitivity(value)

    def latest(self) -> tuple[AudioFeatures, float]:
        """(features, monotonic time when they were published)."""
        return self._latest, self._latest_wall

    def drain_events(self) -> list[PulseEvent]:
        out = []
        while True:
            try:
                out.append(self._events.popleft())
            except IndexError:
                return out

    def _run(self) -> None:
        generation = -1
        hop_buf = np.zeros(1, dtype=np.float32)
        analyzer: AudioAnalyzer | None = None
        try:
            while not self._stop.is_set():
                if self.buffer.generation != generation or analyzer is None:
                    generation = self.buffer.generation
                    analyzer = AudioAnalyzer(self.buffer.sample_rate, self._sensitivity)
                    analyzer.set_sensitivity(self._sensitivity)
                    self.analyzer = analyzer
                    hop_buf = np.zeros(analyzer.hop, dtype=np.float32)
                    log.debug(
                        "analyzer configured: %d Hz, hop %d, fft %d",
                        analyzer.sample_rate,
                        analyzer.hop,
                        analyzer.fft_size,
                    )
                if not self.buffer.read_into(hop_buf, timeout=0.2):
                    continue
                if self.buffer.generation != generation:
                    continue
                started = time.perf_counter()
                features, events = analyzer.process_hop(hop_buf)
                elapsed = (time.perf_counter() - started) * 1000.0
                self.avg_process_ms += (elapsed - self.avg_process_ms) * 0.01
                self._latest = features
                self._latest_wall = time.monotonic()
                self._events.extend(events)
                self.hops_processed += 1
        except Exception:
            log.exception("analyzer worker crashed")
