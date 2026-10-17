#!/bin/bash
# Project EVE launcher for macOS — double-click in Finder.
# First run: creates .venv, installs pinned dependencies with a progress display, launches EVE.
# Later runs: reuse the environment and start EVE immediately.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)" || exit 1
cd "$HERE" || exit 1

pause_on_error() {
  local code="$1"
  if [ "$code" -ne 0 ] && [ -t 0 ]; then
    echo
    echo "Project EVE stopped with exit code $code. Press Return to close this window."
    read -r _
  fi
  exit "$code"
}

# Any Python >= 3.8 can run the bootstrap; it then selects a supported interpreter (3.11–3.13)
# for the virtual environment. /usr/bin/python3 is tried last because, without the Xcode
# Command Line Tools, it opens an installer dialog instead of running.
PY=""
for candidate in python3.12 python3.13 python3.11 \
                 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.11 \
                 /usr/local/bin/python3.12 /usr/local/bin/python3.13 /usr/local/bin/python3.11 \
                 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
                 /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
                 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
                 python3 /usr/bin/python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
    PY="$(command -v "$candidate")"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Project EVE needs Python 3.11, 3.12 or 3.13, and none was found."
  if command -v brew >/dev/null 2>&1; then
    echo "Homebrew is installed. EVE can run:  brew install python@3.12"
    printf "Install Python 3.12 with Homebrew now? [Y/n] "
    read -r answer
    case "$answer" in
      ""|y|Y|yes|YES)
        brew install python@3.12 || pause_on_error 2
        exec "$0" "$@"
        ;;
    esac
  fi
  echo "Please install Python 3.12 from https://www.python.org/downloads/macos/"
  echo "and then double-click run.command again."
  pause_on_error 2
fi

"$PY" "$HERE/setup/bootstrap.py" "$@"
pause_on_error $?
