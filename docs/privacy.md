# Privacy

* **What is captured:** the audio your computer outputs (all apps on macOS via
  ScreenCaptureKit; the selected output device's mix on Windows/Linux). Never a microphone.
* **How it is processed:** in memory, on this computer. Samples go into a 2-second ring
  buffer that is constantly overwritten and are reduced to a handful of numbers
  (loudness, band levels, onsets, tempo). Those numbers drive the animation.
* **What is stored:** nothing from the audio — no recordings, no audio files, no
  fingerprints, no song titles. Settings (sliders, window position, chosen source id) and
  text logs (status changes, errors; never samples) are stored locally (paths in
  setup-and-installation.md). Logs are size-limited (1 MB × 3).
* **Network:** none during normal operation. The first-time setup downloads Python
  packages from PyPI; nothing is uploaded. No telemetry, no accounts, no cloud APIs.
* **Visible indicator:** while capture is active the robot shows a coloured dot in its
  top-right corner (green = receiving audio, amber = connecting/no audio, red = problem),
  and the tray icon shows the same colour. "Stop listening" stops the OS stream
  immediately (verified: zero samples arrive after stop); quitting always stops it.
* **Permissions:** macOS asks for "Screen & System Audio Recording" because Apple delivers
  system audio through ScreenCaptureKit. EVE requests a 2×2-pixel, 1 fps video stream (a
  requirement of the API) and discards every frame without reading it.
* **Screen content:** never captured, stored or analysed.
