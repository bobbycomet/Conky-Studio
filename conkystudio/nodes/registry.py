"""
Node type registry.

Every draggable block in the Studio canvas -- data sources and visual
elements alike -- is described by a NodeSpec. A NodeSpec is pure metadata
(no Qt, no Cairo): the palette panel lists specs, the property panel
builds its form from a spec's `properties`, and the code generator
dispatches on `spec.type` to know which Lua-emitting function to call.
Keeping this Qt-free means the whole node library is unit-testable
without a display, which matters a lot for an app that generates
graphics code headlessly (see tests/test_codegen_smoke.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ---- property editor kinds -----------------------------------------------
FLOAT = "float"
INT = "int"
COLOR = "color"      # (r, g, b[, a]) 0..1 tuple, edited via a colour-swatch button
BOOL = "bool"
ENUM = "enum"
STRING = "string"
PATH = "path"         # string + a "Browse..." picker; copied into the theme's images/ on build
FONT = "font"          # string naming a font FAMILY (fontconfig-matched), picker fed by fonts.manager
CODE = "code"           # multiline text, edited monospace -- for raw Lua passthrough (see visual.custom_lua)

# ---- data-source output kinds ---------------------------------------------
# What a source node's single output socket carries. Drives socket colour
# coding in the canvas and which bindable properties will accept a wire
# from it (see PropertySpec.accepts).
KIND_PERCENT = "percent"    # 0-100 float
KIND_CELSIUS = "celsius"    # raw temperature float, no fixed range
KIND_NUMBER = "number"      # unitless float (process count, KB/s, ...)
KIND_TEXT = "text"          # arbitrary display string
KIND_CATEGORY = "category"  # short token, e.g. a weather category used to pick an icon

ALL_KINDS = (KIND_PERCENT, KIND_CELSIUS, KIND_NUMBER, KIND_TEXT, KIND_CATEGORY)
NUMERIC_KINDS = (KIND_PERCENT, KIND_CELSIUS, KIND_NUMBER)


@dataclass
class PropertySpec:
    key: str
    label: str
    kind: str = FLOAT
    default: Any = 0.0
    minimum: float = 0.0
    maximum: float = 100.0
    step: float = 1.0
    choices: Optional[list[str]] = None    # required for ENUM: list of (value) strings
    choice_labels: Optional[list[str]] = None  # optional friendlier labels, same order as choices
    bindable: bool = False                  # can this property accept an incoming wire?
    accepts: Optional[tuple[str, ...]] = None  # which KIND_* values a wire may carry, if bindable
    help: str = ""
    group: str = "General"                  # section heading in the property panel


@dataclass
class NodeSpec:
    type: str          # dotted registry key, e.g. "visual.arc_gauge"
    category: str        # "source" | "visual" | "logic" | "canvas"
    label: str
    description: str = ""
    color: str = "#4a90d9"    # node header accent colour in the canvas
    output_kind: Optional[str] = None    # set only when category == "source" or "logic"
    properties: list[PropertySpec] = field(default_factory=list)
    icon: str = "circle"
    simple_mode: bool = True   # shown in the trimmed "Simple" palette as well as "Complex"
    subcategory: str = "General"   # finer grouping within the palette, e.g. "Network", "Weather", "Effects"
    # For "source" nodes backed by an external script (see sources_external.py):
    # nodes sharing a script_family are deduplicated by codegen/builder.py into
    # ONE generated script + one cache file (e.g. GPU Util and GPU Temp both
    # read the same gpu_stats.sh run, rather than spawning nvidia-smi twice).
    script_family: Optional[str] = None
    script_output_key: Optional[str] = None   # which key in that family's cache this node reads

    def prop(self, key: str) -> Optional[PropertySpec]:
        for p in self.properties:
            if p.key == key:
                return p
        return None

    def defaults(self) -> dict:
        return {p.key: p.default for p in self.properties}

    def bindable_properties(self) -> list[PropertySpec]:
        return [p for p in self.properties if p.bindable]


_REGISTRY: dict[str, NodeSpec] = {}


def register(spec: NodeSpec, *, replace: bool = False) -> NodeSpec:
    """Register a node type. If *replace* is True, an existing entry is overwritten
    (used when re-installing a plugin after uninstall). Identical re-registration
    (same module imported twice, or a packaging mix-up that loads the same
    NodeSpec again) is ignored. A *different* NodeSpec for the same type still
    raises unless replace=True."""
    existing = _REGISTRY.get(spec.type)
    if existing is not None and not replace:
        # Same object or equal fields → treat as no-op (safe for double import).
        if existing is spec or (
            existing.label == spec.label
            and existing.category == spec.category
            and existing.output_kind == spec.output_kind
            and len(existing.properties) == len(spec.properties)
        ):
            return existing
        raise ValueError(
            f"Duplicate node type registered: {spec.type!r} "
            f"(already {existing.category}/{existing.label!r}; "
            f"new {spec.category}/{spec.label!r}). "
            f"Check that sources_*.py and visuals.py were not swapped when packaging."
        )
    _REGISTRY[spec.type] = spec
    return spec


def unregister(node_type: str) -> bool:
    """Remove a node type from the registry. Returns True if it was present.
    Built-in types should not be unregistered in normal use; this exists so
    plugins can be uninstalled and later re-installed in the same session."""
    return _REGISTRY.pop(node_type, None) is not None


def get(node_type: str) -> NodeSpec:
    try:
        return _REGISTRY[node_type]
    except KeyError:
        raise KeyError(f"Unknown node type {node_type!r}. Is its module imported in nodes/__init__.py?")


def has(node_type: str) -> bool:
    return node_type in _REGISTRY


def all_specs() -> list[NodeSpec]:
    return list(_REGISTRY.values())


def by_category(category: str) -> list[NodeSpec]:
    return [s for s in _REGISTRY.values() if s.category == category]


def subcategories_in(category: str) -> list[str]:
    seen: list[str] = []
    for s in _REGISTRY.values():
        if s.category == category and s.subcategory not in seen:
            seen.append(s.subcategory)
    return seen


def resolve_prop(node_type: str, node_props: dict, key: str):
    """Merge an instance's stored props over the type's declared defaults."""
    spec = get(node_type)
    if key in node_props:
        return node_props[key]
    p = spec.prop(key)
    return p.default if p else None


