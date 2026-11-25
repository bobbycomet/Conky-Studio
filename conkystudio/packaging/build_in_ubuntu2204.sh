#!/usr/bin/env bash
# Build the AppImage inside an Ubuntu 22.04 container (glibc 2.35) from ANY host.
# Run from anywhere:  conkystudio/packaging/build_in_ubuntu2204.sh
# Needs docker or podman. Output lands in <repo root>/dist/.
# Environment passed through to build_appimage.sh: SKIP_TRANSLATIONS.
set -euo pipefail

# This script lives in <repo>/conkystudio/packaging -> repo root is two levels up.
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
RT="$(command -v docker || command -v podman)" || { echo "need docker or podman"; exit 1; }

"$RT" run --rm \
  -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
  -e SKIP_TRANSLATIONS="${SKIP_TRANSLATIONS:-0}" \
  -v "$PWD":/src -w /src/conkystudio/packaging ubuntu:22.04 bash -c '
  set -e; export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends python3 python3-pip python3-venv python3-dev \
    binutils file curl ca-certificates desktop-file-utils squashfs-tools qt6-l10n-tools \
    libgl1 libegl1 libglib2.0-0 libfontconfig1 libdbus-1-3 libxkbcommon0 libxkbcommon-x11-0 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
    libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-xfixes0 libxcb-sync1 libxcb-shm0 libxcb-render0 \
    libx11-xcb1 libxrender1 libsm6 libice6 libwayland-client0 libwayland-cursor0 libwayland-egl1 \
    qt6-l10n-tools
  ./build_appimage.sh'
    libx11-xcb1 libxrender1 libsm6 libice6 libwayland-client0 libwayland-cursor0 libwayland-egl1
  rc=0
  bash ./build_appimage.sh || rc=$?
  # The container runs as root; hand build outputs back to the invoking user
  # (with rootless podman this is a harmless no-op).
  chown -R "$HOST_UID:$HOST_GID" /src/build /src/dist /src/conkystudio/i18n 2>/dev/null || true
  exit $rc'
