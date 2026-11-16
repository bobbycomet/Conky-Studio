#!/usr/bin/env python3
"""Tests for conkystudio.hardware.deps: distro detection, commands, notes, helper safety.

os-release fixtures are written from knowledge of each distro's real file format, NOT
captured from live installs. Run from the repo root:  python tools/compat/deps_matrix.py"""
import os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from conkystudio.hardware import deps, discovery

def osr(**kw): return {k.upper(): v for k, v in kw.items()}
FIX = {
 "ubuntu":       (osr(id="ubuntu", id_like="debian", pretty_name="Ubuntu 24.04.3 LTS"), "debian"),
 "debian":       (osr(id="debian", pretty_name="Debian GNU/Linux 13 (trixie)"), "debian"),
 "linuxmint":    (osr(id="linuxmint", id_like="ubuntu debian", pretty_name="Linux Mint 22"), "debian"),
 "pop":          (osr(id="pop", id_like="ubuntu debian", pretty_name="Pop!_OS 24.04"), "debian"),
 "zorin":        (osr(id="zorin", id_like="ubuntu debian", pretty_name="Zorin OS 17"), "debian"),
 "elementary":   (osr(id="elementary", id_like="ubuntu", pretty_name="elementary OS 8"), "debian"),
 "kali":         (osr(id="kali", id_like="debian", pretty_name="Kali GNU/Linux Rolling"), "debian"),
 "fedora":       (osr(id="fedora", pretty_name="Fedora Linux 43 (Workstation Edition)"), "fedora"),
 "nobara":       (osr(id="nobara", id_like="rhel centos fedora", pretty_name="Nobara Linux 43"), "fedora"),
 "rocky":        (osr(id="rocky", id_like="rhel centos fedora", pretty_name="Rocky Linux 10"), "fedora"),
 "arch":         (osr(id="arch", pretty_name="Arch Linux"), "arch"),
 "manjaro":      (osr(id="manjaro", id_like="arch", pretty_name="Manjaro Linux"), "arch"),
 "endeavouros":  (osr(id="endeavouros", id_like="arch", pretty_name="EndeavourOS"), "arch"),
 "cachyos":      (osr(id="cachyos", id_like="arch", pretty_name="CachyOS"), "arch"),
 "garuda":       (osr(id="garuda", id_like="arch", pretty_name="Garuda Linux"), "arch"),
 "tumbleweed":   (osr(id="opensuse-tumbleweed", id_like="opensuse suse", pretty_name="openSUSE Tumbleweed"), "opensuse"),
 "leap":         (osr(id="opensuse-leap", id_like="suse opensuse", pretty_name="openSUSE Leap 16.0"), "opensuse"),
 "void":         (osr(id="void", pretty_name="Void Linux"), "void"),
 "alpine":       (osr(id="alpine", pretty_name="Alpine Linux v3.22"), "alpine"),
 "gentoo":       (osr(id="gentoo", pretty_name="Gentoo Linux"), "gentoo"),
 "nixos":        (osr(id="nixos", pretty_name="NixOS 25.11"), "nixos"),
 "mystery":      (osr(id="weirdos", pretty_name="Weird OS"), "unknown"),
 "empty":        ({}, "unknown"),
}
fails = []
def check(name, cond, detail=""):
    if not cond: fails.append(f"{name}: {detail}")
    return cond

ALL_MISSING = lambda b: None          # nothing installed
NOTHING = dict(which=ALL_MISSING, conky_probe=lambda p: "", helper=(False, False), euid=1000)

# 1. family detection for every fixture
for name, (data, fam) in FIX.items():
    r = deps.build_report(os_release=data, exists=lambda p: False, **NOTHING)
    check(f"family[{name}]", r.family == fam, f"got {r.family}")

