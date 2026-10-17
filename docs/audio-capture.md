# System-audio capture

EVE listens to what the computer **plays** (music apps, browsers, games…). It never uses
a microphone, and there is no silent microphone fallback: if system-audio capture is not
possible, the status says so and explains what to do.

| Platform | Mechanism | Module | Status |
|---|---|---|---|
| macOS 13+ | ScreenCaptureKit audio stream (PyObjC) | `eve/audio/platforms/macos_capture.py` | **Verified** on macOS 27.0 / M2 |
| macOS (fallback) | Virtual loopback device (BlackHole, Loopback…) via SoundCard | `virtual_device.py` | Implemented, not verified (no virtual device installed) |
| Windows 10/11 | WASAPI loopback of output endpoints via SoundCard | `windows_capture.py` | **Verified in CI** (virtual sound card) |
| Ubuntu (PipeWire / PulseAudio) | Monitor source of the output sink via SoundCard (libpulse) | `linux_capture.py` | **Verified** in a container and CI (PulseAudio) |

## Status values

| Status | Meaning |
|---|---|
| `STOPPED` | Not listening. |
| `WAITING_FOR_PERMISSION` | Asking the OS for content/permission (macOS). |
| `CONNECTING` | Stream starting, or started but no data verified yet. |
| `RECEIVING_AUDIO` | Samples arrive **and** contain signal above −70 dBFS. |
| `NO_AUDIO_DETECTED` | Stream open but either no sample data for 3 s, or only digital silence for 4 s (message says which). |
| `PERMISSION_DENIED` | The OS refused; instructions shown, Retry button, no automatic retry. |
| `DEVICE_UNAVAILABLE` | No capturable output / device vanished; automatic retry with backoff. |
| `UNSUPPORTED` | No backend exists or loads on this system. |
| `ERROR` | Anything else; automatic retry with backoff (2, 5, 10, 20, 30 s). |

"Receiving" is decided by the `CaptureManager` from the samples themselves, never from an
API call returning successfully.

## macOS — ScreenCaptureKit

* Needs macOS 13 or newer and the **Screen & System Audio Recording** permission for the
  app that started EVE: **Terminal** when using `run.command`, or the packaged
  `ProjectEVE.app`.
* First start: macOS shows a permission prompt (or adds the app to the list). Enable it
  in *System Settings → Privacy & Security → Screen & System Audio Recording*, then
  **quit and reopen** that app (macOS only applies the change after a relaunch) and press
  **Retry**. The settings window has an "Open Privacy Settings…" button.
* The stream captures every app's audio regardless of output device and volume slider.
  Format received during verification: 48 kHz, 2 channels, float32, non-interleaved.
* ScreenCaptureKit requires a video track; EVE requests 2×2 pixels at 1 fps and discards
  the frames. No screen content is stored or processed.
* `excludesCurrentProcessAudio` is off (see ADR-003).

### Verification performed (2026-10-16/17, macOS 27.0, Apple M2)

1. A 440 Hz tone (amplitude 0.3) played with `afplay -v 0.15` from another process was
   captured with peak 0.045 — exactly the expected level.
2. `python -m eve --test-capture 12` while a synthetic 120 BPM beat played:
   `WAITING_FOR_PERMISSION → CONNECTING → RECEIVING_AUDIO`, 565 k samples, peak −17 dBFS,
   37 onsets, 16 beats, 0 overruns.
3. A synthetic 100 BPM song (kick, snare, hats, bass, chords) for 16 s: tempo locked at
   100.1 BPM, 22 beats, peak −12.4 dBFS.
4. Three start/stop cycles: each reached `RECEIVING_AUDIO`; zero samples arrived after
   each stop; the stream object was released; no threads left behind.
5. Not verified: the permission-denied path on a machine without the permission (this
   machine already had it). The code path is unit-tested with a fake backend.

### Virtual-device fallback (BlackHole)

For macOS < 13 or if ScreenCaptureKit is unavailable:
1. Install BlackHole 2ch (https://existential.audio/blackhole/).
2. In *Audio MIDI Setup* create a **Multi-Output Device** containing your speakers/
   headphones **and** BlackHole, and select it as the system output.
3. In EVE settings choose the BlackHole source.
Only devices whose names match known loopback drivers are listed.

## Windows — WASAPI loopback

* Captures the mix sent to an output endpoint (the default one unless a specific source
  is chosen). Reopens automatically when the default output device changes (checked every
  2 s). No permission prompt is involved.
* COM is initialised (MTA) in every thread that touches WASAPI — **after** importing
  SoundCard, which initialises COM itself on first import and treats "already
  initialised" (S_FALSE) as fatal. Getting this order wrong made the backend
  "unavailable (Error 0x100000001)"; found and fixed through CI.
* Verified on GitHub's Windows runner with the VB-CABLE virtual device: a 120 BPM beat
  played with `Media.SoundPlayer` was captured through loopback (661 k samples, peak
  −5.2 dBFS, 21 beats, tempo 119.9 BPM, confidence 0.78).
* Known library behaviour: when nothing plays, Windows delivers no packets; SoundCard
  synthesises zeros, so the status becomes "nothing is playing" rather than an error.
* Exclusive-mode apps (some ASIO/pro-audio setups) bypass the shared mix and cannot be
  captured.

## Ubuntu — PulseAudio / PipeWire monitor sources

* Every output sink has a `<sink>.monitor` source. SoundCard (libpulse) lists them; the
  default sink's monitor is chosen automatically and re-chosen if the default changes.
* PipeWire: works through `pipewire-pulse` (default on Ubuntu 22.10+). Pure ALSA without
  a sound server has no monitor sources → `DEVICE_UNAVAILABLE`/`UNSUPPORTED`.
* Requires `libpulse0` (installed on desktop Ubuntu). Flatpak/snap sandboxes may hide
  monitors.
* Discovery uses only the library (no shell commands).

## Diagnostics

```bash
.venv/bin/python -m eve --diagnose-audio          # backends, sources, permission (no prompt)
.venv/bin/python -m eve --test-capture 10         # capture 10 s of real audio and report
.venv/bin/python scripts/verify_environment.py --capture 10
```
(run with `PYTHONPATH=src`, or use `scripts/run_dev.py`).

## Analysis pipeline (summary)

Hop ≈ 10.7 ms (512 samples at 44.1/48 kHz), Hann window 4× hop. Per hop: RMS/dBFS;
band amplitudes (20–150 Hz, 150–2000 Hz, 2–10 kHz); log-compressed spectral flux
(broadband and bass); onset detection (median + k·MAD adaptive threshold, local maximum,
100 ms refractory); tempo by unbiased autocorrelation of the onset envelope (8 s window,
60–190 BPM, log-normal prior around 115 BPM, harmonic enhancement, octave hysteresis);
beat grid locked by comb alignment and corrected by onsets (PLL), re-checked every 2 s;
silence with hysteresis (−60/−52 dBFS, 0.8 s hold); surge = short/long loudness ratio
> 1.7 after ≥ 4 s of music. Each feature is normalised by its own adaptive peak follower,
so system volume changes do not change the dance (tested: −26 dB gives the same
normalised energy within 25 %). Cost ≈ 0.45 ms per hop on an M2 (~4 % of one core).
