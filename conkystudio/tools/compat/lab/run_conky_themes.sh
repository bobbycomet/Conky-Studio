#!/bin/bash
# real Conky over generated themes on Xorg(dummy) with /sys; window-level capture; negative control first
export HOME=/root/h; bash /opt/xorg_up.sh 87 >/dev/null; export DISPLAY=:87
echo "conky: $(conky --version | head -1) | cpus=$(cat /sys/devices/system/cpu/present)"
run() { # label dir
  d=$2; for s in $d/scripts/*.sh; do [ -x "$s" ] && timeout 4 "$s" >/dev/null 2>&1; done
  conky -c $d/conky.conf >/tmp/c.out 2>/tmp/c.err </dev/null & CP=$!; sleep 4
  alive=$(kill -0 $CP 2>/dev/null && echo up || { wait $CP; echo "DIED(rc=$?)"; })
  wid=$(xdotool search --class conky-studio 2>/dev/null | head -1); px=-
  if [ -n "$wid" ]; then import -window $wid /tmp/w.png 2>/dev/null; px=$(convert /tmp/w.png -format '%[fx:mean*1000]' info: 2>/dev/null | cut -d. -f1); fi
  kill $CP 2>/dev/null; wait $CP 2>/dev/null
  e=$(cat /tmp/c.err /tmp/c.out | grep -iE "lua|error|attempt|nil value|syntax|more CPUs|cpu_count|failed" | sort -u | head -2 | cut -c1-150 | tr '\n' '|')
  printf "%-22s %-12s win=%-4s content=%-5s %s\n" "$1" "$alive" "${wid:+yes}${wid:-no}" "$px" "${e}"
}
rm -rf /tmp/bad; mkdir /tmp/bad; cp -r /opt/themes/aurora_Simple/. /tmp/bad/
sed -i '0,/^function main_draw()/s//function main_draw()\n  undefined_fn_for_control()/' /tmp/bad/render.lua
run "CONTROL(broken draw)" /tmp/bad
for d in /opt/themes/*/; do n=$(basename $d); [ -f $d/conky.conf ] && run $n ${d%/}; done
pkill -x Xorg
