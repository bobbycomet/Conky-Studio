"""
Missing-package detection for Conky Studio, per distro.

What it does
  * works out which distro/package manager you are on (reuses discovery.detect_distro)
  * checks what is actually installed (Conky *with Lua-Cairo*, curl, lm-sensors, ...)
  * builds the copy-paste terminal command for exactly what is missing
  * can optionally run that install through pkexec, either one-shot or through a
    small root-owned helper + polkit policy that the user installs on purpose

Principles
  * Nothing is installed without the user asking. No lock-in: the helper and its
    policy are two plain files the user can see, and removing them is one click.
  * The privileged helper only accepts REQUIREMENT KEYS (e.g. "curl"), never package
    names or options, and maps them to a built-in allowlist for the detected distro.
  * Package names below were machine-verified only for the Debian/Ubuntu family
    (apt-cache against real repositories). The others are best knowledge and the UI
    says so (`DepsReport.verified`).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Optional

from conkystudio.hardware import discovery
from conkystudio.sysenv import system_env

HELPER_PATH = "/usr/lib/conky-studio/conky-studio-helper"
POLICY_PATH = "/usr/share/polkit-1/actions/org.conkystudio.install-deps.policy"
POLICY_ACTION_ID = "org.conkystudio.install-deps"

# Families whose package names were checked against a real repository.
VERIFIED_FAMILIES = frozenset({"debian"})
# Families we can install for (command line and optional pkexec).
INSTALLABLE_FAMILIES = ("debian", "fedora", "arch", "opensuse", "void")


@dataclass(frozen=True)
class Requirement:
    key: str
    label: str
    level: str                 # "required" | "recommended"
    purpose: str
    binary: str                # looked up with shutil.which
    packages: dict             # family -> tuple of package names


_ALL = ("debian", "fedora", "arch", "opensuse", "void")


def _same(name: str) -> dict:
    return {f: (name,) for f in _ALL}


REQUIREMENTS: tuple = (
    Requirement(
        "conky-lua-cairo", "Conky with Lua-Cairo support", "required",
        "draws every HUD that Conky Studio builds", "conky",
        {"debian": ("conky-all",), "fedora": ("conky",), "arch": ("conky",),
         "opensuse": ("conky",), "void": ("conky",)},
    ),
    Requirement("curl", "curl", "recommended",
                "weather and public-IP data sources", "curl", _same("curl")),
    Requirement(
        "lm-sensors", "lm-sensors", "recommended",
        "CPU / fan temperature sources", "sensors",
        {"debian": ("lm-sensors",), "fedora": ("lm_sensors",), "arch": ("lm_sensors",),
         "opensuse": ("sensors",), "void": ("lm_sensors",)},
    ),
    Requirement("playerctl", "playerctl", "recommended",
                "Now Playing / media data sources", "playerctl", _same("playerctl")),
    Requirement("smartmontools", "smartmontools", "recommended",
                "disk temperature source", "smartctl", _same("smartmontools")),
)
REQ_BY_KEY = {r.key: r for r in REQUIREMENTS}

# How each family installs packages: terminal line template + the helper's command.
_INSTALL_LINE = {
    "debian": "sudo apt update && sudo apt install -y {pkgs}",
    "fedora": "sudo dnf install -y {pkgs}",
    "arch": "sudo pacman -S --needed {pkgs}",
    "opensuse": "sudo zypper install {pkgs}",
    "void": "sudo xbps-install -S {pkgs}",
}

# Shown when we cannot give a trustworthy one-line command.
_MANUAL_HINT = {
    "alpine": "Alpine uses musl libc, which Conky Studio's AppImage does not support.",
    "gentoo": "Gentoo: install app-admin/conky with its Lua and Cairo USE flags enabled "
              "(check `conky --version` lists 'Lua bindings: * Cairo').",
    "nixos": "NixOS: add conky (a build with Lua and Cairo bindings) to your configuration; "
             "the AppImage also needs nix-ld.",
    "unknown": "Install Conky built with Lua and Cairo bindings using your package manager "
               "(`conky --version` must list 'Lua bindings: * Cairo'), plus curl, lm-sensors, "
               "playerctl and smartmontools if you use those data sources.",
}


@dataclass
class Item:
    key: str
    label: str
    level: str
    purpose: str
    state: str                       # "ok" | "missing" | "no-cairo" | "unknown"
    packages: tuple = ()             # for the detected family, () if none known

    @property
    def needs_install(self) -> bool:
        return self.state in ("missing", "no-cairo")


@dataclass
class DepsReport:
    distro_id: str = ""
    pretty_name: str = ""
    family: str = "unknown"
    immutable: bool = False
    is_root: bool = False
    items: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    pkexec: bool = False
    helper_installed: bool = False
    helper_outdated: bool = False
    verified: bool = False

    # -- views ---------------------------------------------------------------
    @property
    def missing(self) -> list:
        return [i for i in self.items if i.needs_install]

    @property
    def missing_required(self) -> list:
        return [i for i in self.missing if i.level == "required"]

    @property
    def missing_recommended(self) -> list:
        return [i for i in self.missing if i.level == "recommended"]

    @property
    def signature(self) -> str:
        return ",".join(sorted(i.key for i in self.missing))

    @property
    def can_auto_install(self) -> bool:
        return (self.family in INSTALLABLE_FAMILIES and not self.immutable
                and (self.pkexec or self.is_root))

    def installable(self, items) -> list:
        """Items we can name a package for on this family."""
        return [i for i in items if i.packages]

    def command(self, keys=None) -> str:
        """Copy-paste terminal command for the given requirement keys (default: all missing)."""
        items = [i for i in self.missing if keys is None or i.key in keys]
        return command_for(self.family, items, self.immutable, self.is_root)

    def to_dict(self) -> dict:
        return {
            "distro": {"id": self.distro_id, "pretty_name": self.pretty_name,
                       "family": self.family, "immutable": self.immutable},
            "packages_verified_for_family": self.verified,
            "pkexec": self.pkexec, "helper_installed": self.helper_installed,
            "items": [{"key": i.key, "level": i.level, "state": i.state,
                       "packages": list(i.packages)} for i in self.items],
            "command_required": self.command({i.key for i in self.missing_required}) if self.missing_required else "",
            "command_all": self.command() if self.missing else "",
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Environment probing (all injectable for tests)
# ---------------------------------------------------------------------------
def _is_immutable(distro_id: str, os_release: dict, exists: Callable[[str], bool]) -> bool:
    if exists("/run/ostree-booted"):                      # Silverblue/Kinoite/Bazzite/CoreOS...
        return True
    variant = (os_release.get("VARIANT_ID") or "").lower()
    if variant in {"silverblue", "kinoite", "sericea", "onyx", "iot", "coreos", "cosmic-atomic"}:
        return True
    if distro_id in {"steamos", "opensuse-microos", "opensuse-aeon", "opensuse-kalpa", "sle-micro"}:
        return True
    return False


def conky_state(which: Callable = shutil.which, run: Optional[Callable] = None) -> str:
    """"missing" | "no-cairo" | "ok" | "unknown" (version output unreadable: never nag)."""
    path = which("conky")
    if not path:
        return "missing"
    out = ""
    # A cold disk cache can make the first `conky --version` slow; retry once, patiently,
    # before giving up (and giving up means "unknown", which never nags).
    for timeout in (10, 25):
        try:
            if run is None:
                out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=timeout,
                                     env=system_env()).stdout
            else:
                out = run(path)
            break
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            return "unknown"
    if not (out or "").strip():
        return "unknown"
    return "ok" if discovery._conky_has_lua_cairo(out) else "no-cairo"


def helper_status(path: str = HELPER_PATH) -> tuple:
    """(installed, outdated). Installed means: root-owned, not group/other-writable."""
    try:
        st = os.stat(path)
    except OSError:
        return False, False
    if st.st_uid != 0 or (st.st_mode & 0o022):
        return False, False            # not trustworthy -> treat as absent
    try:
        with open(path, "r", encoding="utf-8") as f:
            current = f.read()
    except OSError:
        return True, True
    return True, current != helper_script()


def build_report(
    *,
    os_release: Optional[dict] = None,
    which: Callable = shutil.which,
    conky_probe: Optional[Callable] = None,
    exists: Callable[[str], bool] = os.path.exists,
    euid: Optional[int] = None,
    helper: Optional[tuple] = None,
) -> DepsReport:
    data = os_release if os_release is not None else discovery._read_os_release()
    d = _distro_from(data)
    r = DepsReport(distro_id=d.id, pretty_name=d.pretty_name, family=d.family)
    r.immutable = _is_immutable(d.id, data, exists)
    r.is_root = (os.geteuid() if euid is None else euid) == 0
    r.pkexec = which("pkexec") is not None
    r.verified = d.family in VERIFIED_FAMILIES
    r.helper_installed, r.helper_outdated = helper if helper is not None else helper_status()

    for req in REQUIREMENTS:
        if req.key == "conky-lua-cairo":
            state = conky_state(which, conky_probe)
        else:
            state = "ok" if which(req.binary) else "missing"
        pkgs = req.packages.get(d.family, ())
        # A Conky that is installed but lacks Cairo can only be fixed by a package
        # swap we know about: on the Debian family that is conky-all. Elsewhere we
        # cannot name the right package confidently, so say so instead of guessing.
        if state == "no-cairo" and d.family != "debian":
            pkgs = ()
        r.items.append(Item(req.key, req.label, req.level, req.purpose, state, tuple(pkgs)))

    _add_notes(r)
    return r


def _distro_from(data: dict):
    info = discovery.DistroInfo()
    info.id = (data.get("ID") or "").lower()
    info.id_like = [t.strip() for t in (data.get("ID_LIKE") or "").lower().split() if t.strip()]
    info.pretty_name = data.get("PRETTY_NAME") or data.get("NAME") or ""
    for token in [info.id] + info.id_like:
        if token in discovery._FAMILY_BY_ID:
            info.family = discovery._FAMILY_BY_ID[token]
            return info
    for token in [info.id] + info.id_like:
        for key, fam in discovery._FAMILY_BY_ID.items():
            if key and token and key in token:
                info.family = fam
                return info
    return info


def _add_notes(r: DepsReport) -> None:
    if r.family in _MANUAL_HINT and r.family not in INSTALLABLE_FAMILIES and r.missing:
        r.notes.append(_MANUAL_HINT[r.family])
    if r.immutable and r.missing:
        r.notes.append(
            "This looks like an immutable / image-based system, where packages are layered "
            "or installed in a container rather than with a normal package manager.")
    for i in r.missing:
        if i.state == "no-cairo" and not i.packages:
            hint = ("Your Conky build has no Lua-Cairo support, so Studio-built HUDs would draw "
                    "nothing. Install a build that includes it (`conky --version` must list "
                    "'Lua bindings: * Cairo').")
            if r.family == "arch":
                hint += (" On Arch the official `conky` package normally includes it; community "
                         "AUR builds such as conky-cairo or conky-lua-nv exist for other cases "
                         "(AUR packages are never installed automatically).")
            r.notes.append(hint)
    if r.missing and not r.verified and r.family in INSTALLABLE_FAMILIES:
        r.notes.append("Package names for this distribution family were not machine-verified. "
                       "If one is not found, search your package manager for it.")
    if r.missing and r.family == "unknown":
        r.notes.append(_MANUAL_HINT["unknown"])


def command_for(family: str, items, immutable: bool = False, is_root: bool = False) -> str:
    pkgs: list = []
    for i in items:
        for p in i.packages:
            if p not in pkgs:
                pkgs.append(p)
    if not pkgs:
        return ""
    if immutable:
        if family == "fedora":
            return "rpm-ostree install " + " ".join(pkgs) + "    # then reboot (or add --apply-live)"
        return ""        # no safe generic command; the notes explain
    tmpl = _INSTALL_LINE.get(family)
    if not tmpl:
        return ""
    line = tmpl.format(pkgs=" ".join(pkgs))
    return line.replace("sudo ", "") if is_root else line


# ---------------------------------------------------------------------------
# Optional automation: pkexec + helper script + polkit policy
# ---------------------------------------------------------------------------
def _family_case() -> str:
    by_family: dict = {}
    for token, fam in sorted(discovery._FAMILY_BY_ID.items()):
        if fam in INSTALLABLE_FAMILIES:
            by_family.setdefault(fam, []).append(token)
    lines = []
    for fam in INSTALLABLE_FAMILIES:
        toks = "|".join(by_family.get(fam, []))
        lines.append(f"        {toks}) family={fam} ;;")
    return "\n".join(lines)


def _pkgs_case() -> str:
    lines = []
    for req in REQUIREMENTS:
        for fam in INSTALLABLE_FAMILIES:
            names = req.packages.get(fam)
            if names:
                lines.append(f"    {req.key}:{fam}) echo \"{' '.join(names)}\" ;;")
    return "\n".join(lines)


def helper_script() -> str:
    """The root-side script. It accepts only requirement keys, never package names."""
    return f"""#!/bin/sh
