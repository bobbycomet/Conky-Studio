#!/bin/bash
export HOME=/root/h DISPLAY=:99; mkdir -p $HOME
Xvfb :99 -screen 0 1600x1000x24 >/tmp/xvfb.log 2>&1 </dev/null & XP=$!
sleep 2
/opt/app/AppRun >/tmp/app.log 2>&1 </dev/null &
sleep 12
if pgrep -x conky-studio >/dev/null; then st=RUNNING; else st=DEAD; fi
w=$(xwininfo -root -tree 2>/dev/null | grep -o '"Conky Studio v[0-9.]*"' | head -1)
echo "  state=$st window=$w"
grep -vE "^$|UTF-8|locale|for more information" /tmp/app.log | head -4 | sed 's/^/  log: /'
pkill -x conky-studio; sleep 1; kill $XP 2>/dev/null; rm -f /tmp/.X99-lock
