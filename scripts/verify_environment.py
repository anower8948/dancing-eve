"""Verify this machine can run Project EVE; prints a readable report.

    .venv/bin/python scripts/verify_environment.py [--capture SECONDS]

Checks Python, installed package versions, OpenGL offscreen rendering, Qt platform and
system-audio capture backends. ``--capture N`` additionally captures N seconds of real
system audio (play music while it runs).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=float, default=0.0)
    args = parser.parse_args()
    ok = True

    from setup import dependency_checker as deps
    from setup.platform_detector import detect_platform

    info = detect_platform()
    print(f"Platform: {info.label}   Python {sys.version.split()[0]} ({sys.executable})")
    reqs = deps.parse_requirements(ROOT / "requirements.txt")
    mismatches = deps.find_mismatches(reqs, deps.installed_versions(Path(sys.executable)))
    print(f"Packages: {'OK' if not mismatches else 'MISMATCH ' + str([(r.name, r.version, h) for r, h in mismatches])}")
    ok &= not mismatches

    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication(sys.argv[:1])
    print(f"Qt platform: {app.platformName()}")
    try:
        from eve.character.character_rig import neutral_pose
        from eve.rendering.panda3d_renderer import Panda3DRenderer

        renderer = Panda3DRenderer()
        renderer.initialize(160, 200)
        frame = renderer.render(neutral_pose())
        alpha = frame.pixels[..., 3]
        coverage = (alpha > 0).mean()
        print(f"Renderer: {renderer.description}; transparent corner={alpha[0, 0] == 0}, robot pixels={coverage:.0%}")
        renderer.dispose()
    except Exception as exc:
        ok = False
        print(f"Renderer: FAILED — {exc}")

    from eve.audio.diagnostics import capture_test, diagnose

    report = diagnose()
    print(f"Audio: {report['summary']}")
    for backend in report["backends"]:
        print(f"  {backend['key']}: {'available' if backend['available'] else 'unavailable — ' + backend['reason']}")
    ok &= bool(report.get("ok"))
    if args.capture > 0:
        print(f"Capturing {args.capture:.0f} s of system audio — play music now…", flush=True)
        result = capture_test(args.capture)
        print(json.dumps(result, indent=2))
        ok &= bool(result["real_audio_received"])
    print("RESULT:", "OK" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
