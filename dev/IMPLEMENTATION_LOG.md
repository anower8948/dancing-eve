# Implementation log

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
