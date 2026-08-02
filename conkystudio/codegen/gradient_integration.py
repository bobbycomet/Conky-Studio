"""
Helpers to wire 2-stop gradients into every fill-capable visual.

Usage in nodes/visuals.py
-------------------------
from conkystudio.codegen.color import GRADIENT_FILL_PROP_DICTS
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
#   properties=[ ..., *_grad_props() ]

Usage in codegen/lua_gen.py
---------------------------
from conkystudio.codegen.color import lua_set_source, lua_destroy_gradient_if_needed

def _fill_source_block(node, p, *, box=None, radial=None, alpha=1):
    '''
    box = (x, y, w, h) for linear (numbers or prop lookups already resolved)
    radial = (cx, cy, radius) for radial
    '''
    mode = str(p.get("fill_mode", "solid"))
    color = str(p.get("color", "#4fd1c5"))
    color_end = str(p.get("color_end", "#1a3a4a"))
    angle = float(p.get("gradient_angle", 0))
    spread = float(p.get("gradient_spread", 1.0))

    kw = dict(
        color_hex=color,
        alpha=alpha,
        fill_mode=mode,
        color_end_hex=color_end if mode != "solid" else None,
        angle_deg=angle,
        spread=spread,
    )
    if box is not None:
        kw.update(x=box[0], y=box[1], w=box[2], h=box[3])
    if radial is not None:
        kw.update(cx=radial[0], cy=radial[1], radius=radial[2])

    setup = lua_set_source(**kw)
    destroy = lua_destroy_gradient_if_needed(mode)
    return setup, destroy


# Example replacement inside _gen_bar / _gen_circle / etc.:
#
#   setup, destroy = _fill_source_block(
#       node, p,
#       box=(x, y, width, height),   # for linear
#       radial=(cx, cy, radius),     # for radial (both can be passed)
#       alpha=opacity,
#   )
#   # emit setup, then path + cairo_fill, then destroy
"""

from __future__ import annotations

from conkystudio.codegen.color import (
    GRADIENT_FILL_PROP_DICTS,
    lua_set_source,
    lua_destroy_gradient_if_needed,
)


def gradient_property_specs():
    """Return list[PropertySpec] for fill_mode / color_end / angle / spread."""
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


def fill_source_lua(
    props: dict,
    *,
    color_key: str = "color",
    alpha=1,
    box=None,
    radial=None,
) -> tuple[str, str]:
    """Return (setup_lua, destroy_lua) for a node's fill.

    box: (x, y, w, h) — used for linear gradients
    radial: (cx, cy, radius) — used for radial gradients
    Pass both when the shape supports either mode.
    """
    mode = str(props.get("fill_mode", "solid"))
    color = str(props.get(color_key, "#4fd1c5"))
    color_end = str(props.get("color_end", "#1a3a4a"))
    angle = float(props.get("gradient_angle", 0))
    spread = float(props.get("gradient_spread", 1.0))

    kw = dict(
        color_hex=color,
        alpha=alpha,
        fill_mode=mode,
        color_end_hex=color_end if mode != "solid" else None,
        angle_deg=angle,
        spread=spread,
    )
    if box is not None:
        kw.update(x=box[0], y=box[1], w=box[2], h=box[3])
    if radial is not None:
        kw.update(cx=radial[0], cy=radial[1], radius=radial[2])

    return lua_set_source(**kw), lua_destroy_gradient_if_needed(mode)


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
