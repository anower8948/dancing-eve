# Packaging

Development mode (`run.command` / `run.bat` / `run-ubuntu.sh`) is the primary way to run
EVE. Packaging produces a standalone app with PyInstaller and is kept entirely in
`scripts/` — no application module imports PyInstaller.

```bash
.venv/bin/python scripts/build_macos.py      # on macOS  -> dist/ProjectEVE.app
.venv/bin/python scripts/build_windows.py    # on Windows -> dist\ProjectEVE\ProjectEVE.exe
.venv/bin/python scripts/build_ubuntu.py     # on Ubuntu -> dist/ProjectEVE/ProjectEVE
.venv/bin/python scripts/build_app.py --onefile   # single file (slower start)
.venv/bin/python scripts/clean_build.py      # remove build/ and dist/
```

`build_app.py` installs `requirements-build.txt` (PyInstaller 6.22.3) into the venv if
needed. **Each OS must be built on that OS**; a macOS build will not run on Windows or
Linux.

## What the build includes

* `eve` (all submodules), `panda3d.core` plus the runtime-loaded `libpandagl` display
  module and Panda's `.prc` files. Not `--collect-all panda3d`: the wheel also ships
  optional x86_64-only modules (libRocket) that make PyInstaller abort on arm64.
  When frozen, the renderer sets Panda's `plugin-path` to the bundled folder.
* macOS: PyObjC ScreenCaptureKit/CoreMedia/Quartz; `Info.plist` gets
  `NSAudioCaptureUsageDescription`, `NSScreenCaptureUsageDescription`,
  `LSMinimumSystemVersion 13.0`, bundle id `io.github.projecteve.ProjectEVE`.
* Windows/Linux: SoundCard with its cffi header files.

## Verified

macOS 27.0 / M2 (2026-10-17): `dist/ProjectEVE.app` built (157 MB). The bundled
executable ran the demo smoke test (55 FPS, Panda3D GL renderer, MSAA 4×), listed the
ScreenCaptureKit source, and captured real system audio (tempo locked at 100.1 BPM).
It was launched from a terminal, so macOS attributed the capture permission to the
parent app; **double-clicking the .app in Finder (where the app itself needs the
permission) was not tested.** Windows and Ubuntu builds: not attempted (no machines).

## Signing and distribution

* macOS: the build is **ad-hoc signed** (`codesign --sign -`). It runs on the machine
  that built it. To distribute you need an Apple Developer ID certificate, hardened
  runtime, and notarisation (`codesign --options runtime …`, `notarytool submit`).
  Unsigned/ad-hoc apps downloaded from the internet are blocked by Gatekeeper, and
  macOS resets the Screen & System Audio Recording permission whenever the ad-hoc
  signature changes (i.e. after every rebuild).
* Windows: unsigned executables trigger SmartScreen warnings; sign with an Authenticode
  certificate for distribution. An installer (Inno Setup / MSIX) is a roadmap item.
* Linux: the folder build can be wrapped in an AppImage or .deb later; the target needs
  the same system libraries listed in setup-and-installation.md.

## Common build errors

| Error | Fix |
|---|---|
| `IncompatibleBinaryArchError … rocket … x86_64` | Do not use `--collect-all panda3d` (already handled). |
| App starts but no 3D window / "could not open a graphics pipe" | `libpandagl` missing → check the `--add-binary` lines; on Linux install `libgl1 libegl1`. |
| Qt "could not load the Qt platform plugin xcb" | Install `libxcb-cursor0` on the build/target machine. |
| SoundCard `FileNotFoundError: …pulseaudio.py.h` | Keep `--collect-all soundcard` (header files are data). |
