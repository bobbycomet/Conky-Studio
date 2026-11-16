#!/usr/bin/env python3
"""Tests for conkystudio.manager.autostart (run from the repo root, any Linux)."""
import os, re, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
home = tempfile.mkdtemp(prefix="as-home-"); os.environ["HOME"] = home; os.environ["XDG_CONFIG_HOME"] = os.path.join(home, ".config")
from conkystudio.manager import autostart as A
fails = []
def check(name, cond, detail=""):
    if not cond: fails.append(f"{name}: {detail}")

def make_theme(name, root=None, start=True):
    d = os.path.join(root or tempfile.mkdtemp(prefix="th-"), name); os.makedirs(d)
    if start:
        open(os.path.join(d, "start.sh"), "w").write(f'#!/bin/sh\nprintf "%s|%s" "$0" "$#" > "$(dirname "$0")/ran"\n'); os.chmod(os.path.join(d, "start.sh"), 0o755)
    return d

def spec_unquote_exec(value):
    """Decode a Desktop Entry Exec value the way a spec-following launcher does -> argv[0]."""
    v = re.sub(r"\\(.)", lambda m: {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}.get(m.group(1), "\\" + m.group(1)), value)  # string-value level
    if v.startswith('"'):
        out, i = "", 1
        while i < len(v) and v[i] != '"':
            if v[i] == "\\" and i + 1 < len(v): i += 1
            out += v[i]; i += 1
        return out.replace("%%", "%")
    return v.split(" ")[0].replace("%%", "%")

NAMES = ["plain", "with space", "dollar$HOME", "quote'single", 'quote"double', "back`tick`", "percent%d%%",
         "ünïcode-テーマ", "semi;colon&amp", "paren(thesis)", "ends-with-backslash\\", "-leading-dash", "x" * 120]
roots = [tempfile.mkdtemp(prefix="th root-")]            # a root path with a space too
for n in NAMES:
    d = make_theme(n, roots[0])
    r = A.enable(d, name=n, delay=0)
    check(f"enable[{n!r}]", r.ok, r.message)
    if not r.ok: continue
    kv = A._read_kv(r.entry_path)
    ex = spec_unquote_exec(kv["Exec"])
    check(f"exec points at our launcher [{n!r}]", ex == r.script_path, f"{ex!r} != {r.script_path!r}")
    check(f"launcher perms [{n!r}]", oct(os.stat(r.script_path).st_mode & 0o777) == "0o755")
    p = subprocess.run([ex], capture_output=True, text=True, timeout=20)
    ran = os.path.join(d, "ran")
    check(f"launcher really starts theme [{n!r}]", p.returncode == 0 and os.path.isfile(ran), p.stderr[:120])
    if os.path.isfile(ran): check(f"started the right start.sh [{n!r}]", open(ran).read().startswith(os.path.join(d, "start.sh") + "|0"), open(ran).read())
    check(f"is_enabled [{n!r}]", A.is_enabled(d))
    if shutil.which("desktop-file-validate"):
        v = subprocess.run(["desktop-file-validate", r.entry_path], capture_output=True, text=True)
        check(f"desktop-file-validate [{n!r}]", v.returncode == 0 and not v.stdout.strip(), v.stdout + v.stderr)

# ids are stable + unique
d1 = make_theme("same", tempfile.mkdtemp()); d2 = make_theme("same", tempfile.mkdtemp())
check("same folder name, different root -> different id", A.entry_id(d1) != A.entry_id(d2))
check("id stable", A.entry_id(d1) == A.entry_id(d1))

# idempotent enable, changing delay, disable, idempotent disable
d = make_theme("cycle")
A.enable(d, delay=3); A.enable(d, delay=9)
check("re-enable updates delay", A.configured_delay(d) == 9)
check("one entry only", sum(1 for e in A.list_entries() if e["theme_path"] == d) == 1)
check("disable removes both files", A.disable(d).ok and not os.path.exists(A.entry_path(d)) and not os.path.exists(A.script_path(d)))
check("disable idempotent", A.disable(d).ok)
check("not enabled after disable", not A.is_enabled(d))
# delay clamping / junk
for raw, want in ((-5, 0), (9999, A.MAX_DELAY), ("abc", A.DEFAULT_DELAY), (None, A.DEFAULT_DELAY), (7, 7)):
    A.enable(d, delay=raw); check(f"delay {raw!r} -> {want}", A.configured_delay(d) == want, A.configured_delay(d)); A.disable(d)
# refusals
check("no start.sh refused", not A.enable(make_theme("nostart", start=False)).ok)
bad = os.path.join(tempfile.mkdtemp(), "evil\nExec=/bin/rm -rf ~"); os.makedirs(bad); open(os.path.join(bad, "start.sh"), "w").write("#!/bin/sh\n")
check("newline in path refused (injection)", not A.enable(bad).ok and not any("evil" in e["entry"] for e in A.list_entries()))
# orphan pruning
d = make_theme("orphan"); A.enable(d); shutil.rmtree(d)
check("orphan detected", any(e["theme_path"] == d and not e["theme_exists"] for e in A.list_entries()))
check("orphan pruned", A.entry_path(d) in A.prune_orphans() and not os.path.exists(A.entry_path(d)))
# does not touch other autostart entries
other = os.path.join(A.autostart_dir(), "firefox.desktop"); open(other, "w").write("[Desktop Entry]\nType=Application\nName=x\nExec=x\n")
keep = make_theme("keep"); A.enable(keep); A.prune_orphans(); A.disable(keep)
check("leaves foreign autostart entries alone", os.path.isfile(other))
# session hints
S = "/tmp/x y.sh"
for desk, expect in (("GNOME", ""), ("KDE", ""), ("XFCE", ""), ("ubuntu:GNOME", ""), ("X-Cinnamon", ""), ("", ""), ("COSMIC", ""),
                     ("sway", "exec '/tmp/x y.sh'"), ("i3", "exec --no-startup-id"), ("Hyprland", "exec-once"), ("openbox", "autostart"),
                     ("niri", "spawn-at-startup"), ("weirdwm", "may not process")):
    h = A.session_hint(S, desk)
    check(f"hint[{desk!r}]", (h == "") if expect == "" else (expect in h), h)
print(f"{'FAIL' if fails else 'PASS'}: {len(fails)} failure(s)  ({len(NAMES)} awkward theme names exercised)")
[print("  -", f) for f in fails]; sys.exit(1 if fails else 0)
