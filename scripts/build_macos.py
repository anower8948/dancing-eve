"""Build Project EVE for macOS (must be run on macOS). See docs/packaging.md."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_app

if __name__ == "__main__":
    if not sys.platform.startswith("darwin"):
        print("build_macos.py must be run on macOS (PyInstaller cannot cross-compile).")
        raise SystemExit(2)
    raise SystemExit(build_app.main())
