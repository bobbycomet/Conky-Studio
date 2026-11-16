#!/bin/bash
# usage: t_wl.sh sway|weston|labwc
export HOME=/root/h XDG_RUNTIME_DIR=/tmp/xdg; mkdir -p $HOME; rm -rf $XDG_RUNTIME_DIR; mkdir -m700 $XDG_RUNTIME_DIR
c=$1
case $c in
 sway)   WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=pixman sway >/tmp/comp.log 2>&1 </dev/null & ;;
 labwc)  WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=pixman labwc >/tmp/comp.log 2>&1 </dev/null & ;;
 weston) weston --backend=headless --socket=wl-test --use-pixman >/tmp/comp.log 2>&1 </dev/null & ;;
esac
CP=$!; sleep 4
sock=$(cd $XDG_RUNTIME_DIR && ls | grep -E '^(wayland-[0-9]+|wl-test)$' | head -1)
export WAYLAND_DISPLAY=$sock
echo "  compositor=$c socket=${sock:-NONE} alive=$(kill -0 $CP 2>/dev/null && echo yes || echo NO)"
env -u DISPLAY QT_DEBUG_PLUGINS=1 /opt/app/AppRun >/tmp/app.log 2>&1 </dev/null &
sleep 12
pgrep -x conky-studio >/dev/null && st=RUNNING || st=DEAD
echo "  app=$st"
grep -oE "(libqwayland[a-z-]*|libqxcb|libqoffscreen)\.so[^ ]* *(\(.*\))?" /tmp/app.log | sort -u | head -3 | sed 's/^/  plugin: /'
grep -iE "could not|failed|error|abort|cannot" /tmp/app.log | grep -v "QThread\|locale" | head -4 | sed 's/^/  log: /'
if [ $c = sway ]; then export SWAYSOCK=$(ls $XDG_RUNTIME_DIR/sway-ipc.* 2>/dev/null | head -1); swaymsg -t get_tree 2>/dev/null | grep -E '"app_id"|"shell"|"name": "Conky' | grep -v null | head -3 | sed 's/^/  sway: /'; fi
pkill -x conky-studio; sleep 1; kill $CP 2>/dev/null; sleep 1
