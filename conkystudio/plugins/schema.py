"""
Matches plugins.json's shape: a flat list of node-type definitions a
community author can contribute without touching Conky Studio's source.
Each entry is pure data (metadata + a Lua text template with {property}
placeholders) rather than executable Python -- see loader.py's docstring
for why that boundary matters here.

api_version "1.1" adds optional fields (tags, lua_helpers, simple_mode,
requires) while remaining backward-compatible with 1.0 manifests.

"icon" (1.1, optional) is a PNG reference, never embedded image data:
either an "http(s)://...png" URL (store-hosted) or a bare filename with
no path separators (e.g. "icon.png") that a local plugin pack ships
alongside its JSON file. loader.py's resolve_icon() turns either form
into something a UI can actually load; an empty icon just means "use
the category default" -- nothing downstream requires it. "icon" is the
one media field the desktop app itself ever displays (palette swatches,
the Plugins dialog list).

api_version "1.1" also adds three site-only media fields, rendered by
the community store website (community-store/app.js) and otherwise
inert -- Conky Studio itself never reads them:
  "screenshot" -- a still image of the plugin in use, shown on its
                  store detail page (this is distinct from "icon",
                  which is the small palette/list glyph).
  "gif"        -- a short looping demo, shown alongside "screenshot".
  "video"      -- a link to a longer demo/walkthrough; the store links
                  out to it rather than embedding, so any host works.
All three take the same URL-or-bare-filename shape "icon" does, and are
optional; a plugin with none of them just shows no preview media.

A manifest (plugins.json, or any URL passed to loader.fetch_manifest)
may reference an out-of-line plugin file instead of embedding a full
plugin object, so a manifest.json can sit next to a "plugins/" folder
of one-file-per-plugin JSON on GitHub while plugins.json keeps working
unchanged as a single flat file -- both shapes are read by the exact
same fetch_manifest() call, since the two are only distinguished per
*entry*, not per manifest:
    { "$ref": "plugins/visual.plugin.ring.json" }
"$ref" is resolved relative to wherever the manifest itself was loaded
from (its URL, or its file path for a local manifest) -- see
loader._resolve_plugin_refs(). A $ref entry may carry no other keys;
the referenced file is a single plugin object, not another manifest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Kinds the property panel already knows how to edit
ALLOWED_KINDS = frozenset({
    "float", "int", "bool", "color", "string", "enum", "font", "path", "code",
})
# "source" plugins wrap a real data source (native ${...} isn't enough --
# a custom API, a local daemon, whatever) behind the same execi/daemon
# polling harness as source.custom_script. "canvas_ext" plugins add a
# handful of extra literal conky.conf directives -- deliberately the
# most constrained category, see CANVAS_EXT_ALLOWED_KEYS below.
ALLOWED_CATEGORIES = frozenset({"logic", "visual", "source", "canvas_ext"})
ALLOWED_OUTPUT_KINDS = frozenset({
    "percent", "celsius", "number", "text", "category", "boolean",
})
# A source plugin's own output_kind is a stricter subset of
# ALLOWED_OUTPUT_KINDS: "boolean" only ever makes sense as a logic node's
# convenience return value, never as something a Bar/Gauge/Text node binds
# to straight off a wire.
ALLOWED_SOURCE_OUTPUT_KINDS = frozenset({"percent", "celsius", "number", "text", "category"})
ALLOWED_POLL_MODES = frozenset({"execi", "daemon"})

# The exhaustive set of conky.conf keys a canvas_ext plugin may set. Every
# key here is a plain cosmetic/behavior tuning knob Conky itself defines --
# nothing that loads code (lua_load, lua_*_hook), nothing that manages
# window placement/sizing (own_window*, alignment, gap_x/y, minimum_*,
# maximum_*, xinerama_head -- all core-owned, see codegen/conky_conf_gen.py),
# and nothing that touches the update loop (update_interval, background,
# total_run_times). A plugin author can't add a key outside this list, and
# can't override a core-owned key even if it appeared here by mistake.
CANVAS_EXT_ALLOWED_KEYS = frozenset({
    "border_inner_margin", "border_outer_margin", "border_width",
    "default_outline_color", "default_shade_color",
    "default_bar_size", "default_gauge_size", "default_graph_size",
    "imlib_cache_size", "imlib_cache_flush_interval",
    "text_buffer_size", "temperature_unit", "short_units",
    "top_name_width", "pad_percents", "max_text_width", "max_user_text",
    "override_utf8_locale", "format_human_readable",
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
    icon: str = ""                      # "" | "https://.../icon.png" | bare "icon.png"
    # --- site-only media (community-store/app.js renders these; the
    # desktop app never reads them) -- same URL-or-bare-filename shape as
    # icon, all optional ---
    screenshot: str = ""                # still image for the store detail page
    gif: str = ""                       # short looping demo
    video: str = ""                     # link to a longer demo (store links out, no embed)
    # --- source-plugin fields (category == "source" only) ---
    # script_body is a bash script template (may use {property} placeholders,
    # substituted the same plain-string way as lua_expr/lua_draw_body). It's
    # run through the exact same execi/daemon harness as source.custom_script
    # (see codegen/shell_gen.gen_custom_script_wrapper): stdout's last line
    # is the value. This is deliberately unrestricted -- curl a private API,
    # shell out to a CLI tool, whatever -- same trust level as any theme
    # script or Custom Script node, not sandboxed beyond what Conky itself
    # sandboxes.
    script_body: Optional[str] = None
    poll_mode_default: str = "execi"
    poll_interval_default: int = 5
    # --- canvas_ext-plugin fields (category == "canvas_ext" only) ---
    # conky.conf key -> value template. Keys are checked against
    # CANVAS_EXT_ALLOWED_KEYS at validation time; values may reference
    # {property} placeholders (float/int/bool/string/enum/color properties
    # only -- no "code" kind is allowed on a canvas_ext plugin).
    conf_directives: dict = field(default_factory=dict)

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
            icon=(d.get("icon") or "").strip(),
            screenshot=(d.get("screenshot") or "").strip(),
            gif=(d.get("gif") or "").strip(),
            video=(d.get("video") or "").strip(),
            script_body=d.get("script_body"),
            poll_mode_default=d.get("poll_mode_default", "execi"),
            poll_interval_default=int(d.get("poll_interval_default", 5)),
            conf_directives=dict(d.get("conf_directives", {}) or {}),
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
