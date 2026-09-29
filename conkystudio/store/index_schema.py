"""
Matches the index.json manifest format from the community-store design:
a single JSON file a store host serves (GitHub raw content, or anything
else static), listing every theme with its download URL and a sha256 for
integrity checking before install. See packaging/community-repo-template/
for the matching repo layout and CI validation workflow.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StoreThemeEntry:
    id: str
    name: str
    author: str = ""
    version: str = "1.0.0"
    description: str = ""
    tags: list = field(default_factory=list)
    preview_url: str = ""
    download_url: str = ""
    sha256: str = ""

    @staticmethod
    def from_dict(d: dict) -> "StoreThemeEntry":
        return StoreThemeEntry(
            id=d.get("id", ""), name=d.get("name", "Untitled"), author=d.get("author", ""),
            version=str(d.get("version", "1.0.0")), description=d.get("description", ""),
            tags=list(d.get("tags", [])), preview_url=d.get("preview_url", ""),
            download_url=d.get("download_url", ""), sha256=d.get("sha256", ""),
        )


@dataclass
class StoreIndex:
    api_version: str = "1.0"
    updated_at: str = ""
    themes: list = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict) -> "StoreIndex":
        return StoreIndex(
            api_version=str(d.get("api_version", "1.0")),
            updated_at=d.get("updated_at", ""),
            themes=[StoreThemeEntry.from_dict(t) for t in d.get("themes", [])],
        )
