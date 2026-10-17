# Development roadmap

Priority: P1 next · P2 soon · P3 later. Dependencies in brackets.

## P1 — make every platform real
1. **Windows hardware test** — run `run.bat`, `--test-capture`, manual checklist; fix
   WASAPI/COM/threading issues; update the support matrix.
2. **Ubuntu 24.04 test** (GNOME Wayland + X11) — `run-ubuntu.sh` from Files and terminal,
   XWayland path, monitor sources on PipeWire, tray via AppIndicator.
3. **macOS permission-denied walkthrough** on a fresh user account; polish the message.
4. **Manual interaction pass** on macOS: drag, click-poke, double-click, context menu,
   tray menu, click-through on/off, hide/show, multi-monitor DPI change.

## P2 — quality
5. Lower CPU: async readback (PBO) or Qt-shared GL context; render-on-change at idle.
6. Better rhythm: downbeat/bar tracking, tempo octave resolution using spectral
   (kick vs. hat) weighting [P1 tests for real-world baselines].
7. GUI setup window (Qt after deps, Tk before when available).
8. Hash-pinned per-OS lock files (`pip-compile --generate-hashes` or `uv`).
9. Signed/notarised macOS build; Windows installer; AppImage [P1].
10. More movements and phrase-level choreography (A/B patterns per song section).
11. Thicker, animated happy eyes; more expressions (surprised on surges, sleepy after long idle).

## P3 — extensibility
12. External character models (GLB/VRM via a converter) using the joint-name hook.
13. User-authored movement sequences (JSON) loaded into the library.
14. Optional, explicitly enabled microphone input (clearly labelled).
15. Launch at login, localisation, accessibility review.
16. Local music classification / ML choreography (see future-ai-features.md).
