"""
Helpers to wire gradients, extend modes, and blend operators into every
fill-capable visual.

Usage in nodes/visuals.py
-------------------------
from conkystudio.codegen.color import GRADIENT_FILL_PROP_DICTS
from conkystudio.codegen.cairo_effects import BLEND_OPERATOR_PROP_DICT
from conkystudio.nodes.registry import PropertySpec, ENUM, COLOR, FLOAT

def _grad_props():
    out = []
    for d in GRADIENT_FILL_PROP_DICTS:
        out.append(PropertySpec(
            key=d["key"],
            label=d["label"],
            kind=d["kind"],
            default=d["default"],
            minimum=d.get("minimum", 0),
            maximum=d.get("maximum", 100),
            step=d.get("step", 1),
            choices=d.get("choices"),
            choice_labels=d.get("choice_labels"),
            help=d.get("help", ""),
            group=d.get("group", "Style"),
        ))
    return out

# Then on each fill-capable NodeSpec:
#   properties=[ ..., *_grad_props(), *_blend_props() ]

Usage in codegen/lua_gen.py
---------------------------
from conkystudio.codegen.gradient_integration import fill_source_lua, wrap_blend_lua

def _fill_source_block(node, p, *, box=None, radial=None, alpha=1):
    '''
    box = (x, y, w, h) for linear (numbers or prop lookups already resolved)
    radial = (cx, cy, radius) for radial
    '''
    return fill_source_lua(p, box=box, radial=radial, alpha=alpha)

# Example replacement inside _gen_bar / _gen_circle / etc.:
#
#   setup, destroy = fill_source_lua(
#       p, box=(x, y, width, height), radial=(cx, cy, radius), alpha=opacity,
#   )
#   # emit setup, then path + cairo_fill, then destroy
#
#   # And to let the node's own blend_mode property control compositing:
#   body = wrap_blend_lua("\\n".join(draw_lines), p)
"""

from __future__ import annotations

from conkystudio.codegen.color import (
    GRADIENT_FILL_PROP_DICTS,
    lua_set_source,
    lua_destroy_gradient_if_needed,
)
from conkystudio.codegen.cairo_effects import (
    BLEND_OPERATOR_PROP_DICT,
    lua_with_operator,
)


def gradient_property_specs():
    """Return list[PropertySpec] for fill_mode / color_end / angle / spread / extend."""
    from conkystudio.nodes.registry import PropertySpec

    out = []
    for d in GRADIENT_FILL_PROP_DICTS:
        out.append(
            PropertySpec(
                key=d["key"],
                label=d["label"],
                kind=d["kind"],
                default=d["default"],
                minimum=float(d.get("minimum", 0)),
                maximum=float(d.get("maximum", 100)),
                step=float(d.get("step", 1)),
                choices=d.get("choices"),
                choice_labels=d.get("choice_labels"),
                help=d.get("help", ""),
                group=d.get("group", "Style"),
            )
        )
    return out


def blend_property_spec():
    """Return the single PropertySpec for blend_mode (see cairo_effects.BLEND_OPERATOR_PROP_DICT)."""
    from conkystudio.nodes.registry import PropertySpec

    d = BLEND_OPERATOR_PROP_DICT
    return PropertySpec(
        key=d["key"],
        label=d["label"],
        kind=d["kind"],
        default=d["default"],
        choices=d.get("choices"),
        choice_labels=d.get("choice_labels"),
        help=d.get("help", ""),
        group=d.get("group", "Style"),
    )


