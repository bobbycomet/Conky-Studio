"""
Font install/registration.

"As long as they download and install the .ttf or .otf, and it is
installed at .fonts and/or ~/.local/share/fonts it will register that
font. It should also automate installing fonts for ease of use" -- so
this module does two things:

  1. list_families() -- what fc-list already knows about, for the Font
     property's picker dropdown (both system fonts and anything already
     dropped into ~/.local/share/fonts or ~/.fonts).
  2. install_font(path) -- copies a .ttf/.otf a user drags onto the
     Studio into ~/.local/share/fonts (the standard per-user XDG font
     directory; ~/.fonts is the older/legacy equivalent some tools still
     read from -- honoring the request to check both on the read side
     via fc-list, which already indexes both) and refreshes fontconfig's
     cache so it's immediately available without a logout.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")
USER_FONT_DIR = os.path.expanduser("~/.local/share/fonts")
LEGACY_FONT_DIR = os.path.expanduser("~/.fonts")


@dataclass
class FontInstallResult:
    success: bool
    installed_path: str = ""
    family_name: str = ""
    message: str = ""


def list_families() -> list:
    """Every font family fontconfig currently knows about (system fonts +
    anything already in ~/.local/share/fonts or ~/.fonts), deduplicated
    and sorted. Falls back to a short safe list if fc-list is missing."""
    if not shutil.which("fc-list"):
        return ["Sans", "Serif", "Monospace"]
    try:
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return ["Sans", "Serif", "Monospace"]
    families = set()
    for line in out.splitlines():
        # fc-list can list multiple comma-separated aliases per line; the
        # first is the one fontconfig/Cairo actually matches by default.
        first = line.split(",")[0].strip()
        if first:
            families.add(first)
    return sorted(families) or ["Sans", "Serif", "Monospace"]


def is_font_installed(family_name: str) -> bool:
    return family_name in list_families()


def install_font(source_path: str) -> FontInstallResult:
    if not os.path.isfile(source_path):
        return FontInstallResult(False, message=f"No such file: {source_path}")
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in FONT_EXTENSIONS:
        return FontInstallResult(False, message=f"Not a font file (expected .ttf/.otf/.ttc): {source_path}")

    os.makedirs(USER_FONT_DIR, exist_ok=True)
    dest = os.path.join(USER_FONT_DIR, os.path.basename(source_path))
    try:
        shutil.copy2(source_path, dest)
    except OSError as e:
        return FontInstallResult(False, message=f"Couldn't copy font: {e}")

    refresh_ok = True
    if shutil.which("fc-cache"):
        try:
            subprocess.run(["fc-cache", "-f", USER_FONT_DIR], capture_output=True, timeout=15)
        except Exception:
            refresh_ok = False

    family = _guess_family_name(dest)
    msg = f"Installed {os.path.basename(dest)}" + ("" if refresh_ok else " (installed, but fc-cache refresh failed -- a logout may be needed before it shows up)")
    return FontInstallResult(True, installed_path=dest, family_name=family or "", message=msg)


def _guess_family_name(font_path: str) -> str:
    """Best-effort: ask fontconfig what family it thinks this exact file
    is, now that it's been copied + cache-refreshed."""
    if not shutil.which("fc-scan"):
        return ""
    try:
        out = subprocess.run(["fc-scan", "--format", "%{family[0]}", font_path],
                              capture_output=True, text=True, timeout=5).stdout
        return out.strip()
    except Exception:
        return ""
