"""Audio capture diagnostics (``python -m eve --diagnose-audio`` / ``--test-capture N``).

``diagnose()`` never starts a stream and never triggers a permission prompt.
``capture_test()`` really captures for N seconds and reports what arrived — this is the
honest check that system-audio capture works on a machine.
"""

from __future__ import annotations

import sys
import time
from typing import Any

import numpy as np

from eve.audio.analyzer import AnalyzerWorker
from eve.audio.audio_features import PulseKind
from eve.audio.capture_manager import CaptureManager
from eve.audio.capture_status import CaptureStatus
from eve.audio.sample_buffer import SampleBuffer


def diagnose() -> dict[str, Any]:
    from eve.audio.platforms import default_backend_classes

    report: dict[str, Any] = {"platform": sys.platform, "backends": [], "sources": []}
    try:
        classes = default_backend_classes()
    except Exception as exc:
        report.update(ok=False, summary=f"capture backends failed to import: {exc}")
        return report
    manager = CaptureManager(SampleBuffer(), classes)
    for cls in classes:
        available = cls.key not in manager.unavailable_reasons
        report["backends"].append(
            {
                "key": cls.key,
                "name": cls.display_name,
                "available": available,
                "reason": manager.unavailable_reasons.get(cls.key, ""),
            }
        )
    sources = manager.get_supported_sources()
    report["sources"] = [{"id": s.id, "name": s.name, "kind": s.kind.value, "default": s.is_default} for s in sources]
    if sys.platform == "darwin":
        from eve.audio.platforms.macos_capture import screen_capture_preflight

        granted = screen_capture_preflight()
        report["screen_recording_permission"] = granted
    manager.dispose()
    if not sources:
        report.update(ok=False, summary="no system-audio source available")
    elif sys.platform == "darwin" and report.get("screen_recording_permission") is False:
        report.update(ok=True, summary="ScreenCaptureKit available; permission will be requested on first use")
    else:
        default = next((s for s in sources if s.is_default), sources[0])
        report.update(ok=True, summary=f"{len(sources)} source(s); default: {default.name}")
    return report


def capture_test(seconds: float = 5.0, source_id: str | None = None) -> dict[str, Any]:
    """Capture real system audio for ``seconds`` and summarise what was received."""
    buffer = SampleBuffer()
    manager = CaptureManager(buffer)
    worker = AnalyzerWorker(buffer)
    worker.start()
    statuses: list[str] = []
    peak = 0.0
    onsets = beats = 0
    max_activity = 0.0
    manager.start(source_id)
    started = time.monotonic()
    try:
        while time.monotonic() - started < seconds:
            _pump_runloop(0.1)
            info = manager.poll(0.1)
            label = f"{info.status.name}: {info.message}" if info.message else info.status.name
            if not statuses or statuses[-1] != label:
                statuses.append(label)
            peak = max(peak, manager.peak)
            for event in worker.drain_events():
                if event.kind == PulseKind.ONSET:
                    onsets += 1
                elif event.kind == PulseKind.BEAT:
                    beats += 1
            features, _ = worker.latest()
            max_activity = max(max_activity, features.music_activity)
        final = manager.poll(0.1)
        features, _ = worker.latest()
    finally:
        manager.dispose()
        worker.stop()
    level_db = 20 * np.log10(max(peak, 1e-12))
    return {
        "seconds": seconds,
        "final_status": final.status.name,
        "status_history": statuses,
        "samples_received": manager.samples_received,
        "sample_rate": buffer.sample_rate,
        "peak_dbfs": round(float(level_db), 1),
        "onsets": onsets,
        "beats": beats,
        "tempo_bpm": round(features.tempo_bpm, 1),
        "tempo_confidence": round(features.tempo_confidence, 2),
        "max_music_activity": round(max_activity, 2),
        "buffer_overruns": buffer.overruns,
        "real_audio_received": final.status == CaptureStatus.RECEIVING_AUDIO,
    }


def _pump_runloop(seconds: float) -> None:
    """On macOS, let Cocoa deliver callbacks while we wait (no Qt loop in CLI mode)."""
    if sys.platform == "darwin":
        try:
            from Foundation import NSDate, NSRunLoop

            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
            return
        except Exception:
            pass
    time.sleep(seconds)
