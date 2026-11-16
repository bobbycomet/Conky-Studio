#!/bin/sh
# Run this on ANY distro (Arch, CachyOS, Fedora, openSUSE, Void, ...) to see what Conky Studio
# detects there, without needing a display. Paste the whole output into an issue/message.
#
#   ./distro_check.sh ./Conky-Studio-x86_64.AppImage
#
APP="${1:-./Conky-Studio-x86_64.AppImage}"
[ -x "$APP" ] || { echo "usage: $0 path/to/Conky-Studio-x86_64.AppImage" >&2; exit 2; }
echo "===== os-release";        cat /etc/os-release 2>/dev/null
echo "===== glibc";             getconf GNU_LIBC_VERSION 2>/dev/null
echo "===== session";           echo "XDG_SESSION_TYPE=${XDG_SESSION_TYPE:-} XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP:-} DISPLAY=${DISPLAY:-} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}"
echo "===== conky";             command -v conky && conky --version 2>&1 | sed -n '1p;/Lua bindings/,/^ *[A-Z]/p'
echo "===== other tools";       for t in curl sensors playerctl smartctl pkexec; do printf "%s: %s\n" "$t" "$(command -v $t || echo MISSING)"; done
echo "===== Conky Studio";      APPIMAGE_EXTRACT_AND_RUN=1 "$APP" --version 2>&1
echo "===== dependency report (JSON)"; APPIMAGE_EXTRACT_AND_RUN=1 "$APP" --deps-report 2>&1