# 2. commands for 'everything missing' on every installable family
EXPECT_REQ = {
 "debian":   "sudo apt update && sudo apt install -y conky-all",
 "fedora":   "sudo dnf install -y conky",
 "arch":     "sudo pacman -S --needed conky",
 "opensuse": "sudo zypper install conky",
 "void":     "sudo xbps-install -S conky",
}
for fam, want in EXPECT_REQ.items():
    sample = next(d for d, f in FIX.values() if f == fam)
    r = deps.build_report(os_release=sample, exists=lambda p: False, **NOTHING)
    check(f"cmd-required[{fam}]", r.command({i.key for i in r.missing_required}) == want,
          r.command({i.key for i in r.missing_required}))
    allc = r.command()
    check(f"cmd-all[{fam}]", allc.startswith(want.rsplit(" conky", 1)[0]) and "curl" in allc and "playerctl" in allc and "smartmontools" in allc, allc)
r = deps.build_report(os_release=FIX["tumbleweed"][0], exists=lambda p: False, **NOTHING)
check("opensuse lm-sensors is 'sensors'", " sensors" in r.command(), r.command())
r = deps.build_report(os_release=FIX["fedora"][0], exists=lambda p: False, **NOTHING)
check("fedora lm_sensors", "lm_sensors" in r.command(), r.command())

# 3. root user: no sudo
r = deps.build_report(os_release=FIX["ubuntu"][0], exists=lambda p: False, which=ALL_MISSING, conky_probe=lambda p: "", helper=(False, False), euid=0)
check("root has no sudo", "sudo" not in r.command(), r.command())

# 4. immutable systems
imm = {
 "silverblue(ostree flag)": (FIX["fedora"][0], lambda p: p == "/run/ostree-booted"),
 "bazzite":  (osr(id="bazzite", id_like="fedora", variant_id="kinoite", pretty_name="Bazzite"), lambda p: False),
 "steamos":  (osr(id="steamos", id_like="arch", pretty_name="SteamOS"), lambda p: False),
 "microos":  (osr(id="opensuse-microos", id_like="suse opensuse", pretty_name="openSUSE MicroOS"), lambda p: False),
}
for name, (data, ex) in imm.items():
    r = deps.build_report(os_release=data, exists=ex, **NOTHING)
    check(f"immutable[{name}]", r.immutable and not r.can_auto_install, f"imm={r.immutable} auto={r.can_auto_install}")
    check(f"immutable-note[{name}]", any("immutable" in n for n in r.notes), r.notes)
r = deps.build_report(os_release=FIX["fedora"][0], exists=lambda p: p == "/run/ostree-booted", **NOTHING)
check("rpm-ostree command", r.command().startswith("rpm-ostree install conky"), r.command())
r = deps.build_report(os_release=imm["steamos"][0], exists=lambda p: False, **NOTHING)
check("steamos gives no unsafe command", r.command() == "", r.command())

# 5. Conky present but without Lua-Cairo; and unknown output never nags
CAIRO = "conky 1.19.6\n Lua bindings:\n  * Cairo\n  * Imlib2\n"
STD   = "conky 1.19.6\n X11:\n  * Xinerama\n"
def probe(out): return dict(which=lambda b: "/usr/bin/" + b, conky_probe=lambda p: out, helper=(False, False), euid=1000)
r = deps.build_report(os_release=FIX["ubuntu"][0], exists=lambda p: False, **probe(STD))
c = next(i for i in r.items if i.key == "conky-lua-cairo")
check("debian no-cairo -> conky-all", c.state == "no-cairo" and c.packages == ("conky-all",), (c.state, c.packages))
check("debian no-cairo command", "conky-all" in r.command(), r.command())
r = deps.build_report(os_release=FIX["arch"][0], exists=lambda p: False, **probe(STD))
c = next(i for i in r.items if i.key == "conky-lua-cairo")
check("arch no-cairo: no guessed package", c.state == "no-cairo" and c.packages == (), (c.state, c.packages))
check("arch no-cairo: explanatory note", any("Lua-Cairo" in n for n in r.notes) and any("AUR" in n for n in r.notes), r.notes)
check("arch no-cairo: no command", r.command() == "", r.command())
r = deps.build_report(os_release=FIX["ubuntu"][0], exists=lambda p: False, **probe(CAIRO))
check("all good -> nothing missing", not r.missing and r.signature == "", r.signature)
r = deps.build_report(os_release=FIX["ubuntu"][0], exists=lambda p: False, **probe(""))
check("unreadable conky output -> never nag", next(i for i in r.items if i.key == "conky-lua-cairo").state == "unknown" and not r.missing)