# conky-studio-helper -- installs the distro packages Conky Studio needs.
#
# Generated by Conky Studio. Run as root (normally through pkexec):
#     conky-studio-helper install <requirement-key>...
# Valid keys: {" ".join(r.key for r in REQUIREMENTS)}
#
# SAFETY: this script never takes package names or options from its caller. Each key is
# mapped to a fixed allowlist for the detected distro family below; an unknown key or an
# unsupported distro is refused. Remove it any time with Conky Studio's "Remove admin
# helper" button, or by deleting this file and {POLICY_PATH}.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 022

if [ "$(id -u)" -ne 0 ]; then
    echo "conky-studio-helper must run as root (use pkexec)." >&2
    exit 1
fi

family=unknown
ids=""
if [ -r /etc/os-release ]; then
    ids="$(sed -n -e 's/^ID=//p' -e 's/^ID_LIKE=//p' /etc/os-release | tr -d '"' | tr '\\n' ' ')"
fi
for tok in $ids; do
    case "$tok" in
{_family_case()}
    esac
    [ "$family" != unknown ] && break
done

pkgs_for() {{
    case "$1:$family" in
{_pkgs_case()}
    *) return 1 ;;
    esac
}}

if [ "${{1:-}}" != "install" ] || [ "$#" -lt 2 ]; then
    echo "usage: conky-studio-helper install <key>..." >&2
    exit 2
