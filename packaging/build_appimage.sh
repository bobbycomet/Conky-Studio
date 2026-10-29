#!/usr/bin/env bash
# Builds Conky-Studio-x86_64.AppImage from source.
#
# Release checklist: bump APP_VERSION in conkystudio/update_checker.py (and
# __version__ in conkystudio/__init__.py) BEFORE building. The output file name
# must stay Conky-Studio-x86_64.AppImage -- update_checker.py matches that
# exact asset name on the GitHub release.
#
# GLIBC / COMPATIBILITY
#   An AppImage runs on any distro whose glibc is >= the glibc it was BUILT
#   against, because PyInstaller bundles the build machine's libs. So build on
#   the OLDEST distro you want to support: Ubuntu 22.04 LTS (glibc 2.35) is the
#   oldest Ubuntu LTS still in standard support. This script refuses to run on
#   anything newer unless ALLOW_NEWER_GLIBC=1 (use build_in_ubuntu2204.sh to
#   build in a 22.04 container from any host).
#
# Build-machine requirements (the machine RUNNING the AppImage needs only FUSE
# -- or none, see README note -- same as any AppImage):
#   - Ubuntu 22.04: python3 python3-venv python3-pip binutils curl file
#                   libxcb-cursor0 libxkbcommon-x11-0 libxcb-xinerama0 + the
#                   usual xcb libs (see build_in_ubuntu2204.sh for the full list)
#
# Usage:
#   cd packaging && ./build_appimage.sh
#
set -euo pipefail

MAX_GLIBC="2.35"    # Ubuntu 22.04 LTS

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$REPO_ROOT/build"
DIST_DIR="$REPO_ROOT/dist"
APPDIR="$BUILD_DIR/AppDir"
OUT_NAME="Conky-Studio-x86_64.AppImage"

