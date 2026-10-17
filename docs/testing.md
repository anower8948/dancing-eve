# Testing

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/run_dev.py check      # ruff check + ruff format --check + mypy + pytest
.venv/bin/pytest -o addopts="" -q              # tests only
EVE_SKIP_GUI_TESTS=1 .venv/bin/pytest -q       # headless machines (skips gui/render tests)
```

Latest result (macOS 27.0, M2, Python 3.12.13, 2026-10-17): **138 passed**, ruff clean,
mypy clean (75 files).

## What is covered

| Area | Tests |
|---|---|
| RMS, band energies, flux, hop sizes, silence hysteresis, volume independence, sample-rate changes, abrupt volume changes | `unit/test_audio_features.py` |
| Peak follower, adaptive normaliser, smoothers | `unit/test_normalization.py` |
| Onset cooldowns, tempo accuracy (90–140 BPM within 3 %), beat phase (< 40 ms), low confidence and no beats on noise / steady tone, beats stop after music, surges | `unit/test_beat_detector.py` |
| Sample buffer bounds/overruns/order/wrap-around, mono & format conversion | `unit/test_audio_features.py` |
| Capture status honesty (no data vs silence vs signal), retries/backoff, no auto-retry on permission denial, UNSUPPORTED (never microphone), cleanup, callback isolation | `unit/test_capture_manager.py` (fake backend) |
| Dance states & hysteresis, gradual return to idle, stale features, low-confidence fallback, phase lock, accents, single flourish, variety & no repeats, cooldowns, reduced motion, every movement finite, manual moves, full demo-song pipeline smoothness | `unit/test_dance_controller.py` |
| Springs (convergence, overshoot, frame-rate independence, velocity limits, angle wrap), easing, limits, idle blink/subtlety | `unit/test_motion_smoothing.py` |
| Settings validation, atomic save, corrupt-file recovery, newer-version protection, migration, reset backup | `unit/test_settings.py` |
| OS/distro/session detection, storage paths for all OSes, Wayland→XWayland choice | `unit/test_platform_detection.py` |
| Setup progress (never fake, never backwards), requirement parsing/markers, pins, fingerprints, Python range, network-error detection | `unit/test_setup_progress.py` |
| Mesh validity, outward normals, proportions, eye frame handedness, eye mapping | `unit/test_character_geometry.py` |
| Threaded capture→buffer→analyzer pipeline and clean thread shutdown | `integration/test_audio_pipeline.py` |
| Setup orchestration: first run, reuse, network retry, persistent failure keeps work, setup lock | `integration/test_setup_manager.py` |
| Real app start (Qt + Panda3D) and clean exit, settings outside the repo, single instance | `integration/test_application_lifecycle.py` (marked `gui`/`render`) |

Synthetic audio (`tests/fixtures/synthetic_audio.py`) tests the **analysis only**. It does
not test operating-system capture.

## Real system-audio tests (manual, per platform)

```bash
PYTHONPATH=src .venv/bin/python -m eve --test-capture 15   # play music while it runs
```
Expect `final_status: RECEIVING_AUDIO`, a non-trivial `peak_dbfs`, onsets, and for music
with a clear beat a tempo with confidence. Then the manual checklist:

1. Start EVE with the launcher. 2. Play music in another app. 3. Status shows
"Listening" (green dot on the robot). 4. Activity meter moves. 5. Robot dances.
6. Pause → robot settles to idle within ~3–5 s. 7. Change track → different moves.
8. Revoke the permission (macOS) / disable the device. 9. A clear message appears.
10. Retry after fixing. 11. Stop/Start listening. 12. Quit → capture indicator gone,
`--diagnose-audio` works again.

Status on macOS 27: 1–5 and 11 verified via `--test-capture`, `--smoke-test` and debug
screenshots; 6–7 verified in simulation (demo song / unit tests) not by watching a real
track; 8–10 not verified (permission already granted); 12 verified (start/stop cycles
release the stream). Windows and Ubuntu: none run yet.

## Performance measurement

`python -m eve --smoke-test 20 [--demo|--no-audio] [--screenshot frame.png]` prints FPS,
frame/render percentiles, process CPU %, max RSS, capture status history and overruns.