fi
shift

pkgs=""
for key in "$@"; do
    p="$(pkgs_for "$key")" || {{ echo "refusing: unknown requirement '$key' or unsupported distro ($family)" >&2; exit 3; }}
    pkgs="$pkgs $p"
done

echo "Installing:$pkgs"
case "$family" in
    debian)   export DEBIAN_FRONTEND=noninteractive
              apt-get update || echo "(apt-get update reported a problem; continuing)" >&2
              exec apt-get install -y $pkgs ;;
    fedora)   exec dnf install -y $pkgs ;;
    arch)     exec pacman -S --needed --noconfirm $pkgs ;;
    opensuse) exec zypper --non-interactive install $pkgs ;;
    void)     exec xbps-install -Sy $pkgs ;;
    *)        echo "unsupported distro family: $family" >&2; exit 4 ;;
esac
"""


def polkit_policy() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <vendor>Conky Studio</vendor>
  <vendor_url>https://github.com/bobbycomet/Conky-Studio</vendor_url>
  <action id="{POLICY_ACTION_ID}">
    <description>Install the packages Conky Studio needs</description>
    <message>Authentication is required to install the packages Conky Studio needs (Conky, curl, lm-sensors, ...)</message>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">{HELPER_PATH}</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
"""


def _sh(argv_tail: list, script: str) -> list:
    return ["/bin/sh", "-c", script, "conky-studio-helper", *argv_tail]


