"""
"Drag in a .zip. Drag in a .tar.gz. Manager extracts it. Places it in
~/.config/conky/<Name>. Theme immediately appears in the library." Also
covers the font-handling ask: "scan the theme folder for a fonts/
directory and auto-install them to ~/.local/share/fonts/ (and run
fc-cache -f) upon import."

Runs extraction synchronously -- callers on the UI thread (see
ui/manager_tab.py) push this through a QThread/QRunnable so a large
archive doesn't freeze the window, per the brief's own suggestion.
"""
from __future__ import annotations

import os
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field

from conkystudio.model.theme_meta import ThemeMeta, THEME_META_FILENAME
from conkystudio.fonts import manager as font_manager

DEFAULT_INSTALL_ROOT = os.path.expanduser("~/.config/conky")


@dataclass
class InstallResult:
    success: bool
    installed_path: str = ""
    theme_name: str = ""
    fonts_installed: list = field(default_factory=list)
    message: str = ""


def _archive_kind(archive_path: str) -> str:
    """Return 'zip', 'tar', or '' for unsupported.

    Case-insensitive. Recognizes .zip, .tar.gz, .tgz, .tar.
    """
    name = os.path.basename(archive_path).lower()
    if name.endswith(".zip"):
        return "zip"
    if name.endswith((".tar.gz", ".tgz", ".tar")):
        return "tar"
    return ""


def _theme_name_from_archive(archive_path: str) -> str:
    """Basename of the archive with known archive suffixes stripped."""
    name = os.path.basename(archive_path)
    lower = name.lower()
    for suffix in (".tar.gz", ".tgz", ".tar", ".zip"):
        if lower.endswith(suffix):
            return name[: len(name) - len(suffix)]
    # Fallback: single extension
    return os.path.splitext(name)[0]


def _extract(archive_path: str, dest_dir: str) -> None:
    kind = _archive_kind(archive_path)
    if kind == "zip":
        with zipfile.ZipFile(archive_path) as zf:
            _safe_extract_zip(zf, dest_dir)
    elif kind == "tar":
        # tarfile.open auto-detects gzip for .tar.gz / .tgz
        with tarfile.open(archive_path) as tf:
            _safe_extract_tar(tf, dest_dir)
    else:
        raise ValueError(
            f"Unsupported archive type: {archive_path} "
            "(use .zip, .tar.gz, .tgz, or .tar)"
        )


def _safe_extract_zip(zf: zipfile.ZipFile, dest_dir: str) -> None:
    dest_abs = os.path.abspath(dest_dir)
    for member in zf.namelist():
        target = os.path.abspath(os.path.join(dest_dir, member))
        if not target.startswith(dest_abs + os.sep) and target != dest_abs:
            raise ValueError(f"Archive contains an unsafe path: {member}")
    zf.extractall(dest_dir)


def _safe_extract_tar(tf: tarfile.TarFile, dest_dir: str) -> None:
    dest_abs = os.path.abspath(dest_dir)
    for member in tf.getmembers():
        target = os.path.abspath(os.path.join(dest_dir, member.name))
        if not target.startswith(dest_abs + os.sep) and target != dest_abs:
            raise ValueError(f"Archive contains an unsafe path: {member.name}")
    tf.extractall(dest_dir)


def _dir_looks_like_theme(path: str) -> bool:
    """True if this directory itself holds theme markers (not merely a wrapper)."""
    if not os.path.isdir(path):
        return False
    markers = ("theme.json", "conky.conf", "start.sh")
    try:
        names = os.listdir(path)
    except OSError:
        return False
    if any(os.path.isfile(os.path.join(path, m)) for m in markers):
        return True
    # Closebox73 / Regulus style: any top-level *.conf
    if any(n.endswith(".conf") and os.path.isfile(os.path.join(path, n)) for n in names):
        return True
    return False


def _find_theme_root(extracted_dir: str) -> str:
    """Locate the real theme directory inside an extracted archive.

    Archives are often wrapped in one or more extra folders (GitHub
    "Download ZIP", author packs like RidgeV2/RidgeV2/). Peel single-
    child directory chains until we find a folder that itself contains
    theme.json, conky.conf, start.sh, or any *.conf. Caps depth so a
    pathological tree cannot loop forever.
    """
    current = extracted_dir
    for _ in range(6):
        if _dir_looks_like_theme(current):
            return current
        try:
            entries = [
                e for e in os.listdir(current)
                if not e.startswith("__MACOSX") and e != ".DS_Store"
            ]
        except OSError:
            return current
        # Only peel when there is exactly one child and it is a directory
        if len(entries) != 1:
            return current
        candidate = os.path.join(current, entries[0])
        if not os.path.isdir(candidate):
            return current
        current = candidate
    return current


