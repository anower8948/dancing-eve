# Architecture decision records

Each record: decision · context · alternatives · reason · trade-offs · revisit when.

---

## ADR-001 — Python 3.12 with a supported range of 3.11–3.13

* **Context:** every dependency must have wheels for the target OSes (no compilers on
  user machines). Homebrew's default `python3` on the dev machine is 3.14.
* **Alternatives:** 3.14 (newest; wheel coverage for Panda3D/PySide6 not verified), 3.10
  (Ubuntu 22.04 default; too old for our typing and NumPy 2.5).
* **Reason:** 3.12 had verified wheels for every pinned package on macOS arm64 at the
  time of writing; 3.11 and 3.13 are accepted because the same pins publish wheels for them.
* **Trade-offs:** Ubuntu 22.04 users need `python3.11` from the archive (the launcher
  offers it).
* **Revisit:** when Panda3D/PySide6 publish verified 3.14 wheels.

## ADR-002 — Panda3D renders offscreen; Qt owns the window

* **Context:** the robot must float in a transparent, frameless, always-on-top, draggable,
  optionally click-through window on macOS, Windows, X11 and Wayland/XWayland.
* **Alternatives:** (a) embed Panda3D's native GL window into a Qt widget via window
  handles — fragile on macOS (Cocoa layering) and Wayland, and Panda3D cannot give a
  transparent native window portably; (b) Panda3D's own window with platform hacks for
  transparency; (c) a different engine (moderngl/pyrender inside QOpenGLWidget).
* **Reason:** verified on this machine that Panda3D creates an offscreen GL buffer with
  an alpha channel inside a running Qt application, without ShowBase, and that RAM
  readback costs ~0.5 ms at 320×400 in a tight loop. Qt then handles transparency and
  all window behaviour with its well-tested cross-platform code paths.
* **Trade-offs:** one synchronous GPU→CPU copy per frame (measured ~2–3 ms in the live app
  on an M2 because of GPU idle latency); CPU ~19–23 % of one core at 24–60 FPS.
* **Revisit:** if CPU use matters more — async PBO readback, or a QOpenGLWidget-based
  renderer that shares the GL context.

## ADR-003 — macOS capture through ScreenCaptureKit via PyObjC

* **Context:** macOS has no built-in loopback device. Options: ScreenCaptureKit audio
  (macOS 13+), Core Audio process taps (macOS 14.2+), virtual drivers (BlackHole).
* **Alternatives:** Core Audio taps need an aggregate device and an IOProc callback, which
  PyObjC's CoreAudio bindings do not expose ergonomically; BlackHole requires the user to
  install a kernel-less driver and reroute output.
* **Reason:** ScreenCaptureKit works from Python with PyObjC, needs no driver, and was
  verified: a tone played by another process was received at the expected level
  (peak 0.045 for a 0.3-amplitude tone at 15 % player volume), 48 kHz float32
  non-interleaved stereo.
* **Trade-offs:** requires the "Screen & System Audio Recording" permission for the app
  that launched EVE (Terminal for `run.command`); the stream must include a (2×2 px,
  1 fps) video track that we ignore. `excludesCurrentProcessAudio` is **off**: it
  silenced all audio started from the same responsible app during verification.
* **Revisit:** if Apple deprecates SCK audio or PyObjC adds clean process-tap support
  (taps can request audio-only permission).

## ADR-004 — SoundCard for Windows (WASAPI loopback) and Linux (Pulse monitors)

* **Context:** need loopback on Windows and monitor sources on PulseAudio/PipeWire.
* **Alternatives:** PyAudioWPatch (Windows only), sounddevice (no loopback on Windows
  WASAPI without patches), parsing `pactl` + `parec` subprocesses.
* **Reason:** one maintained, pure-Python (cffi) library covering both; NumPy-2 safe
  (`frombuffer`); returns zeros when Windows delivers no packets during silence.
* **Trade-offs:** COM must be initialised per thread on Windows (done explicitly);
  **not yet verified on real Windows/Ubuntu hardware**.
* **Revisit:** after real-hardware testing.

## ADR-005 — No microphone fallback, ever

Capture failures surface as explicit statuses with instructions. Virtual-device mode only
lists devices whose names identify loopback drivers. Optional microphone input is a
roadmap item that must be an explicit, labelled user choice.

## ADR-006 — NumPy-only analysis (no SciPy/librosa/Essentia)

* **Reason:** the needed DSP (windowed FFT, flux, ACF tempo, comb phase alignment) is a
  few hundred lines of NumPy; runs at ~0.45 ms per 10.7 ms hop. Avoids ~100 MB of
  dependencies.
* **Revisit:** for genre/mood classification or downbeat tracking (see future-ai-features).

## ADR-007 — Tempo confidence must be earned

Confidence is a z-score of the autocorrelation peak against the ACF's own spread, gated
by envelope variance and multiplied by a stability factor. Measured separation: clear
beats z ≥ 3.0, white noise z ≤ 1.7, steady tone rejected by the variance gate. Beats are
emitted only above confidence 0.3; otherwise the dance uses its free clock and
onset-driven accents.

## ADR-008 — Animation = intent curves + damped springs

* **Decision:** movements are pure functions of beat time producing *target offsets*;
  per-channel damped springs (different frequency/damping per body part) produce all
  inertia, overshoot, lag and follow-through; beats act as velocity impulses.
* **Alternatives:** keyframed clips (repetitive, needs authoring tools), direct
  audio→pose mapping (looks like a visualizer).
* **Reason:** frame-rate independent, always continuous, easy to blend, cheap
  (0.07 ms/frame for dance + animation).

## ADR-009 — First-time setup is standard-library Python + thin shell launchers

* **Decision:** launchers only find *some* Python ≥ 3.8 and call `setup/bootstrap.py`,
  which selects a supported interpreter, creates `.venv`, installs exact pins with
  per-package progress, validates versions and imports, then launches.
* **Reason:** one implementation for three OSes; testable with pytest; no privileged
  commands except an explicitly confirmed Python install.
* **Trade-offs:** terminal progress UI rather than a GUI (tkinter is not guaranteed to be
  present — Homebrew ships it separately).
* **Revisit:** a Tk/Qt setup window once Python is guaranteed to have tkinter.

## ADR-010 — Exact pins without hashes

All runtime packages (including transitive) are pinned in `requirements.txt` with
platform markers. Hash pinning was deferred because generating multi-platform hashes
needs per-platform resolution. Revisit with `pip-compile --generate-hashes` per OS or `uv`.

## ADR-011 — PyInstaller for packaging, one build per OS

Packaging is optional; development mode works without it. See [packaging.md](packaging.md).
