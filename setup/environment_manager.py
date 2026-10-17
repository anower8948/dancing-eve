"""Python interpreter discovery, virtual-environment creation and pip execution.

All subprocesses are started with argument lists (never ``shell=True``) so paths with
spaces or shell metacharacters are passed through safely.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# Supported interpreter range: >= MIN, < MAX_EXCLUSIVE (verified wheels exist for all deps).
MIN_PYTHON = (3, 11)
MAX_PYTHON_EXCLUSIVE = (3, 14)
PREFERRED_MINORS = (12, 13, 11)


@dataclass(frozen=True)
class PythonCandidate:
    command: Tuple[str, ...]  # how to invoke it, e.g. ("py", "-3.12") or ("/usr/bin/python3.12",)
    version: Tuple[int, int, int]
    executable: str

    @property
    def supported(self) -> bool:
        return MIN_PYTHON <= self.version[:2] < MAX_PYTHON_EXCLUSIVE


def is_supported_version(version: Sequence[int]) -> bool:
    return MIN_PYTHON <= tuple(version[:2]) < MAX_PYTHON_EXCLUSIVE


def supported_range_text() -> str:
    hi = (MAX_PYTHON_EXCLUSIVE[0], MAX_PYTHON_EXCLUSIVE[1] - 1)
    return "Python {}.{} – {}.{}".format(MIN_PYTHON[0], MIN_PYTHON[1], hi[0], hi[1])


_PROBE = "import sys; print(sys.executable); print('%d.%d.%d' % sys.version_info[:3])"


def probe_python(command: Sequence[str], timeout: float = 15.0) -> Optional[PythonCandidate]:
    """Run an interpreter to learn its real version. Returns None if it does not work."""
    try:
        result = subprocess.run(
            list(command) + ["-c", _PROBE],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    lines = result.stdout.strip().splitlines()
    if len(lines) < 2:
        return None
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", lines[-1])
    if not match:
        return None
    version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return PythonCandidate(tuple(command), version, lines[-2].strip())


def _candidate_commands(system: str) -> List[Tuple[str, ...]]:
    commands: List[Tuple[str, ...]] = []
    if system == "windows":
        for minor in PREFERRED_MINORS:
            commands.append(("py", "-3.{}".format(minor)))
        commands.append(("python",))
        commands.append(("python3",))
        return commands
    names = ["python3.{}".format(minor) for minor in PREFERRED_MINORS] + ["python3"]
    search_dirs: List[str] = []
    if system == "macos":
        search_dirs += ["/opt/homebrew/bin", "/usr/local/bin"]
        for minor in PREFERRED_MINORS:
            search_dirs.append("/Library/Frameworks/Python.framework/Versions/3.{}/bin".format(minor))
    for name in names:
        found = shutil.which(name)
        if found:
            commands.append((found,))
        for folder in search_dirs:
            path = os.path.join(folder, name)
            if os.path.isfile(path) and os.access(path, os.X_OK):
                commands.append((path,))
    return commands


def find_python_candidates(system: str, include_current: bool = True) -> List[PythonCandidate]:
    """Return working interpreters, supported versions first (preferred minor order)."""
    seen = set()
    found: List[PythonCandidate] = []
    commands = _candidate_commands(system)
    if include_current and sys.executable:
        commands.insert(0, (sys.executable,))
    for command in commands:
        candidate = probe_python(command)
        if candidate is None:
            continue
        key = os.path.normcase(os.path.realpath(candidate.executable))
        if key in seen:
            continue
        seen.add(key)
        found.append(candidate)

    def rank(c: PythonCandidate) -> Tuple[int, int]:
        if not c.supported:
            return (1, 0)
        minor = c.version[1]
        return (0, PREFERRED_MINORS.index(minor) if minor in PREFERRED_MINORS else 99)

    found.sort(key=rank)
    return found


def select_python(candidates: Iterable[PythonCandidate]) -> Optional[PythonCandidate]:
    for candidate in candidates:
        if candidate.supported:
            return candidate
    return None


# ---------------------------------------------------------------------------------------
# Virtual environment
# ---------------------------------------------------------------------------------------
def venv_python(venv_dir: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def inspect_venv(venv_dir: Path) -> Optional[PythonCandidate]:
    """Return the venv interpreter if the environment exists and actually runs."""
    python = venv_python(venv_dir)
    if not python.exists() or not (venv_dir / "pyvenv.cfg").exists():
        return None
    return probe_python((str(python),))


class SetupError(Exception):
    """A setup step failed; ``hint`` tells the user what to do next."""

    def __init__(self, message: str, hint: str = "", exit_code: int = 1, retryable: bool = False):
        super().__init__(message)
        self.hint = hint
        self.exit_code = exit_code
        self.retryable = retryable


def create_venv(python: PythonCandidate, venv_dir: Path, log: Callable[[str], None]) -> None:
    """Create ``venv_dir`` with ``python``. A broken previous venv is moved aside, not deleted."""
    if venv_dir.exists():
        backup = venv_dir.with_name(venv_dir.name + ".broken")
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)  # only ever our own previous broken copy
        log("Moving incomplete environment aside: {} -> {}".format(venv_dir, backup))
        venv_dir.rename(backup)
    command = list(python.command) + ["-m", "venv", str(venv_dir)]
    log("Running: " + " ".join(command))
    result = subprocess.run(command, capture_output=True, text=True)
    log(result.stdout + result.stderr)
    if result.returncode != 0 or not venv_python(venv_dir).exists():
        text = (result.stdout + result.stderr).lower()
        hint = "See the setup log for details."
        if "ensurepip" in text or "python3-venv" in text or ("venv" in text and "apt" in text):
            hint = (
                "Your Python is missing the 'venv' module. On Ubuntu/Debian run:\n"
                "    sudo apt install python3-venv\n"
                "(or python{}.{}-venv for the exact version), then start EVE again.".format(*python.version[:2])
            )
        raise SetupError("Could not create the virtual environment.", hint, exit_code=3)


# ---------------------------------------------------------------------------------------
# pip
# ---------------------------------------------------------------------------------------
NETWORK_ERROR_PATTERNS = (
    "could not fetch url",
    "connection error",
    "connectionerror",
    "newconnectionerror",
    "temporary failure in name resolution",
    "name or service not known",
    "nodename nor servname provided",
    "max retries exceeded",
    "read timed out",
    "connect timeout",
    "network is unreachable",
    "ssl: certificate_verify_failed",
    "no matching distribution found",
    "could not find a version that satisfies",
    "proxyerror",
)


def looks_like_network_error(output: str) -> bool:
    lowered = output.lower()
    return any(pattern in lowered for pattern in NETWORK_ERROR_PATTERNS)


_COLLECT_RE = re.compile(r"^(?:Collecting|Requirement already satisfied:)\s+([A-Za-z0-9_.\-]+)")
_INSTALLING_RE = re.compile(r"^Installing collected packages:")


def run_pip(
    python: Path,
    args: Sequence[str],
    log: Callable[[str], None],
    on_package: Optional[Callable[[str], None]] = None,
    on_installing: Optional[Callable[[], None]] = None,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str]:
    """Run ``python -m pip <args>``, streaming output to ``log``.

    ``on_package`` is called for each requirement pip resolves; this drives the real
    per-package progress fraction during installation.
    """
    command = [str(python), "-m", "pip"] + list(args)
    log("Running: " + " ".join(command))
    run_env = dict(os.environ if env is None else env)
    run_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    run_env["PYTHONUNBUFFERED"] = "1"
    captured: List[str] = []
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=run_env,
        )
    except OSError as exc:
        raise SetupError("Could not start pip: {}".format(exc), exit_code=4) from exc
    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip()
        captured.append(line)
        if len(captured) > 400:
            del captured[:100]
        log(line)
        match = _COLLECT_RE.match(line)
        if match and on_package is not None:
            on_package(match.group(1))
        elif _INSTALLING_RE.match(line) and on_installing is not None:
            on_installing()
    code = process.wait()
    return code, "\n".join(captured)