def _find_main_conf(theme_dir: str) -> str | None:
    """Pick the primary Conky config file in a theme folder.

    Preference order:
      1. conky.conf (Studio / standard layout)
      2. <folder-name>.conf (Closebox73 / Regulus style)
      3. any other top-level *.conf (first alphabetically)
      4. same search one level down (leftover nested pack layout)

    Returns a path relative to theme_dir (e.g. "conky.conf" or
    "RidgeV2/Ridge.conf"), or None if nothing suitable is found.
    """
    def _search(directory: str, prefix: str = "") -> str | None:
        preferred = os.path.join(directory, "conky.conf")
        if os.path.isfile(preferred):
            return f"{prefix}conky.conf" if prefix else "conky.conf"

        folder = os.path.basename(directory.rstrip("/"))
        candidates = [folder + ".conf"]
        for sep in ("-v", "_v", "-V", "_V"):
            if sep in folder:
                candidates.append(folder.split(sep)[0] + ".conf")
        if "-" in folder:
            candidates.append(folder.split("-")[0] + ".conf")

        for name in candidates:
            if os.path.isfile(os.path.join(directory, name)):
                return f"{prefix}{name}" if prefix else name

        try:
            names = os.listdir(directory)
        except OSError:
            return None
        confs = sorted(
            n for n in names
            if n.endswith(".conf") and os.path.isfile(os.path.join(directory, n))
        )
        if confs:
            return f"{prefix}{confs[0]}" if prefix else confs[0]
        return None

    found = _search(theme_dir)
    if found:
        return found

    # Fallback: single nested directory still holding the conf
    try:
        subdirs = [
            d for d in os.listdir(theme_dir)
            if os.path.isdir(os.path.join(theme_dir, d))
            and not d.startswith(".")
            and d not in ("scripts", "fonts", "res", "images", "data", "assets")
        ]
    except OSError:
        return None
    if len(subdirs) == 1:
        return _search(os.path.join(theme_dir, subdirs[0]), prefix=subdirs[0] + "/")
    return None


def _build_minimal_start_sh(theme_name: str, conf_basename: str) -> str:
    """Minimal launcher for archives that ship no start.sh.

    Matches the setsid + PID-file lock pattern from start_sh_gen so the
    Manager's Start/Stop controls work the same way. Any scripts/* are
    launched once in the background (many third-party scripts already
    loop internally). Then execs conky against the detected conf file.
    """
    lock_name = "".join(ch if ch.isalnum() else "-" for ch in theme_name.lower()).strip("-") or "conky-studio-hud"
    return f'''#!/usr/bin/env bash
#
# {theme_name} -- start.sh
# ---------------------------------------------------------------
# Auto-generated by Conky Studio on archive install (no start.sh was
# present in the dropped package). Uses the same single-instance lock
# and setsid process-group pattern as Studio-built themes so the
# Manager tab can start/stop this HUD cleanly.
#
# Usage:
#   ~/.config/conky/{theme_name}/start.sh
#

if [[ -z "$CONKY_STUDIO_REEXEC" ]]; then
    export CONKY_STUDIO_REEXEC=1
    exec setsid "$0" "$@"
fi

DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
LOCK_FILE="${{XDG_RUNTIME_DIR:-/tmp}}/{lock_name}.pid"

if [[ -f "$LOCK_FILE" ]]; then
    OLD_PID="$(cat "$LOCK_FILE" 2>/dev/null)"
    if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill -TERM -- "-$OLD_PID" 2>/dev/null
        sleep 0.4
        kill -KILL -- "-$OLD_PID" 2>/dev/null
    fi
fi
echo $$ > "$LOCK_FILE"

mkdir -p "${{DIR}}/.runtime-cache"
chmod +x "${{DIR}}"/scripts/*.sh 2>/dev/null

# Launch shipped shell scripts once in the background. Only *.sh -- Lua
# and other helpers are loaded by Conky itself (lua_load / execi), not
# as standalone processes. Scripts that need continuous polling typically
# contain their own loop; we do not add an outer poller here because
# archive installs have no interval metadata.
if [[ -d "${{DIR}}/scripts" ]]; then
    for s in "${{DIR}}"/scripts/*.sh; do
        [[ -f "$s" ]] || continue
        chmod +x "$s" 2>/dev/null
        "$s" &
    done
fi

exec conky -c "${{DIR}}/{conf_basename}"
'''


def _ensure_start_sh(dest: str, theme_name: str) -> bool:
    """Write a minimal start.sh if the installed theme lacks one and has a conf.

    Returns True if a new start.sh was created.
    """
    start_sh = os.path.join(dest, "start.sh")
    if os.path.isfile(start_sh):
        return False
    conf_basename = _find_main_conf(dest)
    if not conf_basename:
        return False
    with open(start_sh, "w", encoding="utf-8") as f:
        f.write(_build_minimal_start_sh(theme_name, conf_basename))
    os.chmod(start_sh, 0o755)
    return True