def scale_property_spec():
    """Uniform Scale % for every visual node (built-in and plugin).

    Multiplies the whole drawn element — paths, text, line widths, images —
    around the node's position/center. Works *with* Width/Height/Radius etc.:
    those set the base size; Scale % is an extra uniform factor (100 = no change).
    Grouped under ``Size`` so it sits with dimensional controls in the inspector.
    """
    from conkystudio.nodes.registry import PropertySpec, FLOAT

    return PropertySpec(
        key="scale",
        label="Scale %",
        kind=FLOAT,
        default=100.0,
        minimum=1.0,
        maximum=500.0,
        step=1.0,
        group="Shape",
        help=(
            "Uniform scale of this entire visual (geometry, text, strokes, images). "
            "Works together with Width/Height/Radius — 50% makes the whole element "
            "half size so text and shapes stay in proportion. Does not replace those "
            "fields; it multiplies the finished drawing."
        ),
    )


def wrap_scale_lua(
    body: str,
    props: dict,
    *,
    pivot_x=None,
    pivot_y=None,
    cr: str = "cr",
) -> str:
    """Wrap draw-call *body* so it renders under props['scale'] (percent).

    No-op when scale is missing or 100. Pivot defaults to cx/cy if present on
    *props*, else x/y, else (0,0). Pivot values may be Lua expression strings
    or Python numbers.
    """
    try:
        scale_pct = float(props.get("scale", 100) or 100)
    except (TypeError, ValueError):
        scale_pct = 100.0
    if abs(scale_pct - 100.0) < 1e-6:
        return body

    s = scale_pct / 100.0

    def _pivot(key_primary: str, key_fallback: str, explicit):
        if explicit is not None:
            return explicit if isinstance(explicit, str) else repr(float(explicit))
        if key_primary in props and props[key_primary] is not None and props[key_primary] != "":
            try:
                return repr(float(props[key_primary]))
            except (TypeError, ValueError):
                pass
        if key_fallback in props and props[key_fallback] is not None and props[key_fallback] != "":
            try:
                return repr(float(props[key_fallback]))
            except (TypeError, ValueError):
                pass
        return "0"

    px = _pivot("cx", "x", pivot_x)
    py = _pivot("cy", "y", pivot_y)

    indented = "\n".join(
        ("    " + ln if ln.strip() else ln) for ln in body.splitlines()
    )
    lines = [
        f"do -- Scale {scale_pct:g}%",
        f"    local _sc, _px, _py = {s}, {px}, {py}",
        f"    cairo_save({cr})",
        f"    cairo_translate({cr}, _px, _py)",
        f"    cairo_scale({cr}, _sc, _sc)",
        f"    cairo_translate({cr}, -_px, -_py)",
        f"    local _ok, _err = pcall(function()",
        indented,
        f"    end)",
        f"    cairo_restore({cr})",
        f"    if not _ok then error(_err) end",
        f"end",
    ]
    return "\n".join(lines)


def apply_scale_to_draw_function(lua_source: str, node) -> str:
    """Post-process a full ``local function draw_node_*(cr, W, H) ... end`` so
    the body runs under the node's Scale % transform.
    """
    import re

    props = getattr(node, "props", None) or {}
    try:
        scale_pct = float(props.get("scale", 100) or 100)
    except (TypeError, ValueError):
        scale_pct = 100.0
    if abs(scale_pct - 100.0) < 1e-6:
        return lua_source

    m = re.match(
        r"(?s)^(\s*local\s+function\s+draw_node_\w+\s*\(\s*cr\s*,\s*W\s*,\s*H\s*\)\s*\n)(.*)(\nend\s*)$",
        lua_source.strip(),
    )
    if not m:
        return (
            "-- scale wrap (unparsed function shape)\n"
            + wrap_scale_lua(lua_source, props)
        )

    header, body, footer = m.group(1), m.group(2), m.group(3)
    return header + wrap_scale_lua(body, props) + footer


def _prop_get(props: dict, *keys, default=None):
    """First present key wins. Preserves old prop names without migrations."""
    for k in keys:
        if k in props and props[k] is not None and props[k] != "":
            return props[k]
    return default


