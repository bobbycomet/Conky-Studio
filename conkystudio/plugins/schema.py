"""
Matches plugins.json's shape: a flat list of node-type definitions a
community author can contribute without touching Conky Studio's source.
Each entry is pure data (metadata + a Lua text template with {property}
placeholders) rather than executable Python -- see loader.py's docstring
for why that boundary matters here.

api_version "1.1" adds optional fields (tags, lua_helpers, simple_mode,
requires) while remaining backward-compatible with 1.0 manifests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Kinds the property panel already knows how to edit
ALLOWED_KINDS = frozenset({
    "float", "int", "bool", "color", "string", "enum", "font", "path", "code",
})
ALLOWED_CATEGORIES = frozenset({"logic", "visual"})
ALLOWED_OUTPUT_KINDS = frozenset({
    "percent", "celsius", "number", "text", "category", "boolean",
})


@dataclass
class PluginProperty:
    key: str
    label: str
    kind: str = "float"
    default: object = 0.0
    minimum: float = 0.0
    maximum: float = 100.0
    step: float = 1.0
    choices: Optional[list] = None
    choice_labels: Optional[list] = None
    bindable: bool = False
    accepts: Optional[list] = None
    help: str = ""
    group: str = "General"

    @staticmethod
    def from_dict(d: dict) -> "PluginProperty":
        return PluginProperty(
            key=d["key"],
            label=d.get("label", d["key"]),
            kind=d.get("kind", "float"),
            default=d.get("default", 0.0),
            minimum=float(d.get("minimum", 0.0)),
            maximum=float(d.get("maximum", 100.0)),
            step=float(d.get("step", 1.0)),
            choices=d.get("choices"),
            choice_labels=d.get("choice_labels"),
            bindable=bool(d.get("bindable", False)),
            accepts=d.get("accepts"),
            help=d.get("help", ""),
            group=d.get("group", "General"),
        )


@dataclass
class PluginNode:
    id: str                 # registry type, e.g. "logic.clamp" or "visual.plugin.ring"
    category: str           # "logic" or "visual"
    label: str
    author: str = ""
    version: str = "1.0.0"
    description: str = ""
    color: str = "#5f8fd6"
    subcategory: str = "Plugins"
    output_kind: Optional[str] = None
    properties: list = field(default_factory=list)
    lua_expr: Optional[str] = None
    lua_draw_body: Optional[str] = None
    # --- 1.1 optional fields ---
    tags: list = field(default_factory=list)
    lua_helpers: Optional[str] = None   # shared Lua functions, emitted once per project
    simple_mode: bool = False           # if True, also show in Simple palette
    homepage: str = ""
    license: str = ""

    @staticmethod
    def from_dict(d: dict) -> "PluginNode":
        return PluginNode(
            id=d["id"],
            category=d.get("category", "logic"),
            label=d.get("label", d["id"]),
            author=d.get("author", ""),
            version=str(d.get("version", "1.0.0")),
            description=d.get("description", ""),
            color=d.get("color", "#5f8fd6"),
            subcategory=d.get("subcategory", "Plugins"),
            output_kind=d.get("output_kind"),
            properties=[PluginProperty.from_dict(p) for p in d.get("properties", [])],
            lua_expr=d.get("lua_expr"),
            lua_draw_body=d.get("lua_draw_body"),
            tags=list(d.get("tags", []) or []),
            lua_helpers=d.get("lua_helpers"),
            simple_mode=bool(d.get("simple_mode", False)),
            homepage=d.get("homepage", ""),
            license=d.get("license", ""),
        )


@dataclass
class PluginManifest:
    api_version: str = "1.0"
    updated_at: str = ""
    plugins: list = field(default_factory=list)
    # Optional human-readable source label (filled by loader, not required in JSON)
    source: str = ""

    @staticmethod
    def from_dict(d: dict, source: str = "") -> "PluginManifest":
        return PluginManifest(
            api_version=str(d.get("api_version", "1.0")),
            updated_at=d.get("updated_at", ""),
            plugins=[PluginNode.from_dict(p) for p in d.get("plugins", [])],
            source=source or d.get("source", ""),
        )
