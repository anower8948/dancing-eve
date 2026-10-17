# Changelog

## 0.2.0 — 2026-10-17 (unreleased)

### Added
- "Dreamers" dance style (inspired by the FIFA World Cup Qatar 2022 anthem): 7 original
  moves — anthem_march, sky_point, heart_hand, dream_reach, flag_wave, stadium_wave and a
  victory_jump flourish — plus a signature routine; Settings → Dance style or `--style`.
- 14 new dance moves (27 total), including a second flourish.
- Call-and-response phrases (a move, its mirror, a contrast, a return).
- Wide-eyed surprise on musical drops; sleepy mode after a long silence; bolder happy eyes.

### Changed
- Raised-arm poses go out and up to the side so they read from the front.
- Companion window is square and slightly wider in view; default size 280 px.
- Lower CPU: ≈10 % idle (was ≈19 %), 15 FPS when sleepy, single-pass painting.

- Windows/Linux compatibility: renderer fallback chain (GPU OpenGL → headless EGL on
  Linux → software), simplified shading without GLSL, Ubuntu setup offers missing apt
  packages, Windows long-path warning, more Ubuntu terminals, Linux packaging check,
  fallback display modules bundled in builds.
- Ubuntu 24.04 container test harness (`tests/platform/`) and a GitHub Actions workflow
  for Windows and Ubuntu.

### Fixed
- Windows system-audio capture was unavailable (COM initialised before SoundCard import).
- Renderer could accept a blank "parasite" buffer; every attempt is now validated.
- Dance clock can no longer stall or run backwards on inconsistent beat-phase input.
- Phrases could repeat long-cooldown moves (spins) back to back.

## 0.1.0 — 2026-10-17 (first release, macOS verified)

### Added
- One-click launchers (`run.command`, `run.bat`, `run-ubuntu.sh`) with stdlib-only
  first-time setup: Python discovery/optional install, project venv, exact pins,
  genuine progress, validation, audio check, network-failure recovery, setup lock.
- System-audio capture: ScreenCaptureKit (macOS, verified), WASAPI loopback (Windows),
  PulseAudio/PipeWire monitors (Linux), virtual loopback devices (macOS fallback);
  honest capture statuses with retries; no microphone fallback.
- Real-time analysis: bands, spectral flux, onsets, tempo with conservative confidence,
  phase-locked beats, silence, surges; volume-independent normalisation.
- Procedural 3D robot with custom GLSL shading, rendered offscreen by Panda3D into a
  transparent always-on-top Qt window.
- Layered spring animation (idle life, secondary motion, accents) and a music-aware
  choreography engine (6 states, 13 movements, history/cooldowns, crossfades).
- Tray/menu-bar control, settings window, debug panel, demo mode, diagnostics,
  smoke-test performance report, single instance, versioned settings with migrations.
- 138 automated tests; docs; PyInstaller build scripts (macOS build verified).
