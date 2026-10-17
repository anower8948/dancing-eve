# Implementation log

## 2026-10-17 — Session 4 ("Dreamers" style)

* 7 original moves inspired by the Qatar 2022 anthem's stadium feel (no access to the
  performance video; not a copy of its choreography). Arm spread lower limit −4° → −40°
  so an arm can cross the chest (hand on heart); pose sheet confirmed it reads.
* Dance-style system: `Movement.style`, `DanceSettings.style`, Choreographer weighting
  (×5 style / ×0.5 others) and signature routines; `dance_style` setting (validated
  choices), Settings combo, `--style` per-run flag; debug log line per chosen move.
* Pose-sheet review: bell envelopes never let the springs reach raised-arm targets →
  `hold()` plateau envelopes; march arms swung toward the viewer (invisible) → added
  outward lift and side step. Manually played moves fade in 3× faster (previews from
  idle showed half-size gestures).
* Found in a 60 s style run: a phrase pattern could play one move three times in a row →
  pattern "AaB" replaced by "BA", plus a test. mypy caught the settings combo named
  `self.style`, which shadowed `QWidget.style()`.
* 172 tests pass; ruff + mypy clean.

## 2026-10-17 — Session 3 (Windows/Linux compatibility)

* Docker (OrbStack) available → `tests/platform/ubuntu.Dockerfile` +
  `run_linux_tests.sh`. Ubuntu 24.04 arm64: run-ubuntu.sh setup 26 s, reuse works,
  159 tests pass (incl. Qt/Panda3D on Xvfb + Mesa llvmpipe), PulseAudio monitor capture
  119.9 BPM / conf 0.79, app 57 FPS (llvmpipe, no MSAA → retried without).
* Renderer fallback chain: default GL → p3headlessgl (Linux) → p3tinydisplay; GL without
  GLSL → fixed-function "simplified shading" (no halos/shadow). Verified: headless EGL with
  no DISPLAY, forced software renderer (macOS and Linux).
* PyInstaller on Ubuntu needed `libpython3.12` (system Python); build script now checks
  the runtime soname first (first version of the check looked for the dev symlink and
  wrongly refused). Linux build: 233 MB, runs with GL and with the software renderer.
  Fallback display modules are now bundled on every OS.
* Setup: offers `sudo apt-get install` for missing Qt/GL/Pulse libraries (asks first);
  Windows long-path warning; run-ubuntu.sh knows Ptyxis and GNOME Console; SoundCard
  "data discontinuity" warnings filtered.
* `.github/workflows/platforms.yml`: Windows + Ubuntu jobs (setup ×2, tests, diagnostics,
  smoke test + screenshot, PyInstaller build + run).
* CI run 1 (green) exposed in its logs that WASAPI was "unavailable: Error 0x100000001":
  SoundCard initialises COM on import and treats S_FALSE as fatal; we had called
  CoInitializeEx first. Fixed import order. Added a VB-CABLE virtual sound card
  (LABSN/sound-ci-helpers, pinned SHA) and a real capture step → 119.9 BPM via loopback.
* Added a hidden-host-window GL attempt for drivers needing a window context. CI run 2
  failed: on the GPU-less runner it returned a parasite buffer → blank frames and an app
  that did not exit. Fix: BF_refuse_parasite + every renderer attempt must pass a
  test-frame coverage check (≥ 2 %). CI run 3 green on both OSes.

## 2026-10-17 — Session 2 (macOS 27.0, Apple M2)

* Added 14 moves: side_step, robot_pop, body_wave, headbang, fist_pump, hop_turn,
  lean_back_groove, figure_eight, pendulum_swing, look_around, arm_circles, shimmy,
  dip_and_rise, star_burst (second FLOURISH move).
* Phrase planner in `Choreographer` (AB / ABA / BbA / AaB with mirrored repeats). Found
  that phrases bypassed the 12 s spin cooldown → moves with cooldown ≥ 8 s are not phrased.