# 6. auto-install capability
def auto(fam_key, pk=True):
    r = deps.build_report(os_release=FIX[fam_key][0], exists=lambda p: False, which=(lambda b: "/usr/bin/pkexec" if (b == "pkexec" and pk) else None), conky_probe=lambda p: "", helper=(False, False), euid=1000)
    return r.can_auto_install
check("auto: ubuntu+pkexec", auto("ubuntu") is True)
check("auto: ubuntu without pkexec", auto("ubuntu", pk=False) is False)
check("auto: alpine/gentoo/nixos/unknown refused", not any(auto(k) for k in ("alpine", "gentoo", "nixos", "mystery")))

# 7. helper script: syntax, allowlist == python tables, refuses everything else
script = deps.helper_script()
with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f: f.write(script); sp = f.name
check("helper sh -n", subprocess.run(["sh", "-n", sp]).returncode == 0)
sh_map = set(re.findall(r'^\s+([a-z-]+):([a-z]+)\) echo "([^"]+)"', script, re.M))
py_map = {(req.key, fam, " ".join(names)) for req in deps.REQUIREMENTS for fam, names in req.packages.items() if fam in deps.INSTALLABLE_FAMILIES}
check("helper allowlist == python tables", sh_map == py_map, f"only-sh={sh_map - py_map} only-py={py_map - sh_map}")
check("helper family map covers installable families", all(f"family={f}" in script for f in deps.INSTALLABLE_FAMILIES))
def run_helper(env_id, *args, as_root_stub=True):
    d = tempfile.mkdtemp(); open(os.path.join(d, "os-release"), "w").write(f"ID={env_id}\n")
    s = script.replace("/etc/os-release", os.path.join(d, "os-release")).replace('[ "$(id -u)" -ne 0 ]', "false")
    s = s.replace("exec apt-get", "echo WOULD-RUN apt-get").replace("apt-get update ||", "echo WOULD-RUN apt-get update ||")
    for m in ("dnf", "pacman", "zypper", "xbps-install"): s = s.replace(f"exec {m}", f"echo WOULD-RUN {m}")
    return subprocess.run(["sh", "-c", s, "helper", *args], capture_output=True, text=True)
p = run_helper("ubuntu", "install", "conky-lua-cairo", "curl")
check("helper: ubuntu install", "WOULD-RUN apt-get install -y conky-all curl" in p.stdout, p.stdout + p.stderr)
p = run_helper("arch", "install", "lm-sensors")
check("helper: arch lm-sensors -> lm_sensors", "WOULD-RUN pacman -S --needed --noconfirm lm_sensors" in p.stdout, p.stdout + p.stderr)
p = run_helper("opensuse-tumbleweed", "install", "lm-sensors")
check("helper: opensuse lm-sensors -> sensors", "zypper --non-interactive install sensors" in p.stdout, p.stdout)
for evil in ("bash", "curl; touch /tmp/pwned", "$(id)", "--help", "conky-all", "../curl", ""):
    p = run_helper("ubuntu", "install", evil)
    check(f"helper refuses {evil!r}", p.returncode != 0 and "WOULD-RUN" not in p.stdout and not os.path.exists("/tmp/pwned"), p.stdout + p.stderr)
p = run_helper("ubuntu", "remove", "curl");   check("helper refuses non-install verb", p.returncode != 0 and "WOULD-RUN" not in p.stdout)
p = run_helper("alpine", "install", "curl");   check("helper refuses unsupported distro", p.returncode != 0 and "WOULD-RUN" not in p.stdout)

# 8. argv builders
for bad in (["curl; rm -rf /"], ["bash"], [], ["--help"]):
    try: deps.install_argv(bad, use_helper=True); check(f"install_argv rejects {bad}", False, "accepted")
    except ValueError: pass