def install_argv(keys: list, use_helper: bool, is_root: bool = False) -> list:
    """argv to run (through pkexec unless already root). Keys are validated here too."""
    bad = [k for k in keys if k not in REQ_BY_KEY]
    if bad or not keys:
        raise ValueError(f"unknown requirement key(s): {bad or '(none)'}")
    if use_helper:
        base = [HELPER_PATH, "install", *keys]
    else:
        base = _sh(["install", *keys], helper_script())
    return base if is_root else ["pkexec", *base]


def helper_setup_argv(is_root: bool = False) -> list:
    """One-time, admin-approved install of the helper + policy (two plain files)."""
    script = (
        "set -e\n"
        f"install -d -m 0755 /usr/lib/conky-studio\n"
        f"cat > {HELPER_PATH} <<'CONKY_STUDIO_HELPER_EOF'\n{helper_script()}CONKY_STUDIO_HELPER_EOF\n"
        f"chown root:root {HELPER_PATH}\nchmod 0755 {HELPER_PATH}\n"
        f"install -d -m 0755 /usr/share/polkit-1/actions\n"
        f"cat > {POLICY_PATH} <<'CONKY_STUDIO_POLICY_EOF'\n{polkit_policy()}CONKY_STUDIO_POLICY_EOF\n"
        f"chown root:root {POLICY_PATH}\nchmod 0644 {POLICY_PATH}\n"
        "echo 'Conky Studio admin helper installed.'\n"
    )
    base = ["/bin/sh", "-c", script]
    return base if is_root else ["pkexec", *base]


def helper_remove_argv(is_root: bool = False) -> list:
    script = (f"rm -f {HELPER_PATH} {POLICY_PATH}; rmdir /usr/lib/conky-studio 2>/dev/null || true; "
              "echo 'Conky Studio admin helper removed.'")
    base = ["/bin/sh", "-c", script]
    return base if is_root else ["pkexec", *base]


def report_json() -> str:
    return json.dumps(build_report().to_dict(), indent=2)
