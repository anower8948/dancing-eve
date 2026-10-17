"""First-time setup and repeated-launch orchestration.

Flow (each line is one progress step):

  1. Detect operating system
  2. Check Python (find a supported interpreter; offer a safe install if none)
  3. Check system requirements
  4. Create / reuse the project-local virtual environment (.venv)
  5. Install pinned dependencies (skipped when the install fingerprint matches)
  6. Validate packages (versions + imports)
  7. Check audio support (non-fatal diagnostics)
  8. Launch Project EVE

Completed work is preserved between runs: an interrupted install keeps the venv and the
already-downloaded packages, and the install marker is only written after validation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from setup import dependency_checker as deps
from setup import environment_manager as envm
from setup.platform_detector import LINUX, MACOS, WINDOWS, PlatformInfo, detect_platform
from setup.progress import ProgressReporter, SetupStep

MARKER_NAME = ".eve-install.json"
MARKER_VERSION = 1


@dataclass
class SetupOptions:
    assume_yes: bool = False
    repair: bool = False
    launch: bool = True
    app_args: List[str] = field(default_factory=list)
    interactive: bool = True
    max_network_attempts: int = 3


def default_steps() -> List[SetupStep]:
    return [
        SetupStep("os", "Detecting operating system", 1),
        SetupStep("python", "Checking Python", 2),
        SetupStep("system", "Checking system requirements", 1),
        SetupStep("venv", "Creating virtual environment", 4),
        SetupStep("deps", "Installing dependencies", 24),
        SetupStep("validate", "Validating packages", 4),
        SetupStep("audio", "Checking audio support", 2),
        SetupStep("launch", "Launching Project EVE", 1),
    ]


class SetupLock:
    """Prevents two launchers from installing into the same venv at once."""

    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._is_stale():
                    try:
                        self.path.unlink()
                    except OSError:
                        return False
                    continue
                return False
            with os.fdopen(fd, "w") as handle:
                handle.write(str(os.getpid()))
            self.acquired = True
            return True
        return False

    def _is_stale(self) -> bool:
        try:
            pid = int(self.path.read_text().strip() or "0")
        except (OSError, ValueError):
            return True
        if pid <= 0:
            return True
        if time.time() - self.path.stat().st_mtime > 3600:
            return True  # nothing legitimately installs for an hour
        return not _pid_alive(pid)

    def release(self) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except OSError:
                pass
            self.acquired = False


def _pid_alive(pid: int) -> bool:
    if sys.platform.startswith("win"):
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # type: ignore[attr-defined]
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
            return True
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class SetupManager:
    def __init__(
        self,
        project_root: Path,
        reporter: ProgressReporter,
        options: SetupOptions,
        log: Callable[[str], None],
        say: Callable[[str], None],
        ask: Optional[Callable[[str], bool]] = None,
        platform_info: Optional[PlatformInfo] = None,
    ):
        self.root = project_root
        self.reporter = reporter
        self.options = options
        self.log = log
        self.say = say
        self._ask = ask
        self.platform = platform_info
        self.venv_dir = project_root / ".venv"
        self.python: Optional[envm.PythonCandidate] = None
        self.requirement_files = [project_root / "requirements.txt"]
        self.warnings: List[str] = []

    # ------------------------------------------------------------------------------------
    def ask(self, question: str) -> bool:
        if self.options.assume_yes:
            return True
        if not self.options.interactive or self._ask is None:
            return False
        return self._ask(question)

    @property
    def venv_python(self) -> Path:
        return envm.venv_python(self.venv_dir)

    def run(self) -> int:
        """Run every step. Returns the process exit code (0 on success)."""
        steps = [
            ("os", self.step_detect_os),
            ("python", self.step_check_python),
            ("system", self.step_check_system),
            ("venv", self.step_venv),
            ("deps", self.step_dependencies),
            ("validate", self.step_validate),
            ("audio", self.step_audio),
        ]
        for key, func in steps:
            try:
                func(key)
            except envm.SetupError as exc:
                self.reporter.fail(key, str(exc))
                self.say("")
                self.say("Setup failed at step: " + self._title(key))
                self.say("Problem: " + str(exc))
                if exc.hint:
                    self.say("What to do: " + exc.hint)
                self.say("Completed steps are kept; running the launcher again resumes from here.")
                return exc.exit_code
        if not self.options.launch:
            self.reporter.skip("launch", "--no-launch")
            return 0
        return self.step_launch("launch")

    def _title(self, key: str) -> str:
        for step in self.reporter.steps:
            if step.key == key:
                return step.title
        return key

    # ------------------------------------------------------------------------------------
    def step_detect_os(self, key: str) -> None:
        self.reporter.start(key)
        self.platform = self.platform or detect_platform()
        self.log("Platform: " + repr(self.platform))
        if self.platform.system not in (MACOS, WINDOWS, LINUX):
            raise envm.SetupError(
                "Unsupported operating system ({}).".format(sys.platform),
                "Project EVE supports macOS, Windows 10/11 and Ubuntu Linux.",
                exit_code=2,
            )
        self.reporter.complete(key, self.platform.label)

    def step_check_python(self, key: str) -> None:
        assert self.platform is not None
        self.reporter.start(key, "looking for " + envm.supported_range_text())
        existing = envm.inspect_venv(self.venv_dir)
        if existing is not None and existing.supported:
            self.python = existing
            self.reporter.complete(key, "using existing environment (Python {}.{}.{})".format(*existing.version))
            return
        candidates = envm.find_python_candidates(self.platform.system)
        for candidate in candidates:
            self.log("Found interpreter {} -> {}".format(candidate.executable, candidate.version))
        chosen = envm.select_python(candidates)
        if chosen is None:
            chosen = self._offer_python_install(candidates)
        self.python = chosen
        self.reporter.complete(key, "Python {}.{}.{} ({})".format(*chosen.version, chosen.executable))

    def _python_install_plan(self) -> Optional[List[str]]:
        assert self.platform is not None
        if self.platform.system == MACOS and shutil.which("brew"):
            return ["brew", "install", "python@3.12"]
        if self.platform.system == WINDOWS and shutil.which("winget"):
            return ["winget", "install", "--exact", "--id", "Python.Python.3.12", "--scope", "user"]
        if (
            self.platform.system == LINUX
            and shutil.which("apt-get")
            and self.platform.distro_id in ("ubuntu", "debian", "pop", "linuxmint")
        ):
            if self.platform.distro_version.startswith("22."):
                return ["sudo", "apt-get", "install", "-y", "python3.11", "python3.11-venv"]
            return ["sudo", "apt-get", "install", "-y", "python3", "python3-venv"]
        return None

    def _manual_python_hint(self) -> str:
        assert self.platform is not None
        need = envm.supported_range_text()
        if self.platform.system == MACOS:
            return (
                "Install {} from https://www.python.org/downloads/macos/ "
                "(or with Homebrew: brew install python@3.12), then double-click run.command again.".format(need)
            )
        if self.platform.system == WINDOWS:
            return (
                "Install {} from https://www.python.org/downloads/windows/ "
                "(tick 'Add python.exe to PATH'), then double-click run.bat again.".format(need)
            )
        return (
            "Install {} with your package manager (Ubuntu: sudo apt install python3 python3-venv), "
            "then run ./run-ubuntu.sh again.".format(need)
        )

    def _offer_python_install(self, candidates: Sequence[envm.PythonCandidate]) -> envm.PythonCandidate:
        assert self.platform is not None
        found = ", ".join("{}.{}.{}".format(*c.version) for c in candidates) or "none"
        message = "No supported Python found ({} needed; found: {}).".format(envm.supported_range_text(), found)
        plan = self._python_install_plan()
        if plan is None:
            raise envm.SetupError(message, self._manual_python_hint(), exit_code=2)
        self.say("")
        self.say(message)
        self.say("EVE can install it for you by running:")
        self.say("    " + " ".join(plan))
        if plan[0] == "sudo":
            self.say("This uses 'sudo' because system packages on Ubuntu can only be installed by an administrator.")
            self.say("Your password is requested by sudo itself; EVE never sees it.")
        if not self.ask("Install Python now?"):
            raise envm.SetupError(message, self._manual_python_hint(), exit_code=2)
        self.log("Running: " + " ".join(plan))
        if subprocess.call(plan) != 0:
            raise envm.SetupError("The Python installation command failed.", self._manual_python_hint(), exit_code=2)
        chosen = envm.select_python(envm.find_python_candidates(self.platform.system))
        if chosen is None:
            raise envm.SetupError(
                "Python was installed but could not be found yet.",
                "Close this window and start the launcher again (a new terminal picks up the updated PATH).",
                exit_code=2,
            )
        return chosen

    def step_check_system(self, key: str) -> None:
        assert self.platform is not None
        self.reporter.start(key)
        notes: List[str] = []
        if self.platform.system == MACOS:
            version = self.platform.macos_version()
            if version and version < (13,):
                notes.append(
                    "macOS {} has no native system-audio capture (needs macOS 13+); "
                    "EVE will need a virtual audio device such as BlackHole.".format(self.platform.release)
                )
        elif self.platform.system == LINUX:
            notes.extend(deps.check_linux_system_libraries())
            if self.platform.session_type == "wayland":
                notes.append(
                    "Wayland session: EVE runs through XWayland for always-on-top and positioning when available."
                )
        for note in notes:
            self.log("System note: " + note)
        self.warnings.extend(notes)
        self.reporter.complete(key, "{} note(s)".format(len(notes)) if notes else "ok")

    def step_venv(self, key: str) -> None:
        assert self.python is not None
        self.reporter.start(key)
        existing = envm.inspect_venv(self.venv_dir)
        if existing is not None and existing.supported:
            # --repair re-syncs packages in the next step; a working venv is never rebuilt.
            self.reporter.skip(key, "reusing .venv")
            return
        if existing is not None and not existing.supported:
            self.log("Existing venv uses unsupported Python {}; recreating.".format(existing.version))
        self.reporter.update(key, 0.2, "python -m venv .venv")
        envm.create_venv(self.python, self.venv_dir, self.log)
        self.reporter.complete(key, str(self.venv_dir.name))

    # -- dependencies -------------------------------------------------------------------
    def _fingerprint(self) -> str:
        assert self.python is not None
        venv = envm.inspect_venv(self.venv_dir)
        version = venv.version if venv else self.python.version
        return deps.requirements_fingerprint(self.requirement_files, version, sys.platform)

    def _marker_path(self) -> Path:
        return self.venv_dir / MARKER_NAME

    def _read_marker(self) -> Optional[dict]:
        try:
            return json.loads(self._marker_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _write_marker(self) -> None:
        data = {"version": MARKER_VERSION, "fingerprint": self._fingerprint(), "installed_at": time.time()}
        self._marker_path().write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _requirements(self) -> List[deps.Requirement]:
        result: List[deps.Requirement] = []
        for file in self.requirement_files:
            result.extend(deps.parse_requirements(file))
        return result

    def step_dependencies(self, key: str) -> None:
        self.reporter.start(key, "checking installed packages")
        requirements = self._requirements()
        marker = self._read_marker()
        fingerprint = self._fingerprint()
        if marker and marker.get("fingerprint") == fingerprint and not self.options.repair:
            mismatches = deps.find_mismatches(requirements, deps.installed_versions(self.venv_python))
            if not mismatches:
                self.reporter.skip(key, "already up to date")
                return
            self.log("Installed packages drifted: {}".format(mismatches))
        total = max(1, len(requirements))
        seen: set = set()

        def on_package(name: str) -> None:
            seen.add(deps.normalize_name(name))
            self.reporter.update(
                key,
                0.85 * min(len(seen), total) / total,
                "{} of {} packages: {}".format(min(len(seen), total), total, name),
            )

        def on_installing() -> None:
            self.reporter.update(key, 0.88, "installing packages")

        args = ["install", "--retries", "3", "--timeout", "30", "--progress-bar", "off"]
        for file in self.requirement_files:
            args += ["-r", str(file)]

        attempt = 0
        while True:
            attempt += 1
            self.reporter.update(key, 0.0, "attempt {}".format(attempt) if attempt > 1 else "resolving")
            code, output = envm.run_pip(self.venv_python, args, self.log, on_package, on_installing)
            if code == 0:
                break
            network = envm.looks_like_network_error(output)
            if network and attempt < self.options.max_network_attempts:
                delay = 5 * attempt
                self.reporter.update(key, 0.0, "network problem — retrying in {} s".format(delay))
                time.sleep(delay)
                continue
            if network and self.ask("Downloading packages failed (network problem). Retry now?"):
                continue
            if network:
                raise envm.SetupError(
                    "Downloading packages failed — the network or the package index is unreachable.",
                    "Check your internet connection (and proxy settings), then start the launcher again. "
                    "Packages that already downloaded are kept.",
                    exit_code=4,
                    retryable=True,
                )
            raise envm.SetupError(
                "pip could not install the dependencies (exit code {}).".format(code),
                "See the setup log for the pip output. Running the launcher again retries the installation.",
                exit_code=4,
            )
        self.reporter.complete(key, "{} packages".format(total))

    def step_validate(self, key: str) -> None:
        self.reporter.start(key, "checking versions")
        requirements = self._requirements()
        mismatches = deps.find_mismatches(requirements, deps.installed_versions(self.venv_python))
        if mismatches:
            names = ", ".join("{}=={} (have {})".format(r.name, r.version, have or "nothing") for r, have in mismatches)
            raise envm.SetupError(
                "Installed packages do not match requirements: " + names,
                "Run the launcher again to repair.",
                exit_code=5,
            )
        self.reporter.update(key, 0.4, "importing modules")
        modules = dict(deps.REQUIRED_IMPORTS)
        platform_key = (
            "darwin" if sys.platform == "darwin" else ("win32" if sys.platform.startswith("win") else "linux")
        )
        modules.update(deps.PLATFORM_IMPORTS.get(platform_key, {}))
        failures = deps.validate_imports(self.venv_python, modules)
        if failures:
            hint = "Run the launcher again to repair the installation."
            if (
                any("xcb" in f.lower() or "libgl" in f.lower() or "pulse" in f.lower() for f in failures)
                and self.platform
                and self.platform.system == LINUX
            ):
                hint = "Install the missing system libraries: sudo apt install libxcb-cursor0 libpulse0 libgl1 libegl1"
            raise envm.SetupError("Some packages failed to import: " + "; ".join(failures), hint, exit_code=5)
        self._write_marker()
        self.reporter.complete(key)

    def _app_env(self) -> dict:
        env = dict(os.environ)
        src = str(self.root / "src")
        env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["EVE_LAUNCHER"] = "1"
        return env

    def step_audio(self, key: str) -> None:
        self.reporter.start(key, "probing capture backends")
        try:
            result = subprocess.run(
                [str(self.venv_python), "-m", "eve", "--diagnose-audio", "--json"],
                capture_output=True,
                text=True,
                timeout=45,
                cwd=str(self.root),
                env=self._app_env(),
            )
            report = json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else {}
        except (subprocess.SubprocessError, OSError, ValueError, IndexError) as exc:
            self.log("Audio diagnostics failed: {}".format(exc))
            self.reporter.complete(key, "diagnostics unavailable (non-fatal)")
            return
        self.log("Audio diagnostics: " + json.dumps(report))
        summary = report.get("summary") or "unknown"
        if not report.get("ok", False):
            self.warnings.append("Audio: " + summary)
        self.reporter.complete(key, summary[:70])

    def step_launch(self, key: str) -> int:
        self.reporter.start(key)
        command = [str(self.venv_python), "-m", "eve"] + list(self.options.app_args)
        self.log("Launching: " + " ".join(command))
        self.reporter.complete(key)
        for warning in self.warnings:
            self.say("Note: " + warning)
        self.say("Project EVE is running. Close it from its tray/menu-bar icon or right-click menu.")
        try:
            return subprocess.call(command, cwd=str(self.root), env=self._app_env())
        except KeyboardInterrupt:
            return 130
