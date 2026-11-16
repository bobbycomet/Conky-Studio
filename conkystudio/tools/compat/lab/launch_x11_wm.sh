#!/bin/bash
export HOME=/root/h DISPLAY=:97; mkdir -p $HOME
wm=$1
Xvfb :97 -screen 0 1600x1000x24 >/tmp/xvfb.log 2>&1 </dev/null & XP=$!
sleep 2
[ "$wm" != none ] && { $wm >/tmp/wm.log 2>&1 </dev/null & WP=$!; sleep 3; }
/opt/app/AppRun >/tmp/app.log 2>&1 </dev/null &
sleep 11
pgrep -x conky-studio >/dev/null && st=RUNNING || st=DEAD
geo=$(xwininfo -root -tree 2>/dev/null | grep '"Conky Studio v' | head -1 | grep -oE '[0-9]+x[0-9]+\+[0-9-]+\+[0-9-]+' | head -1)
echo "  wm=$wm state=$st geometry=$geo"
pkill -x conky-studio; sleep 1; [ -n "$WP" ] && kill $WP 2>/dev/null; kill $XP 2>/dev/null; rm -f /tmp/.X97-lock; sleep 1