ver_gt() { [[ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n1)" == "$1" && "$1" != "$2" ]]; }

# NB: no `| head`/`grep -q`/`awk exit` on a producer under pipefail -- the producer
# gets SIGPIPE (exit 141) and `set -e` kills the script silently.
HOST_GLIBC="$(ldd --version 2>&1 | sed -n '1s/.* //p')"
echo "==> Build host glibc: $HOST_GLIBC (target floor: $MAX_GLIBC)"
if ver_gt "$HOST_GLIBC" "$MAX_GLIBC" && [[ "${ALLOW_NEWER_GLIBC:-0}" != "1" ]]; then
    echo "ERROR: this machine's glibc ($HOST_GLIBC) is newer than $MAX_GLIBC; the AppImage would not run on"
    echo "       Ubuntu 22.04. Build on 22.04 or run ./build_in_ubuntu2204.sh. (Override: ALLOW_NEWER_GLIBC=1)"
    exit 1
fi

echo "==> Cleaning previous build artifacts"
rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

echo "==> Creating build venv + installing PyQt6 / PyInstaller"
python3 -m venv "$BUILD_DIR/venv"
# shellcheck disable=SC1091
source "$BUILD_DIR/venv/bin/activate"
pip install -q --upgrade pip
pip install -q PyQt6 pyinstaller

echo "==> Freezing Conky Studio with PyInstaller"
cd "$REPO_ROOT"
pyinstaller --name conky-studio --windowed --noconfirm \
    --distpath "$DIST_DIR" --workpath "$BUILD_DIR/pyi" --specpath "$BUILD_DIR" \
    --contents-directory . \
    --paths "$REPO_ROOT" \
    --collect-submodules conkystudio \
    "$REPO_ROOT/conkystudio/__main__.py"

BUNDLE="$DIST_DIR/conky-studio"

PLATFORM_PLUGIN_DIR="$BUNDLE/PyQt6/Qt6/plugins/platforms"
if [[ -f "$PLATFORM_PLUGIN_DIR/libqwayland-generic.so" || -f "$PLATFORM_PLUGIN_DIR/libqwayland.so" ]]; then
    echo "==> Wayland Qt plugin found: OK"
else
    echo "==> WARNING: no Qt Wayland platform plugin under $PLATFORM_PLUGIN_DIR"
    echo "    AppRun will still fall back to X11/XCB, but native Wayland won't work."
fi

# Qt >= 6.5's xcb plugin hard-requires libxcb-cursor, which a stock Ubuntu 22.04
# desktop does NOT ship. Make sure it travels inside the bundle.
if [[ -z "$(find "$BUNDLE" -name 'libxcb-cursor.so*' -print -quit)" ]]; then
    SRC="$(ldconfig -p | awk '/libxcb-cursor\.so\.0 / && !f {print $NF; f=1}')"
    if [[ -n "$SRC" ]]; then
        echo "==> Bundling $SRC"
        cp -L "$SRC" "$BUNDLE/"
    else
        echo "ERROR: libxcb-cursor0 is not installed on the build machine (apt install libxcb-cursor0)"; exit 1
    fi
fi

echo "==> Checking bundled binaries against glibc $MAX_GLIBC"
FAIL=0
while IFS= read -r f; do
    need="$(objdump -T "$f" 2>/dev/null | grep -oE 'GLIBC_[0-9]+\.[0-9]+(\.[0-9]+)?' | sed 's/GLIBC_//' | sort -V | tail -n1 || true)"
    if [[ -n "$need" ]] && ver_gt "$need" "$MAX_GLIBC"; then
        echo "   TOO NEW (needs glibc $need): ${f#"$BUNDLE"/}"; FAIL=1
    fi
done < <(find "$BUNDLE" -type f \( -name '*.so' -o -name '*.so.*' -o -perm -u+x \) -exec sh -c 'file -b "$1" | grep -q "^ELF" && echo "$1"' _ {} \;)
[[ $FAIL -eq 0 ]] || { echo "ERROR: bundle needs a newer glibc than $MAX_GLIBC"; exit 1; }
echo "   OK -- nothing in the bundle needs glibc > $MAX_GLIBC"

echo "==> Assembling AppDir"
mkdir -p "$APPDIR/usr/bin"
cp -r "$BUNDLE" "$APPDIR/usr/bin/conky-studio"
cp "$SCRIPT_DIR/conky-studio.desktop" "$APPDIR/conky-studio.desktop"
cp "$SCRIPT_DIR/icon_256.png" "$APPDIR/conky-studio.png"
cp "$SCRIPT_DIR/icon_256.png" "$APPDIR/.DirIcon"
for s in 16 32 48 64 128 256; do
    if [[ -f "$SCRIPT_DIR/icon_$s.png" ]]; then
        mkdir -p "$APPDIR/usr/share/icons/hicolor/${s}x${s}/apps"
        cp "$SCRIPT_DIR/icon_$s.png" "$APPDIR/usr/share/icons/hicolor/${s}x${s}/apps/conky-studio.png"
    fi
done

cat > "$APPDIR/AppRun" << 'APPRUN_EOF'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"

# --- Qt platform: use native Wayland when available, X11 otherwise ---
# Qt understands a semicolon-separated fallback list, so "wayland;xcb" tries
# Wayland first and drops to XCB automatically if the Wayland plugin can't
# connect (e.g. running under a plain X11 session, or over SSH/X-forwarding).
# Respect an explicit QT_QPA_PLATFORM from the user's environment if set.
if [[ -z "${QT_QPA_PLATFORM:-}" ]]; then
    if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        export QT_QPA_PLATFORM="wayland;xcb"
    else
        export QT_QPA_PLATFORM="xcb"
    fi
fi
# Make sure Qt can find the platform plugins PyInstaller bundled, regardless
# of what else is on the host (some distros set QT_PLUGIN_PATH globally and
# point it at a system Qt install that doesn't match our bundled version).
export QT_PLUGIN_PATH="${HERE}/usr/bin/conky-studio/PyQt6/Qt6/plugins"
export QT_QPA_PLATFORM_PLUGIN_PATH="${HERE}/usr/bin/conky-studio/PyQt6/Qt6/plugins/platforms"

# --- Self-integrate into the host's app menu + icon theme ---
# A bare AppImage has no icon/menu entry until something registers it, and
# not every system runs an integration daemon (appimaged / AppImageLauncher).
# We don't just point the .desktop file at wherever this AppImage currently
# sits ($APPIMAGE) -- if the user moves or renames that file later, the
# shortcut breaks ("Could not find the program"). Instead, install a stable
# copy under ~/Applications and always point Exec= there. The original
# download/build output can then be moved or deleted freely after first run.
if [[ -n "${APPIMAGE:-}" ]]; then
    DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
    APPS_DIR="$DATA_HOME/applications"
    ICON_DIR="$DATA_HOME/icons/hicolor/256x256/apps"
    INSTALL_DIR="$HOME/Applications"
    INSTALL_DEST="$INSTALL_DIR/conky-studio.AppImage"
    DESKTOP_DEST="$APPS_DIR/conky-studio.desktop"
    ICON_DEST="$ICON_DIR/conky-studio.png"

    {
        mkdir -p "$INSTALL_DIR" "$APPS_DIR" "$ICON_DIR"

        SRC_REAL="$(readlink -f "$APPIMAGE" 2>/dev/null || echo "$APPIMAGE")"
        DEST_REAL="$(readlink -f "$INSTALL_DEST" 2>/dev/null || echo "$INSTALL_DEST")"

        # Only copy if we're not already running the installed copy, and
        # only when needed (missing, or this run is a newer build).
        if [[ "$SRC_REAL" != "$DEST_REAL" ]] \
           && { [[ ! -f "$INSTALL_DEST" ]] || [[ "$APPIMAGE" -nt "$INSTALL_DEST" ]]; }; then
            cp -f "$APPIMAGE" "$INSTALL_DEST" && chmod +x "$INSTALL_DEST"
        fi

        if [[ -f "$INSTALL_DEST" ]] \
           && ! grep -q "^Exec=\"$INSTALL_DEST\"" "$DESKTOP_DEST" 2>/dev/null; then
            cp -f "$HERE/conky-studio.png" "$ICON_DEST"
            sed -e "s|^Exec=.*|Exec=\"$INSTALL_DEST\" %U|" \
                -e "s|^Icon=.*|Icon=$ICON_DEST|" \
                "$HERE/conky-studio.desktop" > "$DESKTOP_DEST.tmp" \
                && mv -f "$DESKTOP_DEST.tmp" "$DESKTOP_DEST"
            command -v update-desktop-database >/dev/null 2>&1 \
                && update-desktop-database "$APPS_DIR" >/dev/null 2>&1
            command -v gtk-update-icon-cache >/dev/null 2>&1 \
                && gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1
        fi
    } 2>/dev/null || true
fi

exec "${HERE}/usr/bin/conky-studio/conky-studio" "$@"
APPRUN_EOF
chmod +x "$APPDIR/AppRun"

echo "==> Fetching appimagetool if needed"
APPIMAGETOOL="$BUILD_DIR/appimagetool.AppImage"
if ! command -v appimagetool >/dev/null 2>&1 && [[ ! -x "$APPIMAGETOOL" ]]; then
    curl -fsSL -o "$APPIMAGETOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "$APPIMAGETOOL"
fi
APPIMAGETOOL_BIN="$(command -v appimagetool || echo "$APPIMAGETOOL")"

echo "==> Building AppImage"
# APPIMAGE_EXTRACT_AND_RUN lets appimagetool itself run without FUSE (containers/CI).
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL_BIN" "$APPDIR" "$DIST_DIR/$OUT_NAME"

echo "==> Done: $DIST_DIR/$OUT_NAME"
ls -lh "$DIST_DIR/$OUT_NAME"
