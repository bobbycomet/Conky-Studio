"""
Download an OCS / ocs:// payload and install it as a Conky theme when possible.

Pipeline:
  1. Download URL to a temp file (Pling CDN links are often time-limited).
  2. Unpack archives (.zip / .tar* / plain folder).
  3. Detect a Conky theme (conky.conf, .conkyrc, start.sh, render.lua, …).
  4. Copy into ~/.config/conky/<name> (or DEFAULT_INSTALL_ROOT).
  5. If the installed theme has no start.sh, write a minimal one that
     launches the main conky config (so Pling / openDesktop downloads
     are runnable from the Manager tab).
  6. Optionally run the legacy importer if available.

This module is UI-agnostic; the Store tab / main window call install_from_url().
"""
from __future__ import annotations

import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from conkystudio.store.ocs_url import OcsUrl, parse_ocs_url

DEFAULT_INSTALL_ROOT = os.path.expanduser("~/.config/conky")

THEME_MARKERS = (
    "conky.conf",
    ".conkyrc",
    "start.sh",
    "render.lua",
    "theme.json",
)


@dataclass
class InstallResult:
    success: bool
    message: str
    install_dir: str = ""
    theme_name: str = ""
    source_path: str = ""


ProgressCb = Optional[Callable[[str], None]]


def _log(cb: ProgressCb, msg: str) -> None:
    if cb:
        cb(msg)


def _safe_name(name: str) -> str:
    name = (name or "ocs-theme").strip()
    name = re.sub(r"[^\w.\- ]+", "_", name)
    name = name.strip(" ._") or "ocs-theme"
    return name[:80]


def download_file(url: str, dest: Path, *, user_agent: str = "ConkyStudio/1.0", progress: ProgressCb = None) -> Path:
    _log(progress, f"Downloading {url[:80]}…")
    req = Request(url, headers={"User-Agent": user_agent})
    try:
        with urlopen(req, timeout=60) as resp:
            # Prefer Content-Disposition filename if present
            cd = resp.headers.get("Content-Disposition") or ""
            fname = dest.name
            m = re.search(r'filename="?([^";]+)"?', cd)
            if m:
                fname = os.path.basename(m.group(1).strip())
            out = dest if dest.suffix else dest.with_name(fname)
            if out.is_dir():
                out = out / fname
            with open(out, "wb") as f:
                shutil.copyfileobj(resp, f)
            return out
    except URLError as e:
        raise RuntimeError(f"Download failed: {e}") from e


