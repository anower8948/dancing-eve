"""Remove build artefacts (build/, dist/, caches). Never touches .venv or user settings."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ["build", "dist", ".pytest_cache", ".mypy_cache", ".ruff_cache"]


def main() -> int:
    for name in TARGETS:
        path = ROOT / name
        if path.is_dir() and path.resolve().parent == ROOT:
            shutil.rmtree(path)
            print(f"removed {name}/")
    for cache in ROOT.glob("**/__pycache__"):
        if ".venv" not in cache.parts:
            shutil.rmtree(cache, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
