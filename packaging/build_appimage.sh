#!/usr/bin/env bash
# Builds Conky-Studio-x86_64.AppImage from source. 
# Rename file to version number, change version number in conkystudio/update_checker.py
# Requirements on the BUILD machine (not the machine that will run the
# AppImage -- that one needs nothing but FUSE, same as any AppImage):
#   - Python 3.10+, pip
#   - pip install pyinstaller PyQt6
#   - appimagetool (downloaded automatically below if missing)
#
# Usage:
#   cd packaging && ./build_appimage.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$REPO_ROOT/build"
DIST_DIR="$REPO_ROOT/dist"
APPDIR="$BUILD_DIR/AppDir"

echo "==> Cleaning previous build artifacts"
rm -rf "$BUILD_DIR" "$DIST_DIR" "$APPDIR"

echo "==> Freezing Conky Studio with PyInstaller"
cd "$REPO_ROOT"
pyinstaller --name conky-studio --windowed --noconfirm \
    --contents-directory . \
    --paths . \
    conkystudio/__main__.py

PLATFORM_PLUGIN_DIR="$DIST_DIR/conky-studio/PyQt6/Qt6/plugins/platforms"
if [[ -f "$PLATFORM_PLUGIN_DIR/libqwayland.so" ]]; then
    echo "==> Wayland Qt plugin found: OK"
else
    echo "==> WARNING: libqwayland.so not found under $PLATFORM_PLUGIN_DIR"
    echo "    AppRun will still fall back to X11/XCB, but native Wayland won't work."
    echo "    If your PyQt6 install doesn't ship it, try: pip install PyQt6-Qt6"
fi

echo "==> Assembling AppDir"
mkdir -p "$APPDIR/usr/bin"
cp -r "$DIST_DIR/conky-studio" "$APPDIR/usr/bin/conky-studio"
cp "$SCRIPT_DIR/conky-studio.desktop" "$APPDIR/conky-studio.desktop"
cp "$SCRIPT_DIR/icon_256.png" "$APPDIR/conky-studio.png"

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
mkdir -p "$DIST_DIR"
ARCH=x86_64 "$APPIMAGETOOL_BIN" "$APPDIR" "$DIST_DIR/Conky-Studio-x86_64.AppImage" \
    || ARCH=x86_64 "$APPIMAGETOOL_BIN" --appimage-extract-and-run "$APPDIR" "$DIST_DIR/Conky-Studio-x86_64.AppImage"

echo "==> Done: $DIST_DIR/Conky-Studio-x86_64.AppImage"
ls -lh "$DIST_DIR/Conky-Studio-x86_64.AppImage"
