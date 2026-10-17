# Documentation index

| Document | Contents |
|---|---|
| [architecture.md](architecture.md) | Components, data flow (Mermaid), threading, interfaces, error handling, storage |
| [architecture-decisions.md](architecture-decisions.md) | ADRs: Python version, rendering integration, capture APIs, no-mic rule, DSP, animation, setup, pinning, packaging |
| [audio-capture.md](audio-capture.md) | Per-platform capture, permissions, statuses, verification log, analysis summary |
| [animation-system.md](animation-system.md) | Rig channels, animation layers, springs, choreography, adding movements |
| [rendering.md](rendering.md) | Offscreen Panda3D pipeline, shading, measured performance, model replacement hook |
| [cross-platform-support.md](cross-platform-support.md) | Verified / partial / planned matrix |
| [setup-and-installation.md](setup-and-installation.md) | Launchers, first-run steps, recovery, storage locations |
| [packaging.md](packaging.md) | PyInstaller builds, signing, build errors |
| [testing.md](testing.md) | Automated coverage, manual real-audio checklist, performance measurement |
| [troubleshooting.md](troubleshooting.md) | Symptoms and fixes |
| [privacy.md](privacy.md) | What is captured, processed and stored |
| [known-limitations.md](known-limitations.md) | Current limitations |
| [development-roadmap.md](development-roadmap.md) | Prioritised future work |
| [future-ai-features.md](future-ai-features.md) | Ideas for local ML features (not implemented) |

Development state for the next coding session: [../dev/CURRENT_STATE.md](../dev/CURRENT_STATE.md),
[../dev/NEXT_STEPS.md](../dev/NEXT_STEPS.md).

### Repository layout notes

The tree follows the requested structure with these deliberate differences (no empty
placeholder modules): `desktop/transparency.py` and `desktop/click_through.py` are folded
into `desktop/window_manager.py`; `core/events.py` and `core/service_manager.py` were not
needed (Qt signals and the composition root cover them); `desktop/startup_manager.py`
(launch at login) and `ui/setup_window.py` (GUI setup) are roadmap items. Added:
`audio/diagnostics.py`, `audio/platforms/soundcard_backend.py`, `dance/demo_source.py`,
`desktop/icons.py`, `rendering/shaders.py`, `tests/unit/test_capture_manager.py`,
`test_setup_progress.py`, `test_character_geometry.py`.
