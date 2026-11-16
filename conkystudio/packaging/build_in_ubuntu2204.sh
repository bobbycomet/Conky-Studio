#!/usr/bin/env bash
# Build the AppImage inside an Ubuntu 22.04 container (glibc 2.35) from ANY host.
# Run from the repo's packaging/ directory:  ./build_in_ubuntu2204.sh
# Needs docker or podman. Output lands in ../dist/.
# NOTE: written after the AppImage was built+tested in a 22.04 chroot; the
# container wrapper itself has not been run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
RT="$(command -v docker || command -v podman)" || { echo "need docker or podman"; exit 1; }
"$RT" run --rm -v "$PWD":/src -w /src/packaging ubuntu:22.04 bash -c '
  set -e; export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends python3 python3-pip python3-venv python3-dev \
    binutils file curl ca-certificates desktop-file-utils squashfs-tools \
    libgl1 libegl1 libglib2.0-0 libfontconfig1 libdbus-1-3 libxkbcommon0 libxkbcommon-x11-0 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-xfixes0 libxcb-sync1 libxcb-shm0 libxcb-render0 \
    libx11-xcb1 libxrender1 libsm6 libice6 libwayland-client0 libwayland-cursor0 libwayland-egl1
  ./build_appimage.sh'