def install_theme_archive(archive_path: str, install_root: str = DEFAULT_INSTALL_ROOT) -> InstallResult:
    if not os.path.isfile(archive_path):
        return InstallResult(False, message=f"No such file: {archive_path}")

    scratch = archive_path + ".conky-studio-extract-tmp"
    if os.path.exists(scratch):
        shutil.rmtree(scratch, ignore_errors=True)
    os.makedirs(scratch, exist_ok=True)
    try:
        _extract(archive_path, scratch)
    except Exception as e:
        shutil.rmtree(scratch, ignore_errors=True)
        return InstallResult(False, message=f"Couldn't extract archive: {e}")

    theme_root = _find_theme_root(scratch)
    meta_path = os.path.join(theme_root, THEME_META_FILENAME)
    if os.path.isfile(meta_path):
        try:
            meta = ThemeMeta.load(meta_path)
            theme_name = meta.name
        except (OSError, ValueError, KeyError):
            theme_name = _theme_name_from_archive(archive_path)
    else:
        theme_name = _theme_name_from_archive(archive_path)

    theme_name = "".join(c for c in theme_name if c not in '/\\:*?"<>|').strip() or "Imported Theme"
    os.makedirs(install_root, exist_ok=True)
    dest = os.path.join(install_root, theme_name)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.move(theme_root, dest)
    shutil.rmtree(scratch, ignore_errors=True)

    created_start = _ensure_start_sh(dest, theme_name)
    has_start = os.path.isfile(os.path.join(dest, "start.sh"))
    conf_found = _find_main_conf(dest)

    for f in ("start.sh",):
        p = os.path.join(dest, f)
        if os.path.isfile(p):
            os.chmod(p, 0o755)
    scripts_dir = os.path.join(dest, "scripts")
    if os.path.isdir(scripts_dir):
        for name in os.listdir(scripts_dir):
            os.chmod(os.path.join(scripts_dir, name), 0o755)

    installed_fonts = []
    fonts_dir = os.path.join(dest, "fonts")
    if os.path.isdir(fonts_dir):
        for name in os.listdir(fonts_dir):
            if os.path.splitext(name)[1].lower() in font_manager.FONT_EXTENSIONS:
                result = font_manager.install_font(os.path.join(fonts_dir, name))
                if result.success:
                    installed_fonts.append(result.family_name or name)

    extras = []
    if created_start:
        extras.append(f"generated start.sh → {conf_found}")
    elif has_start:
        extras.append("kept existing start.sh")
    elif conf_found:
        extras.append(f"conf={conf_found}, but start.sh missing (unexpected)")
    else:
        extras.append("no .conf found — start.sh not generated")
    if installed_fonts:
        extras.append(f"+{len(installed_fonts)} font(s)")
    suffix = f" ({'; '.join(extras)})" if extras else ""

    return InstallResult(
        success=True, installed_path=dest, theme_name=theme_name,
        fonts_installed=installed_fonts,
        message=f"Installed '{theme_name}'{suffix}",
    )


def uninstall_theme(theme_path: str) -> bool:
    real = os.path.realpath(theme_path)
    allowed_roots = [os.path.realpath(r) for r in (DEFAULT_INSTALL_ROOT, os.path.expanduser("~/.conky"))]
    if not any(real.startswith(root + os.sep) for root in allowed_roots):
        return False  # refuse to delete anything outside the known theme roots
    shutil.rmtree(real, ignore_errors=True)
    return not os.path.exists(real)


def duplicate_theme(theme_path: str, new_name: str, install_root: str = DEFAULT_INSTALL_ROOT) -> InstallResult:
    dest = os.path.join(install_root, new_name)
    if os.path.exists(dest):
        return InstallResult(False, message=f"'{new_name}' already exists.")
    shutil.copytree(theme_path, dest)
    meta_path = os.path.join(dest, THEME_META_FILENAME)
    if os.path.isfile(meta_path):
        try:
            meta = ThemeMeta.load(meta_path)
            meta.name = new_name
            meta.save(meta_path)
        except (OSError, ValueError, KeyError):
            pass
    return InstallResult(True, installed_path=dest, theme_name=new_name, message=f"Duplicated as '{new_name}'")


def export_theme_zip(theme_path: str, output_zip_path: str) -> bool:
    base = os.path.splitext(output_zip_path)[0]
    archive = shutil.make_archive(base, "zip", root_dir=os.path.dirname(theme_path), base_dir=os.path.basename(theme_path))
    return os.path.isfile(archive)