def fill_source_lua(
    props: dict,
    *,
    color_key: str = "color",
    alpha_key: str | None = None,
    alpha=1,
    box=None,
    radial=None,
    cr: str = "cr",
) -> tuple[str, str]:
    """Return (setup_lua, destroy_lua) for a node's fill.

    **Single fill pipeline** for core generators and plugins. Always routes
    through ``lua_set_source`` so solid / linear / radial, extend modes, and
    future N-stop gradients stay in one place.

    box: (x, y, w, h) — used for linear gradients
    radial: (cx, cy, radius) — used for radial gradients
    Pass both when the shape supports either mode.

    Property keys (normalized, first match wins):
      color:       color_key, "color", "color_hex", "fill_color"
      color_end:   "color_end", "color_end_hex"
      fill_mode:   "fill_mode", "gradient_mode"
      angle:       "gradient_angle", "angle_deg"
      spread:      "gradient_spread", "spread"
      extend:      "gradient_extend", "extend_mode"  (default ``pad``)
      alpha:       *alpha* arg, or *alpha_key* / "opacity" / "alpha" in props

    ``gradient_extend`` defaults to ``pad`` so projects saved before the
    extend-mode property was added render unchanged.
    """
    mode = str(_prop_get(props, "fill_mode", "gradient_mode", default="solid") or "solid")
    color = str(
        _prop_get(props, color_key, "color", "color_hex", "fill_color", default="#4fd1c5")
    )
    color_end = str(
        _prop_get(props, "color_end", "color_end_hex", default="#1a3a4a")
    )
    angle = float(_prop_get(props, "gradient_angle", "angle_deg", default=0) or 0)
    spread = float(_prop_get(props, "gradient_spread", "spread", default=1.0) or 1.0)
    extend = str(
        _prop_get(props, "gradient_extend", "extend_mode", default="pad") or "pad"
    )

    # Alpha: explicit arg wins unless alpha_key is set and present on props
    a = alpha
    if alpha_key and alpha_key in props:
        try:
            a = float(props[alpha_key])
        except (TypeError, ValueError):
            a = alpha
    elif alpha == 1:
        # Only auto-read opacity/alpha when caller left the default
        for k in ("opacity", "alpha", "fill_alpha"):
            if k in props and props[k] is not None:
                try:
                    a = float(props[k])
                except (TypeError, ValueError):
                    pass
                break

    kw = dict(
        color_hex=color,
        alpha=a,
        fill_mode=mode,
        color_end_hex=color_end if mode != "solid" else None,
        angle_deg=angle,
        spread=spread,
        extend_mode=extend,
        cr=cr,
    )
    if box is not None:
        kw.update(x=box[0], y=box[1], w=box[2], h=box[3])
    if radial is not None:
        kw.update(cx=radial[0], cy=radial[1], radius=radial[2])

    return lua_set_source(**kw), lua_destroy_gradient_if_needed(mode)


def wrap_blend_lua(body: str, props: dict, *, cr: str = "cr") -> str:
    """Wrap generated draw-call *body* under props['blend_mode'] if the
    node has that property and it isn't the 'over' default. No-op
    (returns body unchanged) for nodes that haven't been given the
    blend_mode property yet, so this is safe to add to every generator
    unconditionally."""
    op = str(props.get("blend_mode", "over"))
    return lua_with_operator(body, op, cr=cr)


# Nodes that should receive gradient props (fill-based shapes / gauges).
GRADIENT_ENABLED_TYPES = frozenset({
    "visual.bar",
    "visual.arc_gauge",
    "visual.circle",
    "visual.star",
    "visual.triangle",
    "visual.reactor_gauge",
    "visual.glow_pulse",
    "visual.spiral",
    "visual.history_graph",
    "visual.radar",
})

# Nodes that should also receive the blend_mode property. Superset of
# GRADIENT_ENABLED_TYPES -- includes shapes that are always solid-filled
# (e.g. glow/particle effects) but still benefit from additive compositing.
BLEND_ENABLED_TYPES = GRADIENT_ENABLED_TYPES | frozenset({
    "visual.orbit_field",
    "visual.equalizer_bars",
    "visual.core_strip",
})


