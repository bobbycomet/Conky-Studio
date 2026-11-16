#!/bin/bash
# usage: t_fuzz.sh <from> <to>
export HOME=/root/h; bash /opt/xorg_up.sh 85 >/dev/null; export DISPLAY=:85
echo "conky: $(conky --version | head -1 | cut -d' ' -f1-2) | cpus=$(cat /sys/devices/system/cpu/present)"
for d in /opt/fuzz/*/; do n=$(basename $d); [ $((10#$n)) -ge $1 ] && [ $((10#$n)) -lt $2 ] || continue
  conky -c $d/conky.conf >/tmp/c.out 2>/tmp/c.err </dev/null & CP=$!; sleep 2.2
  if kill -0 $CP 2>/dev/null; then st=ok; kill $CP; else wait $CP; st="DIED(rc=$?)"; fi; wait $CP 2>/dev/null
  e=$(cat /tmp/c.err /tmp/c.out | grep -iE "lua|error|attempt|nil value|cpu_count|failed|can't|cannot" | grep -v "drawing to" | sort -u | head -1 | cut -c1-110)
  [ "$st" != ok ] || [ -n "$e" ] && printf "%s  %-52s %s %s\n" "$n" "$(cat $d/LABEL)" "$st" "$e"
done
echo "done $1-$2"
pkill -x Xorg
