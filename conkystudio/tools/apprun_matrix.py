#!/usr/bin/env python3
"""Regression matrix for the AppRun platform-selection logic (no GUI needed).

    python tools/apprun_matrix.py path/to/AppRun

Runs AppRun with CONKY_STUDIO_DRYRUN=1 under many environments (with a real
listening unix socket standing in for a live Wayland compositor and a real stale
path for a dead one) and compares the outcome with the PRE-hardening behaviour.
Exit status 1 if any outcome differs from the expectation table."""
import os, shutil, socket, subprocess, sys, tempfile

apprun = sys.argv[1]
rt = tempfile.mkdtemp(prefix="xdg-")
os.chmod(rt, 0o700)
live = socket.socket(socket.AF_UNIX); live.bind(os.path.join(rt, "wayland-live")); live.listen(1)

def run(env):
    base = {"PATH": "/usr/bin:/bin", "HOME": rt, "CONKY_STUDIO_DRYRUN": "1", "LANG": "en_US.UTF-8"}
    p = subprocess.run(["bash", apprun], env={**base, **env}, capture_output=True, text=True, timeout=20)
    plat = next((l.split("=", 1)[1] for l in p.stdout.splitlines() if l.startswith("QT_QPA_PLATFORM=")), None)
    return p.returncode, plat, p.stderr.strip()

def old_behaviour(env):  # the pre-hardening AppRun, reimplemented
    if env.get("QT_QPA_PLATFORM"): return env["QT_QPA_PLATFORM"]
    return "wayland;xcb" if env.get("WAYLAND_DISPLAY") else "xcb"

R = {"XDG_RUNTIME_DIR": rt}
X = {"DISPLAY": ":0"}
WL = {"WAYLAND_DISPLAY": "wayland-live"}
STALE = {"WAYLAND_DISPLAY": "wayland-dead"}
# name, env, expected (rc, platform), intended_change_vs_old
cases = [
 ("X11 only",                          {**R, **X},                         (0, "xcb"),          False),
 ("Wayland only (live socket)",        {**R, **WL},                        (0, "wayland;xcb"),  False),
 ("Wayland live + X (XWayland)",       {**R, **WL, **X},                   (0, "wayland;xcb"),  False),
 ("preset xcb",                        {**R, **X, "QT_QPA_PLATFORM": "xcb"}, (0, "xcb"),        False),
 ("preset 'wayland;xcb'",              {**R, **WL, "QT_QPA_PLATFORM": "wayland;xcb"}, (0, "wayland;xcb"), False),
 ("preset offscreen, no display",      {**R, "QT_QPA_PLATFORM": "offscreen"}, (0, "offscreen"), False),
 ("preset eglfs, no display",          {**R, "QT_QPA_PLATFORM": "eglfs"},  (0, "eglfs"),        False),
 ("STALE wayland + X",                 {**R, **STALE, **X},                (0, "xcb"),          True),
 ("preset wayland + X, live socket",   {**R, **WL, **X, "QT_QPA_PLATFORM": "wayland"}, (0, "wayland;xcb"), True),
 ("preset wayland + X, no socket",     {**R, **STALE, **X, "QT_QPA_PLATFORM": "wayland"}, (0, "wayland;xcb"), True),
 ("preset wayland, live, no X",        {**R, **WL, "QT_QPA_PLATFORM": "wayland"}, (0, "wayland"), False),
 ("NO display at all (ssh/tty)",       {**R},                              (1, None),           True),
 ("STALE wayland, no X",               {**R, **STALE},                     (1, None),           True),
 ("no XDG_RUNTIME_DIR, X only",        {**X},                              (0, "xcb"),          False),
]
# glibc-floor cases use a fake `getconf` first in PATH
def fake_getconf(ver):
    fake = tempfile.mkdtemp(prefix="fakebin-")      # one directory per case
    path = os.path.join(fake, "getconf")
    open(path, "w").write(f"#!/bin/sh\necho 'glibc {ver}'\n"); os.chmod(path, 0o755)
    return {"PATH": f"{fake}:/usr/bin:/bin"}
cases += [
 ("glibc 2.31 (too old)",              {**R, **X, **fake_getconf("2.31")}, (1, None),           True),
 ("glibc 2.34 (RHEL 9 class)",         {**R, **X, **fake_getconf("2.34")}, (1, None),           True),
 ("glibc 2.35 (exactly the floor)",    {**R, **X, **fake_getconf("2.35")}, (0, "xcb"),          False),
 ("glibc 2.39",                        {**R, **X, **fake_getconf("2.39")}, (0, "xcb"),          False),
 ("glibc 2.9 vs 2.35 (version sort)",  {**R, **X, **fake_getconf("2.9")},  (1, None),           True),
 ("too old but check skipped",         {**R, **X, **fake_getconf("2.31"), "CONKY_STUDIO_SKIP_GLIBC_CHECK": "1"}, (0, "xcb"), False),
]
# --version / --deps-report must work with no display at all (they are answered without Qt)
def run_flag(args, env=None):
    root = tempfile.mkdtemp(prefix="apphome-"); b = os.path.join(root, "usr", "bin", "conky-studio"); os.makedirs(b)
    open(os.path.join(b, "conky-studio"), "w").write('#!/bin/sh\necho "ARGS:$*"\n'); os.chmod(os.path.join(b, "conky-studio"), 0o755)
    shutil.copy(apprun, os.path.join(root, "AppRun"))
    p = subprocess.run(["bash", os.path.join(root, "AppRun"), *args], env={"PATH": "/usr/bin:/bin", "HOME": root, **(env or {})}, capture_output=True, text=True, timeout=20)
    return p.returncode, p.stdout.strip()
extra_fail = []
for flag in ("--version", "--deps-report"):
    rc, out = run_flag([flag])
    ok = rc == 0 and out == f"ARGS:{flag}"
    print(f"{'PASS' if ok else 'FAIL'}  {flag} works with no display at all            rc={rc} out={out!r}")
    if not ok: extra_fail.append(flag)
rc, out = run_flag(["--something-else"])
ok = rc == 1 and "ARGS" not in out
print(f"{'PASS' if ok else 'FAIL'}  other args still need a display                  rc={rc}")
if not ok: extra_fail.append("other-args")
bad = len(extra_fail)
for name, env, (erc, eplat), intended in cases:
    rc, plat, err = run(env)
    ok = (rc, plat) == (erc, eplat)
    changed = (rc == 0 and plat != old_behaviour(env)) or rc != 0
    flag = "" if ok else "  <-- UNEXPECTED"
    note = " [intended change]" if (changed and intended) else (" [UNINTENDED CHANGE]" if changed else "")
    if not ok or (changed and not intended): bad += 1
    print(f"{'PASS' if ok else 'FAIL'}  {name:36s} rc={rc} platform={plat}{note}{flag}")
    if err and rc != 0: print("        ", err.splitlines()[0][:110])
print(f"\n{len(cases)+3-bad}/{len(cases)+3} as expected")
sys.exit(1 if bad else 0)
