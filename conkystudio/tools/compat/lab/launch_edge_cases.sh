#!/bin/bash
export HOME=/root/h; mkdir -p $HOME
Xvfb :96 -screen 0 1280x800x24 >/tmp/xvfb.log 2>&1 </dev/null & XP=$!; sleep 2
run() {  # name, env...
  name=$1; shift
  env -i HOME=$HOME PATH=$PATH "$@" /opt/app/AppRun >/tmp/e.log 2>&1 </dev/null & P=$!
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do sleep 1; kill -0 $P 2>/dev/null || break; done
  if kill -0 $P 2>/dev/null; then r="RUNNING"; pkill -x conky-studio; sleep 1; else wait $P; r="EXITED rc=$?"; fi
  echo "[$name] $r"
  grep -vE "^$|UTF-8|locale\(1\)|for more information" /tmp/e.log | head -3 | cut -c1-150 | sed 's/^/     /'
}
run "A stale WAYLAND_DISPLAY + DISPLAY (expect X11 fallback)" WAYLAND_DISPLAY=wayland-99 XDG_RUNTIME_DIR=/tmp DISPLAY=:96
run "B QT_QPA_PLATFORM=wayland preset, no socket, DISPLAY ok" QT_QPA_PLATFORM=wayland WAYLAND_DISPLAY=wayland-99 XDG_RUNTIME_DIR=/tmp DISPLAY=:96
run "C no DISPLAY / no WAYLAND_DISPLAY (ssh/tty)" 
run "D DISPLAY points at a dead server" DISPLAY=:55
run "E QT_QPA_PLATFORM=xcb preset (baseline)" QT_QPA_PLATFORM=xcb DISPLAY=:96
kill $XP 2>/dev/null; rm -f /tmp/.X96-lock
