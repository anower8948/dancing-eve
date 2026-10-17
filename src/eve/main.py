"""Command-line entry point: ``python -m eve`` (the launchers call this).

Exit codes: 0 ok · 1 error · 3 already running · 4 renderer unavailable.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys

from eve import APP_NAME, __version__

log = logging.getLogger("eve")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="eve", description=f"{APP_NAME} — a dancing desktop robot companion")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--demo", action="store_true", help="dance to a built-in virtual song (no audio capture)")
    parser.add_argument("--no-audio", action="store_true", help="do not capture audio (idle animation only)")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument(
        "--reset-settings", action="store_true", help="restore default settings (old file is backed up)"
    )
    parser.add_argument("--size", type=int, help="character window height in pixels (this run only)")
    parser.add_argument("--fps", type=int, help="target frame rate (this run only)")
    parser.add_argument("--style", choices=("mixed", "dreamers"), help="dance style (this run only)")
    parser.add_argument("--diagnose-audio", action="store_true", help="list capture backends/sources and exit")
    parser.add_argument(
        "--test-capture", type=float, metavar="SECONDS", help="capture real system audio for N seconds, report, exit"
    )
    parser.add_argument("--source", help="audio source id for --test-capture")
    parser.add_argument("--json", action="store_true", help="machine-readable output for diagnostics")
    parser.add_argument(
        "--smoke-test",
        type=float,
        metavar="SECONDS",
        default=0.0,
        help="run N seconds, print a performance report, quit",
    )
    parser.add_argument("--screenshot", help="with --smoke-test: save the last rendered frame (PNG)")
    return parser.parse_args(argv)


def _run_diagnostics(args: argparse.Namespace) -> int | None:
    if args.diagnose_audio:
        from eve.audio.diagnostics import diagnose

        report = diagnose()
        if args.json:
            print(json.dumps(report))
        else:
            print(f"Platform: {report['platform']}")
            for backend in report["backends"]:
                state = "available" if backend["available"] else f"unavailable ({backend['reason']})"
                print(f"  backend {backend['key']}: {backend['name']} — {state}")
            for source in report["sources"]:
                print(f"  source {source['id']}: {source['name']}{' [default]' if source['default'] else ''}")
            if "screen_recording_permission" in report:
                print(f"  Screen & System Audio Recording permission granted: {report['screen_recording_permission']}")
            print(f"Summary: {report['summary']}")
        return 0
    if args.test_capture:
        from eve.audio.diagnostics import capture_test

        if not args.json:
            print(f"Capturing system audio for {args.test_capture:.0f} s — play some music now…", flush=True)
        report = capture_test(args.test_capture, args.source)
        print(json.dumps(report, indent=None if args.json else 2))
        return 0 if report["real_audio_received"] else 1
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    code = _run_diagnostics(args)
    if code is not None:
        return code

    from eve.desktop.platform_capabilities import preferred_qt_platform
    from eve.logging_config import configure_logging
    from eve.storage.paths import resolve_paths

    paths = resolve_paths().ensure()
    log_path = configure_logging(paths.log_dir, args.debug)
    log.info("%s %s starting (Python %s, %s)", APP_NAME, __version__, sys.version.split()[0], sys.platform)
    qpa = preferred_qt_platform()
    if qpa:
        os.environ["QT_QPA_PLATFORM"] = qpa
        log.info("using Qt platform %s (XWayland)", qpa)

    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox

    from eve.application import AppOptions, EveApplication
    from eve.constants import ORGANIZATION
    from eve.exceptions import RendererUnavailable
    from eve.storage.settings_store import SettingsStore

    qapp = QApplication(sys.argv[:1])
    qapp.setApplicationName(APP_NAME)
    qapp.setOrganizationName(ORGANIZATION)
    qapp.setApplicationDisplayName(APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)  # closing Settings must not quit the companion

    lock = QLockFile(str(paths.lock_file))
    lock.setStaleLockTime(0)
    if not lock.tryLock(200):
        message = f"{APP_NAME} is already running. Use its tray / menu-bar icon to show it."
        log.warning(message)
        print(message, file=sys.stderr)
        QMessageBox.information(None, APP_NAME, message)
        return 3

    store = SettingsStore(paths.settings_file)
    settings = store.reset() if args.reset_settings else store.load()

    options = AppOptions(
        demo=args.demo,
        no_audio=args.no_audio,
        debug=args.debug,
        smoke_test=args.smoke_test,
        size=max(140, min(560, args.size)) if args.size else None,
        fps=max(15, min(120, args.fps)) if args.fps else None,
        style=args.style,
        screenshot=args.screenshot,
    )
    app = EveApplication(qapp, options, paths, store, settings)
    try:
        app.start()
    except RendererUnavailable as exc:
        log.error("%s", exc)
        QMessageBox.critical(
            None,
            APP_NAME,
            f"{exc}\n\nPlease make sure your graphics drivers support OpenGL 2.1 or newer.\nLog: {log_path}",
        )
        lock.unlock()
        return 4

    def _stop(*_args: object) -> None:
        app.quit()

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)
    code = qapp.exec()
    lock.unlock()
    log.info("exited with code %s", code)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
