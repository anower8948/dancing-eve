"""Build a standalone Project EVE application with PyInstaller for the *current* OS.

    .venv/bin/python scripts/build_app.py            # build
    .venv/bin/python scripts/build_app.py --onefile  # single executable (slower start)

Each OS must be built on that OS (PyInstaller does not cross-compile). Output goes to
``dist/``; intermediate files to ``build/``. Packaging is kept separate from app logic:
nothing in src/ imports PyInstaller.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "ProjectEVE"
BUNDLE_ID = "io.github.projecteve.ProjectEVE"


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Installing build requirements (PyInstaller)…", flush=True)
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements-build.txt")])


def entry_script() -> Path:
    path = ROOT / "build" / "eve_entry.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("from eve.main import main\n\nraise SystemExit(main())\n", encoding="utf-8")
    return path


def panda3d_binaries() -> list[str]:
    import panda3d

    folder = Path(panda3d.__file__).parent
    sep = ";" if sys.platform.startswith("win") else ":"
    args: list[str] = []
    # GPU OpenGL module, plus the fallbacks the renderer may switch to at runtime:
    # headless EGL (Linux) and the software rasteriser (all platforms).
    patterns = ("libpandagl.*", "libp3headlessgl.*", "libp3tinydisplay.*")
    for pattern in patterns:
        for path in folder.glob(pattern):
            args += ["--add-binary", f"{path}{sep}panda3d"]
    for prc in (folder / "etc").glob("*.prc"):
        args += ["--add-data", f"{prc}{sep}panda3d/etc"]
    if not any(a.startswith(str(folder / "libpandagl")) for a in args):
        raise SystemExit("libpandagl not found in the Panda3D installation")
    return args


def pyinstaller_args(onefile: bool) -> list[str]:
    args = [
        str(entry_script()),
        "--name",
        APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",
        "--paths",
        str(ROOT / "src"),
        "--distpath",
        str(ROOT / "dist"),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
        "--specpath",
        str(ROOT / "build"),
        # Only the Panda3D parts EVE uses (the wheel also ships x86_64-only optional modules
        # such as libRocket that break arm64 bundles). The GL display module is loaded at
        # runtime, so it is added explicitly next to libpanda.
        "--hidden-import",
        "panda3d.core",
        *panda3d_binaries(),
        "--collect-submodules",
        "eve",
        # Unused heavy Qt modules.
        "--exclude-module",
        "PySide6.QtWebEngineCore",
        "--exclude-module",
        "PySide6.QtQml",
        "--exclude-module",
        "tkinter",
    ]
    if onefile:
        args.append("--onefile")
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", BUNDLE_ID]
        for module in ("ScreenCaptureKit", "CoreMedia", "Quartz"):
            args += ["--collect-submodules", module]
    else:
        args += ["--collect-all", "soundcard"]  # ships its C header (.h) files used by cffi
    return args


def patch_macos_plist(app: Path) -> None:
    """Explain the audio permission in the system prompt."""
    import plistlib

    plist_path = app / "Contents" / "Info.plist"
    with plist_path.open("rb") as handle:
        info = plistlib.load(handle)
    info["NSAudioCaptureUsageDescription"] = (
        "Project EVE listens to the music your Mac plays so the robot can dance to it."
    )
    info["NSScreenCaptureUsageDescription"] = (
        "macOS delivers system audio through Screen & System Audio Recording. Project EVE uses audio only; "
        "no screen content is captured or stored."
    )
    info["LSMinimumSystemVersion"] = "13.0"
    info["NSHighResolutionCapable"] = True
    with plist_path.open("wb") as handle:
        plistlib.dump(info, handle)


def check_prerequisites() -> str | None:
    """Return a problem description if this machine cannot build, else None."""
    if sys.platform.startswith("linux"):
        import sysconfig

        # PyInstaller bundles the runtime soname (e.g. libpython3.12.so.1.0), which Ubuntu's
        # system Python ships in a separate package.
        libdir = Path(sysconfig.get_config_var("LIBDIR") or "")
        multiarch = sysconfig.get_config_var("MULTIARCH") or ""
        names = [sysconfig.get_config_var("INSTSONAME") or "", sysconfig.get_config_var("LDLIBRARY") or ""]
        names = [n for n in names if ".so" in n]
        candidates = [folder / name for name in names for folder in (libdir, libdir / multiarch)]
        if not any(c.exists() for c in candidates):
            version = f"{sys.version_info[0]}.{sys.version_info[1]}"
            return (
                f"PyInstaller needs Python's shared library (libpython{version}.so). On Ubuntu install it with:\n"
                f"    sudo apt install libpython{version}"
            )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--onefile", action="store_true")
    args = parser.parse_args()
    if not (3, 11) <= sys.version_info[:2] < (3, 14):
        print("Run this with the project's virtual environment (Python 3.11–3.13).")
        return 2
    problem = check_prerequisites()
    if problem:
        print(problem)
        return 2
    ensure_pyinstaller()
    import PyInstaller.__main__

    PyInstaller.__main__.run(pyinstaller_args(args.onefile))
    dist = ROOT / "dist"
    if sys.platform == "darwin" and not args.onefile:
        app = dist / f"{APP_NAME}.app"
        patch_macos_plist(app)
        # Re-sign ad hoc after editing Info.plist (not a Developer ID signature).
        subprocess.call(["codesign", "--force", "--deep", "--sign", "-", str(app)])
        print(f"Built {app}")
    else:
        print(f"Built into {dist}")
    leftover = ROOT / "build" / "eve_entry.py"
    if leftover.exists():
        leftover.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
