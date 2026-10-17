# Ubuntu 24.04 desktop-like test environment for Project EVE:
# virtual X display (Xvfb), software OpenGL (Mesa llvmpipe), PulseAudio, Qt's X11 libraries.
# Used by tests/platform/run_linux_tests.sh — see docs/testing.md.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv libpython3.12t64 ca-certificates \
        xvfb xauth x11-utils \
        libgl1 libegl1 libgl1-mesa-dri libglx-mesa0 \
        libxkbcommon0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
        libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 \
        libxcb-xkb1 libxcb-xfixes0 libxrender1 libxi6 libsm6 libice6 \
        libdbus-1-3 libfontconfig1 libfreetype6 libglib2.0-0 \
        pulseaudio pulseaudio-utils libpulse0 \
        binutils \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash eve
USER eve
WORKDIR /home/eve
