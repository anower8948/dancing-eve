#!/usr/bin/env bash
# Project EVE launcher for Ubuntu Linux.
#   ./run-ubuntu.sh                          start EVE (first run installs everything)
#   ./run-ubuntu.sh --install-desktop-entry  add "Project EVE" to the applications menu
# When started from a file manager without a terminal, it reopens itself in one so the
# setup progress and any error messages are visible.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)" || exit 1
SELF="$HERE/run-ubuntu.sh"
cd "$HERE" || exit 1

if [ "${1:-}" = "--install-desktop-entry" ]; then
  apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$apps"
  # Desktop Entry spec: quote the Exec path and escape embedded double quotes/backslashes.
  exec_path=$(printf '%s' "$SELF" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
  cat > "$apps/project-eve.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Project EVE
Comment=Dancing desktop robot companion
Exec="$exec_path"
Terminal=true
Categories=AudioVideo;Audio;
EOF
  echo "Added $apps/project-eve.desktop"
  exit 0
fi

if [ ! -t 1 ] && [ -z "${EVE_IN_TERMINAL:-}" ] && { [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; }; then
  export EVE_IN_TERMINAL=1
  if command -v gnome-terminal >/dev/null 2>&1; then exec gnome-terminal -- "$SELF" "$@"; fi
  if command -v ptyxis >/dev/null 2>&1; then exec ptyxis -- "$SELF" "$@"; fi  # Ubuntu 25.10+ default
  if command -v kgx >/dev/null 2>&1; then exec kgx -- "$SELF" "$@"; fi  # GNOME Console
  if command -v konsole >/dev/null 2>&1; then exec konsole -e "$SELF" "$@"; fi
  if command -v xfce4-terminal >/dev/null 2>&1; then exec xfce4-terminal -x "$SELF" "$@"; fi
  if command -v x-terminal-emulator >/dev/null 2>&1; then exec x-terminal-emulator -e "$SELF" "$@"; fi
  if command -v xterm >/dev/null 2>&1; then exec xterm -e "$SELF" "$@"; fi
  # No terminal emulator: continue headless; output goes to the setup log.
fi

pause_on_error() {
  local code="$1"
  if [ "$code" -ne 0 ] && [ -t 0 ]; then
    echo
    echo "Project EVE stopped with exit code $code. Press Enter to close this window."
    read -r _
  fi
  exit "$code"
}

PY=""
for candidate in python3.12 python3.13 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
    PY="$(command -v "$candidate")"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Project EVE needs Python 3.11, 3.12 or 3.13, and none was found."
  if command -v apt-get >/dev/null 2>&1 && [ -t 0 ]; then
    echo "EVE can install it with:  sudo apt-get install -y python3 python3-venv"
    echo "(sudo is needed because system packages can only be installed by an administrator;"
    echo " the password prompt comes from sudo itself.)"
    printf "Install now? [Y/n] "
    read -r answer
    case "$answer" in
      ""|y|Y|yes|YES)
        sudo apt-get install -y python3 python3-venv || pause_on_error 2
        exec "$SELF" "$@"
        ;;
    esac
  fi
  echo "Install Python 3 (sudo apt install python3 python3-venv) and run ./run-ubuntu.sh again."
  pause_on_error 2
fi

"$PY" "$HERE/setup/bootstrap.py" "$@"
pause_on_error $?
