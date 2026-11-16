"""
Start a theme automatically at login -- with no lock-in.

How it works (two plain, visible files per theme, both removed by "disable"):
    ~/.config/autostart/conky-studio-<name>-<hash>.desktop    standard XDG autostart entry
    ~/.config/conky-studio/autostart/conky-studio-<name>-<hash>.sh   tiny launcher: sleep N; exec start.sh

Why a launcher script instead of putting the command in the .desktop file: the
Desktop Entry `Exec=` key has its own quoting/escaping rules that are easy to get wrong
for paths with spaces, quotes or `$`. The .desktop file only ever names the launcher
script, whose path we control, and the launcher quotes the theme path for the shell.

Nothing here is required for a theme to work. Deleting those two files (or unticking
"Start at login" in the Manager) removes the autostart completely; the theme itself is
never modified. Sessions that do not read XDG autostart (Sway, i3, Hyprland, ...) are
told exactly which line to add to their own config instead.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
from dataclasses import dataclass, field

THEME_META_FILENAME = "theme.json"
DEFAULT_DELAY = 5
MAX_DELAY = 120

# XDG_CURRENT_DESKTOP tokens of sessions that DO process ~/.config/autostart.
_XDG_AUTOSTART_DESKTOPS = {
    "gnome", "kde", "xfce", "x-cinnamon", "cinnamon", "mate", "lxqt", "lxde", "budgie",
    "pantheon", "cosmic", "deepin", "unity", "ubuntu", "lxqt", "enlightenment", "ukui",
}


@dataclass
class AutostartResult:
    ok: bool
    message: str = ""
    entry_path: str = ""
    script_path: str = ""
    notes: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# paths / naming
# ---------------------------------------------------------------------------
def _config_home() -> str:
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")


def autostart_dir() -> str:
    return os.path.join(_config_home(), "autostart")


def script_dir() -> str:
    return os.path.join(_config_home(), "conky-studio", "autostart")


def entry_id(theme_path: str) -> str:
    """Stable id: readable slug + short hash of the absolute path (so two themes with the
    same folder name in different roots never collide)."""
    real = os.path.abspath(theme_path)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", os.path.basename(real)).strip("-").lower() or "theme"
    return f"conky-studio-{slug[:40]}-{hashlib.sha1(real.encode('utf-8', 'replace')).hexdigest()[:6]}"


def entry_path(theme_path: str) -> str:
    return os.path.join(autostart_dir(), entry_id(theme_path) + ".desktop")


def script_path(theme_path: str) -> str:
    return os.path.join(script_dir(), entry_id(theme_path) + ".sh")


# ---------------------------------------------------------------------------
# Desktop Entry quoting (spec: reserved characters inside double quotes, then a
# second level of backslash escaping for the key's string value)
# ---------------------------------------------------------------------------
def desktop_exec_quote(path: str) -> str:
    if not re.search(r'[\s"\'`$\\<>~|&;*?#()%=]', path):
        return path
    s = path.replace("%", "%%")
    for ch in ('\\', '"', '`', '$'):
        s = s.replace(ch, "\\" + ch)
    s = s.replace("\\", "\\\\")          # string-value level escaping
    return f'"{s}"'


def _clean_text(text: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", text or "").strip()


# ---------------------------------------------------------------------------
# reading state
# ---------------------------------------------------------------------------
def _read_kv(path: str) -> dict:
    out: dict = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.rstrip("\n").partition("=")
                    out[k.strip()] = v
    except OSError:
        pass
    return out


def is_enabled(theme_path: str) -> bool:
    kv = _read_kv(entry_path(theme_path))
    return bool(kv) and kv.get("Hidden", "false").lower() != "true" \
        and kv.get("X-GNOME-Autostart-enabled", "true").lower() != "false"


def configured_delay(theme_path: str) -> int:
    kv = _read_kv(entry_path(theme_path))
    try:
        return max(0, min(MAX_DELAY, int(kv.get("X-Conky-Studio-Delay", DEFAULT_DELAY))))
    except ValueError:
        return DEFAULT_DELAY


# ---------------------------------------------------------------------------
# launch target (honours a theme's monitor pin, like Start in the Manager does)
# ---------------------------------------------------------------------------
def _launch_target(theme_path: str, notes: list) -> str:
    start_sh = os.path.join(theme_path, "start.sh")
    meta = os.path.join(theme_path, THEME_META_FILENAME)
    monitor = "auto"
    try:
        with open(meta, "r", encoding="utf-8") as f:
            monitor = str(json.load(f).get("monitor") or "auto").strip() or "auto"
    except (OSError, ValueError):
        pass
    if monitor in ("", "auto", "primary"):
        return start_sh
    try:
        from conkystudio.manager import process
        head, note = process._resolve_xinerama_head(monitor)
        if head is not None:
            pinned = process._write_pinned_launch(theme_path, head)
            if pinned:
                notes.append(f"Monitor pin '{monitor}' was applied as it is today ({note}). "
                             "If your monitors are re-ordered later, switch autostart off and on again.")
                return pinned
        notes.append(f"Monitor pin '{monitor}' could not be resolved right now; the theme will "
                     "start with its default placement.")
    except Exception as exc:                                  # never block autostart on this
        notes.append(f"Monitor pin could not be applied ({exc}); using default placement.")
    return start_sh


# ---------------------------------------------------------------------------
# enable / disable
# ---------------------------------------------------------------------------
def _atomic_write(path: str, text: str, mode: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def enable(theme_path: str, name: str = "", delay: int = DEFAULT_DELAY) -> AutostartResult:
    theme_path = os.path.abspath(theme_path)
    if re.search(r"[\x00-\x1f\x7f]", theme_path):
        # a newline in a path would let it inject extra keys into the .desktop file
        return AutostartResult(False, "The theme folder's path contains control characters; "
                                      "rename the folder to use autostart.")
    if not os.path.isfile(os.path.join(theme_path, "start.sh")):
        return AutostartResult(False, "This theme has no start.sh, so there is nothing to start at login.")
    try:
        delay = max(0, min(MAX_DELAY, int(delay)))
    except (TypeError, ValueError):
        delay = DEFAULT_DELAY
    notes: list = []
    target = _launch_target(theme_path, notes)
    label = _clean_text(name) or os.path.basename(theme_path)
    sp, ep = script_path(theme_path), entry_path(theme_path)

    launcher = (
        "#!/bin/sh\n"
        f"# Created by Conky Studio: starts the theme \"{label}\" at login.\n"
        "# Remove it by unticking \"Start at login\" in the Conky Studio Manager, or just delete\n"
        f"# this file and {ep}\n"
        f"sleep {delay}\n"
        f"exec {shlex.quote(target)}\n"
    )
    entry = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name=Conky Studio: {label}\n"
        f"Comment=Starts the Conky theme \"{label}\" at login (created by Conky Studio; "
        "delete this file to remove)\n"
        f"Exec={desktop_exec_quote(sp)}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        f"X-Conky-Studio-Theme={theme_path}\n"
        f"X-Conky-Studio-Delay={delay}\n"
    )
    try:
        _atomic_write(sp, launcher, 0o755)
        _atomic_write(ep, entry, 0o644)
    except OSError as exc:
        return AutostartResult(False, f"Could not write the autostart files: {exc}")
    hint = session_hint(sp)
    if hint:
        notes.append(hint)
    return AutostartResult(True, f"'{label}' will start at login.", ep, sp, notes)


def disable(theme_path: str) -> AutostartResult:
    removed = []
    for p in (entry_path(theme_path), script_path(theme_path)):
        try:
            os.unlink(p)
            removed.append(p)
        except FileNotFoundError:
            pass
        except OSError as exc:
            return AutostartResult(False, f"Could not remove {p}: {exc}")
    return AutostartResult(True, "Autostart removed." if removed else "Autostart was not enabled.")


def list_entries() -> list:
    """Every autostart entry Conky Studio created: [{theme_path, entry, script, theme_exists}]."""
    out = []
    d = autostart_dir()
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if not (n.startswith("conky-studio-") and n.endswith(".desktop")):
            continue
        p = os.path.join(d, n)
        kv = _read_kv(p)
        theme = kv.get("X-Conky-Studio-Theme", "")
        out.append({"theme_path": theme, "entry": p,
                    "script": os.path.join(script_dir(), n[:-8] + ".sh"),
                    "theme_exists": bool(theme) and os.path.isfile(os.path.join(theme, "start.sh"))})
    return out


def prune_orphans() -> list:
    """Remove entries whose theme folder is gone (so uninstalling a theme can't leave a
    broken login item behind). Returns the removed entry paths."""
    gone = []
    for e in list_entries():
        if e["theme_path"] and not e["theme_exists"]:
            for p in (e["entry"], e["script"]):
                try:
                    os.unlink(p)
                except OSError:
                    pass
            gone.append(e["entry"])
    return gone


# ---------------------------------------------------------------------------
# sessions that do not read XDG autostart
# ---------------------------------------------------------------------------
def session_hint(script: str, desktop: str = "") -> str:
    """"" when the session reads XDG autostart; otherwise the exact line to add."""
    raw = desktop or os.environ.get("XDG_CURRENT_DESKTOP", "") or os.environ.get("DESKTOP_SESSION", "")
    tokens = {t.strip().lower() for t in re.split(r"[:;\s]+", raw) if t.strip()}
    if not tokens or tokens & _XDG_AUTOSTART_DESKTOPS:
        return ""
    q = shlex.quote(script)
    snippets = {
        "i3": f"i3 config:        exec --no-startup-id {q}",
        "sway": f"sway config:      exec {q}",
        "hyprland": f"hyprland.conf:   exec-once = {q}",
        "openbox": f"~/.config/openbox/autostart:   {q} &",
        "labwc": f"~/.config/labwc/autostart:   {q} &",
        "bspwm": f"bspwmrc:          {q} &",
        "niri": f"niri config.kdl:  spawn-at-startup {q}",
        "river": f"river init:       riverctl spawn {q}",
    }
    for key, line in snippets.items():
        if key in tokens:
            return (f"Your session ({raw}) does not process ~/.config/autostart by itself. "
                    f"Add this to its own config instead:\n    {line}")
    return (f"Your session ({raw}) may not process ~/.config/autostart. If the theme does not "
            f"appear after login, make your session run this script at startup:\n    {q}")