* Expressions: wide-eyed surprise on surges (EYE_OPEN range now 0–1.3), sleepy mode after
  45 s without dancing, tapered thicker happy arcs.
* Pose-sheet review showed "arms up" moves using *swing* are foreshortened from the front
  → arm spread limit raised to 165° and raised-arm poses use spread; window made square
  (VIEW_HEIGHT 2.25, aspect 1.0), ROOT_X limit ±0.22 to avoid clipping; default size 280.
* A preview harness fed a frozen beat phase and the dance clock stalled at ~0.46 beat →
  phase correction is now capped at half a frame's advance (clock is monotonic).
* CPU: renderer alone 4.9 % at 24 FPS; app at 60 FPS ≈27 % (render 12, paint 8, rest 7).
  Panda `threading-model Cull/Draw` and MSAA off did not help. Fixes: single-pass paint,
  idle power save no longer disabled by debug mode, 15 FPS when sleepy. Idle steady
  state 19 % → 9.9 %; sleepy 8.7 %.
* 157 tests pass; ruff + mypy clean.

## 2026-10-16/17 — Session 1 (macOS 27.0, Apple M2)

### Phase 1 — environment & feasibility
* Empty project folder. Python: 3.14 default, 3.12/3.11 via Homebrew. Chose 3.12.
* Panda3D offscreen buffer inside a running QApplication: works (RGBA with alpha,
  CocoaGraphicsBuffer, 4× MSAA, ~0.5 ms/frame readback at 320×400) → ADR-002.
* ScreenCaptureKit via PyObjC: buffers arrive. First probe read silence — cause:
  `excludesCurrentProcessAudio=True` excluded `afplay` started from the same responsible
  app. With it off, a 0.3-amplitude tone at 15 % volume arrived at peak 0.045 → ADR-003.
  Also learned: PyObjC completion handlers returning non-None abort the process.
* SoundCard 0.4.6 uses `frombuffer` (NumPy-2 safe) and zero-fills silent WASAPI loopback.

### Phase 2 — setup
* Stdlib-only bootstrap + three launchers. Verified first run and fast repeat run.
* Dropped `platformdirs`: `eve.storage.paths` is stdlib so setup and app share paths.

### Phases 3–4 — character & animation
* NumPy procedural meshes → Panda3D buffers. Bug found visually: eye surface frame was
  left-handed (up recomputed after flipping the normal) → eyes back-face culled; fixed and
  covered by a test. Halos rebuilt on the head surface (flat discs sank into the visor).
* Spring bank + idle + secondary motion; 13 movements; state machine; transitions.
  Simulation: 0.07 ms/frame; fixed flourish chaining twice.

### Phases 5–6 — capture & analysis
* Tempo: fixed octave stickiness locking a wrong first guess; beat phase locked to
  off-beat hats → comb alignment + periodic re-check (re-check timer bug: only advanced
  when an offset was supplied); ACF input smoothing fixed half-tempo at 150 BPM.
* Tests exposed overconfidence: white noise conf 0.39, steady tone "127 BPM" →
  z-score confidence + envelope-variance gate (ADR-007). Song start counted as surge →
  4 s gate + expanding-mean loudness reference.
* CaptureManager kept a stale failure status after a successful retry → now CONNECTING
  until samples are verified.

### Phase 7 — app integration
* Real capture inside the app reached GROOVE from a played beat track. Settings window
  and debug panel verified by rendering to an image. `--size/--fps` were accidentally
  persisted → made per-run only. Start/stop cycles verified to release SCK.

### Phases 8–9 — hardening & release prep
* ruff (line length 120) + mypy clean; 138 tests pass.
* PyInstaller: `--collect-all panda3d` failed (x86_64-only libRocket in the wheel) →
  collect `panda3d.core` + `libpandagl` + prc files, set `plugin-path` when frozen.
  `dist/ProjectEVE.app` (157 MB) renders and captures real audio.

### Unresolved
Windows/Ubuntu untested; macOS permission denial not observed live; CPU 19–23 % of a
core; tempo octave ambiguity on some patterns.
