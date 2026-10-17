# Next steps (priority order)

0. **Run the CI workflow** (push to GitHub) and fix anything it finds on Windows/Ubuntu.
   Done when: both `platforms` jobs are green and artifacts (screenshots, builds) look right.
1. **Windows 10/11 real test.**
   Done when: `run.bat` completes setup from a clean checkout; `--test-capture 15` reports
   `RECEIVING_AUDIO` with music playing; the robot dances, idles on pause, quits cleanly;
   `docs/cross-platform-support.md` updated with evidence.
2. **Ubuntu 24.04 real test (GNOME, Wayland session → XWayland, and X11).**
   Done when: `run-ubuntu.sh` works from a terminal and from Files; a PipeWire monitor
   source is captured; transparency/always-on-top/tray verified or limitations documented.
3. **macOS permission-denied walkthrough** on a user without the permission.
   Done when: the denial shows the guidance text, "Open Privacy Settings…" opens the
   right pane, and Retry after relaunching Terminal reaches `RECEIVING_AUDIO`.
4. **Manual interaction pass (macOS).**
   Done when: drag, poke, double-click, context menu, tray menu, click-through on/off,
   hide/show and moving between the 1080p and 4K monitors all behave; bugs fixed.
5. **Watch EVE with real songs** (several genres/tempos) and tune thresholds/weights,
   including the 14 moves and phrase patterns added in session 2.
   Done when: calm, groove and energetic songs visibly differ, no jitter, settling is
   smooth; changes recorded in IMPLEMENTATION_LOG.md.
6. **Reduce CPU further** (async readback or a Qt-shared GL context). Idle is now ≈10 %.
   Done when: dancing CPU < 12 % and idle < 6 % of one core on the M2.
7. **Finder double-click tests** for `run.command` and `dist/ProjectEVE.app`.
   Done when: both start EVE and the permission is attributed as documented.
