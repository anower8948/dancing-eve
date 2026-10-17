"""Requirement parsing, install fingerprints, and installed-package validation.

Standard library only (no ``packaging``): requirement lines in this project are always
exact ``name==version`` pins with optional simple ``sys_platform`` markers.
"""

from __future__ import annotations

import ctypes.util
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_PIN_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)\s*==\s*([A-Za-z0-9_.+\-!]+)\s*(?:;\s*(.+))?$")
_MARKER_RE = re.compile(r"""^(sys_platform|platform_system)\s*(==|!=)\s*["']([^"']+)["']$""")

# Import names checked after installation (module -> friendly name).
REQUIRED_IMPORTS = {
    "numpy": "NumPy",
    "PySide6.QtWidgets": "PySide6 (Qt)",
    "panda3d.core": "Panda3D",
}
PLATFORM_IMPORTS = {
    "darwin": {"ScreenCaptureKit": "PyObjC ScreenCaptureKit", "CoreMedia": "PyObjC CoreMedia"},
    "win32": {"soundcard": "SoundCard (WASAPI)"},
    "linux": {"soundcard": "SoundCard (PulseAudio)"},
}


@dataclass(frozen=True)
class Requirement:
    name: str
    version: str
    marker: str = ""

    @property
    def key(self) -> str:
        return normalize_name(self.name)


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def evaluate_marker(marker: str, sys_platform: Optional[str] = None) -> bool:
    """Evaluate the small marker subset used in requirements.txt. Unknown markers -> True."""
    if not marker:
        return True
    sys_platform = sys_platform or sys.platform
    system_name = {"darwin": "Darwin", "win32": "Windows"}.get(sys_platform, "Linux")
    for clause in marker.split(" and "):
        match = _MARKER_RE.match(clause.strip())
        if not match:
            continue
        variable, op, value = match.groups()
        actual = sys_platform if variable == "sys_platform" else system_name
        if (actual == value) != (op == "=="):
            return False
    return True


def parse_requirements(
    path: Path, sys_platform: Optional[str] = None, _seen: Optional[set] = None
) -> List[Requirement]:
    """Parse pinned requirements (follows ``-r other.txt`` includes)."""
    _seen = set() if _seen is None else _seen
    path = path.resolve()
    if path in _seen:
        return []
    _seen.add(path)
    result: List[Requirement] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r "):
            result.extend(parse_requirements(path.parent / line[3:].strip(), sys_platform, _seen))
            continue
        match = _PIN_RE.match(line)
        if not match:
            raise ValueError("Unsupported requirement line in {}: {!r}".format(path.name, raw))
        name, version, marker = match.group(1), match.group(2), (match.group(3) or "").strip()
        if evaluate_marker(marker, sys_platform):
            result.append(Requirement(name, version, marker))
    return result


def requirements_fingerprint(files: Sequence[Path], python_version: Sequence[int], platform_tag: str) -> str:
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.name.encode())
        digest.update(file.read_bytes())
    digest.update(".".join(str(p) for p in python_version[:2]).encode())
    digest.update(platform_tag.encode())
    return digest.hexdigest()


_LIST_SCRIPT = (
    "import json, importlib.metadata as m\n"
    "print(json.dumps({d.metadata['Name']: d.version for d in m.distributions() if d.metadata['Name']}))"
)


def installed_versions(python: Path, timeout: float = 60.0) -> Dict[str, str]:
    result = subprocess.run([str(python), "-c", _LIST_SCRIPT], capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "could not list installed packages")
    data = json.loads(result.stdout.strip().splitlines()[-1])
    return {normalize_name(name): version for name, version in data.items()}


def find_mismatches(
    requirements: Sequence[Requirement], installed: Dict[str, str]
) -> List[Tuple[Requirement, Optional[str]]]:
    """Return requirements that are missing or installed with a different version."""
    problems = []
    for req in requirements:
        have = installed.get(req.key)
        if have != req.version:
            problems.append((req, have))
    return problems


def validate_imports(python: Path, modules: Dict[str, str], timeout: float = 120.0) -> List[str]:
    """Import each module in the venv interpreter; return friendly names that failed."""
    script = (
        "import importlib, json, sys\n"
        "bad = []\n"
        "for name in sys.argv[1:]:\n"
        "    try:\n"
        "        importlib.import_module(name)\n"
        "    except Exception as exc:\n"
        "        bad.append([name, '%s: %s' % (type(exc).__name__, exc)])\n"
        "print(json.dumps(bad))\n"
    )
    result = subprocess.run(
        [str(python), "-c", script] + list(modules), capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        return ["interpreter error: " + (result.stderr.strip()[-300:] or "unknown")]
    failures = json.loads(result.stdout.strip().splitlines()[-1])
    return ["{} ({})".format(modules.get(name, name), err) for name, err in failures]


def check_linux_system_libraries() -> List[str]:
    """Return human-readable warnings for shared libraries Qt/Panda3D/SoundCard need."""
    needed = [
        ("xcb-cursor", "libxcb-cursor0", "Qt's X11 platform plugin (Qt 6.5+)"),
        ("pulse", "libpulse0", "audio capture through PulseAudio / PipeWire-Pulse"),
        ("GL", "libgl1", "OpenGL rendering"),
        ("EGL", "libegl1", "OpenGL/EGL rendering"),
        ("xkbcommon", "libxkbcommon0", "Qt keyboard handling"),
    ]
    warnings = []
    for lib, package, purpose in needed:
        if ctypes.util.find_library(lib) is None:
            warnings.append("Missing {} (Ubuntu package '{}') — needed for {}.".format(lib, package, purpose))
    return warnings
