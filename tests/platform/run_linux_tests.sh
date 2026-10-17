#!/usr/bin/env bash
# Run Project EVE's Linux checks inside the Ubuntu container.
#
#   tests/platform/run_linux_tests.sh            (from the host, needs Docker)
#
# Copies the working tree into the container (your .venv/dist/build are not copied),
# then: run-ubuntu.sh first-time setup, a repeat launch, pytest, audio diagnostics,
# a real PulseAudio monitor capture while audio plays into a virtual sink, a rendered
# smoke test with screenshot, and a PyInstaller build. Results go to tests/platform/out/.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$HERE/../.." && pwd -P)"
OUT="$HERE/out"
mkdir -p "$OUT"
IMAGE=project-eve-ubuntu-test
docker build -q -t "$IMAGE" -f "$HERE/ubuntu.Dockerfile" "$HERE" >/dev/null

docker run --rm -i \
    -v "$ROOT:/src:ro" -v "$OUT:/out" \
    "$IMAGE" bash -s <<'INNER'
set -uo pipefail
step() { printf '\n===== %s =====\n' "$*"; }
cd /home/eve
tar -C /src --exclude=.venv --exclude=.venv.broken --exclude=dist --exclude=build \
    --exclude=.eve-setup --exclude=.git --exclude=tests/platform/out -cf - . | (mkdir -p eve && tar -C eve -xf -)
cd eve

step "virtual display + sound server"
Xvfb :99 -screen 0 1920x1080x24 >/tmp/xvfb.log 2>&1 &
export DISPLAY=:99 XDG_SESSION_TYPE=x11 XDG_RUNTIME_DIR=/tmp/xdg
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
pulseaudio --start --exit-idle-time=-1 --daemonize=yes
sleep 1
pactl load-module module-null-sink sink_name=speakers sink_properties=device.description=Speakers >/dev/null
pactl set-default-sink speakers
pactl info | grep -E "Server Name|Default Sink"

step "first launch: run-ubuntu.sh (setup only)"
time ./run-ubuntu.sh --no-launch </dev/null; echo "exit=$?"

step "second launch (should reuse .venv)"
time ./run-ubuntu.sh --no-launch </dev/null; echo "exit=$?"

step "tests"
.venv/bin/pip install -q -r requirements-dev.txt
.venv/bin/pytest -o addopts="" -q 2>&1 | tail -5

step "audio diagnostics"
PYTHONPATH=src .venv/bin/python -m eve --diagnose-audio

step "real capture from the PulseAudio monitor while audio plays"
PYTHONPATH=src:. .venv/bin/python - <<'PY'
import numpy as np, wave
from tests.fixtures import synthetic_audio as sa
x = sa.beat_track(14, bpm=120, amp=0.6)
w = wave.open("/tmp/beat.wav", "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()); w.close()
PY
(sleep 1; paplay /tmp/beat.wav) &
PYTHONPATH=src .venv/bin/python -m eve --test-capture 12

step "app smoke test (demo, 8 s) with screenshot"
EVE_HOME=/tmp/evehome PYTHONPATH=src .venv/bin/python -m eve --demo --smoke-test 8 --screenshot /out/linux_frame.png 2>/tmp/eve_err.log | tail -25
tail -5 /tmp/eve_err.log

step "renderer fallback: no X display (Qt offscreen) -> headless EGL"
env -u DISPLAY QT_QPA_PLATFORM=offscreen EVE_HOME=/tmp/evehome3 PYTHONPATH=src \
    .venv/bin/python -m eve --demo --smoke-test 4 --screenshot /out/linux_headless.png 2>/dev/null | grep -E '"(frames|avg_fps|renderer|screenshot_saved)"'

step "renderer fallback: forced software rasteriser"
EVE_RENDERER=software EVE_HOME=/tmp/evehome4 PYTHONPATH=src \
    .venv/bin/python -m eve --demo --smoke-test 4 --screenshot /out/linux_software.png 2>/dev/null | grep -E '"(frames|avg_fps|renderer|screenshot_saved)"'

step "PyInstaller build"
.venv/bin/python scripts/build_ubuntu.py >/tmp/build.log 2>&1; echo "build exit=$?"; tail -3 /tmp/build.log
du -sh dist/ProjectEVE 2>/dev/null
EVE_HOME=/tmp/evehome2 dist/ProjectEVE/ProjectEVE --demo --smoke-test 5 2>/dev/null | grep -E '"(frames|avg_fps|renderer)"'
INNER
