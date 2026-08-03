"""
theme.json -- the metadata manifest that sits at the root of every theme
folder, e.g.:

    ~/.config/conky/Batman/theme.json

This is what lets the Manager tab show a library of installed themes
without guessing: name/author/version/description for the list view,
resolution + requires[] for a pre-launch dependency check, tags for
search/filter, and (once a theme came from the Store) store_id/sha256
so re-checking for updates doesn't require re-downloading anything.

Directory convention a theme.json describes:

    <ThemeName>/
    |-- theme.json
    |-- start.sh
    |-- preview.png        (optional, shown as a thumbnail in the Manager)
    |-- README.md           (optional, shown in an "Info" panel)
    |-- LICENSE              (optional)
    |-- conky.conf
    |-- render.lua
    |-- images/
    |-- fonts/
    |-- scripts/
"""
from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from typing import Optional

THEME_META_FILENAME = "theme.json"


@dataclass
class ThemeMeta:
    name: str = "Untitled HUD"
    author: str = ""
    version: str = "1.0.0"
    description: str = ""
    resolution: str = "1920x1080"
    requires: list[str] = field(default_factory=lambda: ["lua-cairo"])
    tags: list[str] = field(default_factory=list)
    created_with: str = "conky-studio"
    store_id: Optional[str] = None
    sha256: Optional[str] = None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        # Keep store-only bookkeeping fields out of manually-authored files
        # unless they're actually set, so a hand-edited theme.json stays tidy.
        if d["store_id"] is None:
            d.pop("store_id")
        if d["sha256"] is None:
            d.pop("sha256")
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @staticmethod
    def from_dict(d: dict) -> "ThemeMeta":
        return ThemeMeta(
            name=d.get("name", "Untitled HUD"),
            author=d.get("author", ""),
            version=str(d.get("version", "1.0.0")),
            description=d.get("description", ""),
            resolution=d.get("resolution", "1920x1080"),
            requires=list(d.get("requires", ["lua-cairo"])),
            tags=list(d.get("tags", [])),
            created_with=d.get("created_with", "conky-studio"),
            store_id=d.get("store_id"),
            sha256=d.get("sha256"),
        )

    @staticmethod
    def load(path: str) -> "ThemeMeta":
        with open(path, "r", encoding="utf-8") as f:
            return ThemeMeta.from_dict(json.load(f))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
