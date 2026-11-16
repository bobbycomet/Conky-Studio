#!/bin/bash
# start Xorg(dummy) on :$1 ; prints visual info
D=$1
Xorg :$D -config /etc/X11/dummy.conf -noreset -nolisten tcp +extension RENDER +extension Composite +extension GLX >/tmp/xorg.log 2>&1 </dev/null &
for i in 1 2 3 4 5 6 7 8; do sleep 1; DISPLAY=:$D xdpyinfo >/dev/null 2>&1 && break; done
DISPLAY=:$D xdpyinfo >/dev/null 2>&1 && echo "Xorg :$D UP; 32-bit visuals: $(DISPLAY=:$D xdpyinfo | grep -c 'depth of visual:.*32\|^    depth: *32')  ext: $(DISPLAY=:$D xdpyinfo | grep -cE 'RENDER|Composite')" || { echo "Xorg FAILED"; tail -5 /tmp/xorg.log; }
