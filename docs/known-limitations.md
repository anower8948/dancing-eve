# Known limitations

1. **Windows and Ubuntu are untested.** Capture (WASAPI loopback, Pulse monitors),
   launchers, window behaviour and packaging are implemented but have never run on those
   OSes. Expect fixes after the first real test.
2. **macOS permission-denied flow not observed live** (the dev machine had the permission).
   Unit-tested with a fake backend only.
3. **Tempo octave errors:** slow songs with off-beat hi-hats can be read at double tempo
   (70/75 BPM → 140/150), and 174 BPM drum & bass at half-time. The beat grid stays in
   phase, so the dance still lands on beats. Tempo confidence is conservative; songs
   without a clear pulse get the free-running, energy-reactive fallback.
4. **No downbeat/bar detection.** Phrases are 2/4/8-beat aligned from wherever the move
   starts, not from the musical bar.
5. **CPU use** ~20 % of one M2 core while dancing (≈10 % idle, ≈9 % sleepy) because of a synchronous GPU readback each frame
   (see rendering.md). Power-saving mode (30 FPS) and automatic 24 FPS idle help.
6. **Native Wayland:** no always-on-top, positioning or click-through; EVE prefers XWayland.
7. **Click-through, drag, tray menu interaction** are implemented but were not exercised
   by hand on macOS during this session.
8. **Preview of the new moves** was checked in rendered stills and tests, not by watching
   them live with real songs; timing/amplitude tuning may still be needed.
9. **External character models:** configuration hook exists; loading is not implemented.
10. **Packaged macOS app** is ad-hoc signed: it needs re-granting the capture permission
    after each rebuild and is not distributable without Developer ID + notarisation.
11. **Setup UI is terminal-based** (a GUI setup window is a roadmap item).
12. **Dependency hashes** are not pinned (exact versions are).
13. **Exclusive-mode / protected audio** (some pro-audio apps, DRM paths) may be
    uncapturable on any OS.