a = deps.install_argv(["curl"], use_helper=True);  check("argv helper mode", a == ["pkexec", deps.HELPER_PATH, "install", "curl"], a)
a = deps.install_argv(["curl"], use_helper=False); check("argv one-shot mode", a[:3] == ["pkexec", "/bin/sh", "-c"] and a[-2:] == ["install", "curl"], a[:3])
check("argv as root has no pkexec", deps.install_argv(["curl"], True, is_root=True)[0] == deps.HELPER_PATH)

# 9. polkit policy: well-formed, right action, exec.path matches the helper
import xml.dom.minidom
dom = xml.dom.minidom.parseString(deps.polkit_policy())
ann = {a.getAttribute("key"): a.firstChild.data for a in dom.getElementsByTagName("annotate")}
check("policy action id", dom.getElementsByTagName("action")[0].getAttribute("id") == deps.POLICY_ACTION_ID)
check("policy exec.path == helper path", ann.get("org.freedesktop.policykit.exec.path") == deps.HELPER_PATH, ann)
check("policy requires admin auth", all(t in deps.polkit_policy() for t in ("<allow_any>auth_admin<", "<allow_active>auth_admin_keep<")))

# 10. helper trust: world/group-writable or non-root-owned counts as NOT installed
d = tempfile.mkdtemp(); hp = os.path.join(d, "h"); open(hp, "w").write(script); os.chmod(hp, 0o755)
if os.geteuid() == 0:
    os.chown(hp, 0, 0); check("helper trusted when root-owned 755", deps.helper_status(hp) == (True, False), deps.helper_status(hp))
    os.chmod(hp, 0o777); check("helper NOT trusted when world-writable", deps.helper_status(hp) == (False, False))
    os.chmod(hp, 0o755); os.chown(hp, 1000, 1000); check("helper NOT trusted when user-owned", deps.helper_status(hp) == (False, False))
    os.chown(hp, 0, 0); open(hp, "w").write("#!/bin/sh\necho old\n"); check("outdated helper detected", deps.helper_status(hp) == (True, True))
check("missing helper", deps.helper_status("/nonexistent/h") == (False, False))

# 11. AppImage environment: system tools must not inherit the bundle's LD_LIBRARY_PATH
from conkystudio.sysenv import system_env
d = tempfile.mkdtemp(); fake = os.path.join(d, "conky")
open(fake, "w").write('#!/bin/sh\ncase "$LD_LIBRARY_PATH" in *bundle*) echo "libstdc++: GLIBCXX_3.4.32 not found" >&2; exit 1;; esac\nprintf "conky 1.19.6\\n Lua bindings:\\n  * Cairo\\n"\n'); os.chmod(fake, 0o755)
saved = {k: os.environ.get(k) for k in ("LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG", "LD_PRELOAD")}
os.environ.update(LD_LIBRARY_PATH="/opt/app/usr/bin/conky-studio-bundle", LD_LIBRARY_PATH_ORIG="/usr/local/lib", LD_PRELOAD="/x.so")
check("system_env restores the original path", system_env().get("LD_LIBRARY_PATH") == "/usr/local/lib" and "LD_PRELOAD" not in system_env() and "LD_LIBRARY_PATH_ORIG" not in system_env(), system_env())
check("conky_state reads a conky that breaks under the bundle path", deps.conky_state(which=lambda b: fake) == "ok", deps.conky_state(which=lambda b: fake))
check("discovery._run reads it too", "Cairo" in discovery._run([fake, "--version"]))
os.environ.pop("LD_LIBRARY_PATH_ORIG"); check("no ORIG -> LD_LIBRARY_PATH removed", "LD_LIBRARY_PATH" not in system_env())
for k, v in saved.items(): (os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v))
n = 0
print(f"{'FAIL' if fails else 'PASS'}: {len(fails)} failure(s)")
for f in fails: print("  -", f)
sys.exit(1 if fails else 0)