def _extract(archive: Path, dest_dir: Path, progress: ProgressCb = None) -> Path:
    _log(progress, f"Extracting {archive.name}…")
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()

    if name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dest_dir)
        return dest_dir

    if name.endswith((".tar", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tbz2")):
        with tarfile.open(archive, "r:*") as tf:
            # Python 3.12+ has filter=; ignore if older
            try:
                tf.extractall(dest_dir, filter=tarfile.data_filter)  # type: ignore[arg-type]
            except (TypeError, AttributeError):
                tf.extractall(dest_dir)
        return dest_dir

    # Single file — copy as-is into dest
    target = dest_dir / archive.name
    shutil.copy2(archive, target)
    return dest_dir


def _find_theme_root(extracted: Path) -> Optional[Path]:
    """Find a directory that looks like a Conky theme (walk shallow)."""
    candidates: list[Path] = []
    for root, dirs, files in os.walk(extracted):
        depth = Path(root).relative_to(extracted).parts
        if len(depth) > 4:
            dirs.clear()
            continue
        lower_files = {f.lower() for f in files}
        if any(m.lower() in lower_files or any(f.endswith(m) for f in files) for m in THEME_MARKERS):
            # .conkyrc match
            if any(f == "conky.conf" or f.endswith(".conkyrc") or f == "start.sh" or f == "theme.json" or f == "render.lua" for f in files):
                candidates.append(Path(root))
        # also accept folder named *conky*
        if "conky" in Path(root).name.lower():
            candidates.append(Path(root))

    if not candidates:
        # If archive unpacked to a single top-level folder, use it
        kids = [p for p in extracted.iterdir() if p.is_dir() and not p.name.startswith(".")]
        if len(kids) == 1:
            return kids[0]
        return extracted if any(extracted.iterdir()) else None

    # Prefer deepest meaningful match with conky.conf
    def score(p: Path) -> tuple:
        files = {f.name.lower() for f in p.iterdir() if f.is_file()}
        has_conf = 1 if ("conky.conf" in files or any(f.endswith(".conkyrc") for f in files)) else 0
        has_start = 1 if "start.sh" in files else 0
        has_json = 1 if "theme.json" in files else 0
        return (has_conf + has_start + has_json, -len(p.parts))

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def _pick_conf_name(theme_dir: Path) -> str:
    """Choose the best Conky config filename inside theme_dir."""
    for candidate in ("conky.conf", "conkyrc", ".conkyrc"):
        if (theme_dir / candidate).is_file():
            return candidate
    for p in sorted(theme_dir.iterdir()):
        if p.is_file() and (p.suffix.lower() == ".conf" or p.name.endswith(".conkyrc")):
            return p.name
    return "conky.conf"


def _ensure_start_sh(theme_dir: Path, progress: ProgressCb = None) -> bool:
    """
    If theme_dir has no usable start.sh, write a minimal one that:
      - makes scripts executable
      - prefers conky.conf, otherwise the first *.conf / *.conkyrc
      - launches conky from the theme directory
    Returns True if a start.sh was created (or replaced an empty/non-executable stub).
    """
    start_sh = theme_dir / "start.sh"
    # Treat missing, empty, or non-file the same: we need a real launcher.
    if start_sh.is_file() and start_sh.stat().st_size > 0:
        # Ensure it's executable even if the archive dropped the bit.
        try:
            mode = start_sh.stat().st_mode
            if not (mode & 0o111):
                start_sh.chmod(mode | 0o755)
        except OSError:
            pass
        return False

    conf_name = _pick_conf_name(theme_dir)

    content = f'''#!/usr/bin/env bash
# Minimal start.sh added by Conky Studio (theme had none).
# Launches the theme's Conky config from this directory.

DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
cd "$DIR" || exit 1

# Make helper scripts executable when present
chmod +x scripts/*.sh 2>/dev/null || true
chmod +x *.sh 2>/dev/null || true

CONF="{conf_name}"
if [[ ! -f "$CONF" ]]; then
    # Fallback: first .conf / .conkyrc in the theme root
    CONF="$(ls *.conf *.conkyrc .conkyrc 2>/dev/null | head -n1 || true)"
fi
if [[ -z "$CONF" || ! -f "$CONF" ]]; then
    echo "No Conky config found in $DIR" >&2
    exit 1
fi

exec conky -c "$DIR/$CONF"
'''
    try:
        start_sh.write_text(content, encoding="utf-8")
        start_sh.chmod(0o755)
    except OSError as e:
        _log(progress, f"Could not write start.sh: {e}")
        return False

    _log(progress, "No start.sh found — added a minimal one.")
    return True


def install_from_url(
    url: str,
    *,
    filename: str = "",
    install_type: str = "conky",
    theme_name: str = "",
    install_root: str = DEFAULT_INSTALL_ROOT,
    progress: ProgressCb = None,
) -> InstallResult:
    """
    Download `url` and install into install_root/<theme_name>.
    For install_type in (conky, themes, downloads) we try theme detection.
    """
    install_root_path = Path(install_root).expanduser()
    install_root_path.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="conkystudio-ocs-") as tmp:
        tmp_path = Path(tmp)
        suggested = filename or os.path.basename(urlparse_path(url)) or "download.bin"
        dest = tmp_path / suggested
        try:
            archive = download_file(url, dest, progress=progress)
        except Exception as e:
            return InstallResult(False, str(e))

        extract_dir = tmp_path / "extracted"
        try:
            _extract(archive, extract_dir, progress=progress)
        except Exception as e:
            return InstallResult(False, f"Extract failed: {e}", source_path=str(archive))

        theme_root = _find_theme_root(extract_dir)
        if theme_root is None:
            return InstallResult(
                False,
                "Downloaded, but no Conky theme files were found "
                "(expected conky.conf, start.sh, theme.json, or render.lua).",
                source_path=str(archive),
            )

        name = _safe_name(theme_name or theme_root.name or Path(suggested).stem)
        target = install_root_path / name
        if target.exists():
            # Unique suffix
            i = 2
            while (install_root_path / f"{name}-{i}").exists():
                i += 1
            target = install_root_path / f"{name}-{i}"
            name = target.name

        _log(progress, f"Installing to {target}…")
        shutil.copytree(theme_root, target)

        # Always ensure start.sh on the *final* installed copy so Pling /
        # openDesktop themes without one are still launchable from Manager.
        added_start = _ensure_start_sh(target, progress=progress)

        msg = f"Installed theme to {target}"
        if added_start:
            msg += " (added a minimal start.sh)"
        return InstallResult(
            success=True,
            message=msg,
            install_dir=str(target),
            theme_name=name,
            source_path=str(archive),
        )


def install_from_ocs_url(
    ocs_url: str,
    *,
    theme_name: str = "",
    install_root: str = DEFAULT_INSTALL_ROOT,
    progress: ProgressCb = None,
) -> InstallResult:
    parsed: OcsUrl = parse_ocs_url(ocs_url)
    return install_from_url(
        parsed.url,
        filename=parsed.filename,
        install_type=parsed.install_type,
        theme_name=theme_name,
        install_root=install_root,
        progress=progress,
    )


def urlparse_path(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).path or ""

