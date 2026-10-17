"""Project EVE bootstrap — called by run.command / run.bat / run-ubuntu.sh.

Usage:  python setup/bootstrap.py [--yes] [--repair] [--no-launch] [-- <app arguments>]

Runs with only the standard library (any Python 3.8+), so it can explain problems even
before a supported interpreter or the dependencies exist.

Exit codes: 0 ok · 2 Python unavailable · 3 venv failure · 4 dependency install failure
· 5 validation failure · 9 another setup is running · 130 interrupted · otherwise the
application's own exit code.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(1, str(PROJECT_ROOT / "src"))

from eve.storage.paths import resolve_paths  # noqa: E402  (stdlib-only module)
from setup.progress import ProgressReporter, TerminalRenderer  # noqa: E402
from setup.setup_manager import SetupLock, SetupManager, SetupOptions, default_steps  # noqa: E402

LOG_LIMIT_BYTES = 1_000_000


class SetupLog:
    """Plain-text setup log in the user's log directory (rotated at ~1 MB)."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_LIMIT_BYTES:
            backup = path.with_suffix(".log.1")
            if backup.exists():
                backup.unlink()
            path.rename(backup)
        self._handle = open(path, "a", encoding="utf-8")  # noqa: SIM115 - lives for the whole setup run
        self.write("=" * 60)
        self.write("Setup started {}".format(datetime.datetime.now().isoformat(timespec="seconds")))

    def write(self, text: str) -> None:
        for line in str(text).splitlines() or [""]:
            self._handle.write(line + "\n")
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()


def _ask_tty(question: str) -> bool:
    try:
        answer = input(question + " [Y/n] ").strip().lower()
    except EOFError:
        return False
    return answer in ("", "y", "yes")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Project EVE setup and launcher")
    parser.add_argument("--yes", "-y", action="store_true", help="answer yes to install prompts")
    parser.add_argument("--repair", action="store_true", help="re-sync and re-validate all dependencies")
    parser.add_argument("--no-launch", action="store_true", help="prepare the environment only")
    parser.add_argument("app_args", nargs=argparse.REMAINDER, help="arguments passed to the app after --")
    args = parser.parse_args(argv)
    if args.app_args and args.app_args[0] == "--":
        args.app_args = args.app_args[1:]
    return args


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    paths = resolve_paths()
    log = SetupLog(paths.log_dir / "setup.log")
    renderer = TerminalRenderer()
    reporter = ProgressReporter(default_steps(), renderer)
    interactive = sys.stdin is not None and sys.stdin.isatty()
    options = SetupOptions(
        assume_yes=args.yes,
        repair=args.repair,
        launch=not args.no_launch,
        app_args=list(args.app_args),
        interactive=interactive,
    )
    lock = SetupLock(PROJECT_ROOT / ".eve-setup" / "setup.lock")
    if not lock.acquire():
        renderer.message("Another Project EVE setup is already running in this folder. Wait for it to finish.")
        return 9
    manager = SetupManager(PROJECT_ROOT, reporter, options, log.write, renderer.message, _ask_tty)
    try:
        code = manager.run()
    except KeyboardInterrupt:
        renderer.message("\nSetup interrupted. Completed steps are kept; run the launcher again to continue.")
        code = 130
    except Exception as exc:  # last-resort guard: always leave a readable message
        log.write("Unexpected error: {!r}".format(exc))
        import traceback

        log.write(traceback.format_exc())
        renderer.message("Unexpected setup error: {}".format(exc))
        code = 1
    finally:
        lock.release()
    if code not in (0, 130):
        renderer.message("Setup log: {}".format(log.path))
    log.write("Exit code {}".format(code))
    log.close()
    return code


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
