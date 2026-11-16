"""
"It scans ~/.config/conky and ~/.conky, lists every installed theme."
A theme is any immediate subdirectory of either root that contains a
theme.json (see model.theme_meta) -- themes without one (hand-written,
predating Conky Studio) still show up, just with placeholder metadata
guessed from the folder name, so the Manager is useful on day one even
before every theme has adopted the standard layout.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from conkystudio.model.theme_meta import ThemeMeta, THEME_META_FILENAME

SCAN_ROOTS = [
    os.path.expanduser("~/.config/conky"),
    os.path.expanduser("~/.conky"),
]


@dataclass
class InstalledTheme:
    path: str
    meta: ThemeMeta
    has_start_sh: bool
    has_preview: bool
    has_theme_json: bool = True
    preview_path: str = ""


def _guess_meta(dirpath: str) -> ThemeMeta:
    name = os.path.basename(dirpath.rstrip("/"))
    return ThemeMeta(name=name, description="(no theme.json -- metadata guessed from folder name)")


def scan_installed_themes(extra_roots: list | None = None) -> list:
    roots = SCAN_ROOTS + (extra_roots or [])
    found: dict[str, InstalledTheme] = {}
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            theme_dir = os.path.join(root, name)
            if not os.path.isdir(theme_dir):
                continue
            if theme_dir in found:
                continue
            meta_path = os.path.join(theme_dir, THEME_META_FILENAME)
            theme_json_present = os.path.isfile(meta_path)
            if theme_json_present:
                try:
                    meta = ThemeMeta.load(meta_path)
                except (OSError, ValueError, KeyError):
                    meta = _guess_meta(theme_dir)
                    theme_json_present = False
            else:
                start_sh = os.path.join(theme_dir, "start.sh")
                conf = os.path.join(theme_dir, "conky.conf")
                if not (os.path.isfile(start_sh) or os.path.isfile(conf)):
                    continue  # not a theme folder at all
                meta = _guess_meta(theme_dir)

            preview_path = ""
            for candidate in ("preview.png", "preview.jpg", "preview.jpeg"):
                p = os.path.join(theme_dir, candidate)
                if os.path.isfile(p):
                    preview_path = p
                    break

            found[theme_dir] = InstalledTheme(
                path=theme_dir, meta=meta,
                has_start_sh=os.path.isfile(os.path.join(theme_dir, "start.sh")),
                has_preview=bool(preview_path), preview_path=preview_path,
                has_theme_json=theme_json_present,
            )
    return sorted(found.values(), key=lambda t: t.meta.name.lower())
