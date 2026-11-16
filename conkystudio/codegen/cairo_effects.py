"""
Blend-operator and group-compositing codegen helpers.

These wrap a block of already-generated Lua drawing code (the same shape
as the `body` argument to color.lua_with_fill_source) rather than emitting
a single expression -- an operator change or a push_group/pop_group pair
only makes sense around a whole draw sequence, not one call.

Usage in a visual generator
----------------------------
    from conkystudio.codegen.cairo_effects import lua_with_operator, lua_with_group

    draw_lines = [...]  # normal cairo_* calls, same as any generator today
    body = "\\n".join(draw_lines)

    # Additive blend for a glow/energy look:
    body = lua_with_operator(body, "add")

    # Isolate a multi-primitive shape so opacity applies once to the
    # composite instead of per-primitive (fixes double-blended overlaps):
    body = lua_with_group(body, alpha=opacity)

Both helpers save/restore cr's full state around the change, so nothing
leaks into whatever the framework draws next -- safe to nest, and safe to
drop into any existing generator without auditing the rest of the file.

Requires the Cairo build conky links against to expose cairo_set_operator
/ cairo_push_group / cairo_pop_group_to_source / cairo_paint_with_alpha
via its Lua binding. All four are long-standing core Cairo API (present
since 1.0/1.2), but bindings do vary -- if a symbol is missing you'll get
a Lua "attempt to call a nil value" at render time rather than a build
error, so smoke-test after adding a new operator/group node type.
"""
from __future__ import annotations

from typing import Optional

# Friendly name -> CAIRO_OPERATOR_* constant. Compositing operators first
# (the common case: mimics Porter-Duff over/add/etc.), then the separable
# blend modes (Cairo 1.10+, same set browsers call "mix-blend-mode").
OPERATORS = {
    "over": "CAIRO_OPERATOR_OVER",
    "clear": "CAIRO_OPERATOR_CLEAR",
    "source": "CAIRO_OPERATOR_SOURCE",
    "in": "CAIRO_OPERATOR_IN",
    "out": "CAIRO_OPERATOR_OUT",
    "atop": "CAIRO_OPERATOR_ATOP",
    "dest": "CAIRO_OPERATOR_DEST",
    "dest_over": "CAIRO_OPERATOR_DEST_OVER",
    "dest_in": "CAIRO_OPERATOR_DEST_IN",
    "dest_out": "CAIRO_OPERATOR_DEST_OUT",
    "dest_atop": "CAIRO_OPERATOR_DEST_ATOP",
    "xor": "CAIRO_OPERATOR_XOR",
    "add": "CAIRO_OPERATOR_ADD",
    "saturate": "CAIRO_OPERATOR_SATURATE",
    "multiply": "CAIRO_OPERATOR_MULTIPLY",
    "screen": "CAIRO_OPERATOR_SCREEN",
    "overlay": "CAIRO_OPERATOR_OVERLAY",
    "darken": "CAIRO_OPERATOR_DARKEN",
    "lighten": "CAIRO_OPERATOR_LIGHTEN",
    "color_dodge": "CAIRO_OPERATOR_COLOR_DODGE",
    "color_burn": "CAIRO_OPERATOR_COLOR_BURN",
    "hard_light": "CAIRO_OPERATOR_HARD_LIGHT",
    "soft_light": "CAIRO_OPERATOR_SOFT_LIGHT",
    "difference": "CAIRO_OPERATOR_DIFFERENCE",
    "exclusion": "CAIRO_OPERATOR_EXCLUSION",
    "hsl_hue": "CAIRO_OPERATOR_HSL_HUE",
    "hsl_saturation": "CAIRO_OPERATOR_HSL_SATURATION",
    "hsl_color": "CAIRO_OPERATOR_HSL_COLOR",
    "hsl_luminosity": "CAIRO_OPERATOR_HSL_LUMINOSITY",
}

# Property dict for visuals.py, same convention as color.GRADIENT_FILL_PROP_DICTS.
BLEND_OPERATOR_PROP_DICT = {
    "key": "blend_mode",
    "label": "Blend mode",
    "kind": "enum",
    "default": "over",
    "choices": ["over", "add", "screen", "multiply", "lighten", "darken", "difference"],
    "choice_labels": [
        "Normal", "Additive (glow)", "Screen", "Multiply", "Lighten", "Darken", "Difference",
    ],
    "group": "Style",
    "help": (
        "How this shape composites onto what's already drawn. Additive is the "
        "usual choice for glow/energy effects; Multiply/Darken for grounding "
        "shadows onto a bright background."
    ),
}


def _operator_const(name: str) -> str:
    return OPERATORS.get((name or "over").lower(), "CAIRO_OPERATOR_OVER")


def lua_set_operator(op: str, cr: str = "cr") -> str:
    """Emit a *safe* operator set: many Conky Lua Cairo builds omit
    cairo_set_operator / CAIRO_OPERATOR_* entirely. Calling a nil C
    binding crashes the process (exit 11); guard with type checks."""
    const = _operator_const(op)
    return (
        f"if type(cairo_set_operator) == 'function' and {const} ~= nil then "
        f"cairo_set_operator({cr}, {const}) end"
    )


def lua_with_operator(body: str, op: str, cr: str = "cr") -> str:
    """Wrap *body* (draw calls only — not a whole `local function ... end`)
    so it draws under the given blend operator, then restores OVER.

    Safe on Conky builds without operator bindings (no-ops the blend).
    A no-op ('over') returns *body* unchanged."""
    mode = (op or "over").lower()
    if mode == "over":
        return body
    # Indent body lines so they sit cleanly inside the save/restore block
    indented = "\n".join(
        ("    " + ln if ln.strip() else ln) for ln in body.splitlines()
    )
    lines = [
        f"cairo_save({cr})",
        lua_set_operator(mode, cr),
        indented,
        (
            f"if type(cairo_set_operator) == 'function' and CAIRO_OPERATOR_OVER ~= nil then "
            f"cairo_set_operator({cr}, CAIRO_OPERATOR_OVER) end"
        ),
        f"cairo_restore({cr})",
    ]
    return "\n".join(lines)


def lua_push_group(cr: str = "cr") -> str:
    return f"cairo_push_group({cr})"


def lua_pop_group_paint_alpha(alpha: "str | float" = 1, cr: str = "cr") -> str:
    a = alpha if isinstance(alpha, str) else repr(float(alpha))
    return (
        f"cairo_pop_group_to_source({cr})\n"
        f"cairo_paint_with_alpha({cr}, {a})"
    )


def lua_with_group(
    body: str,
    *,
    alpha: "str | float" = 1,
    operator: Optional[str] = None,
    cr: str = "cr",
) -> str:
    """Wrap *body* in cairo_push_group/pop_group_to_source so it's
    composited onto the canvas as a single flattened layer.

    Two independent things this buys you over drawing straight to *cr*:

    1. *alpha* applies once to the finished composite instead of per
       primitive -- fixes the "overlapping translucent shapes go darker
       where they cross" look when a shape is built from several
       cairo_fill/cairo_stroke calls but should read as one semi
       transparent object (e.g. a multi-layer needle gauge at 60% opacity).

    2. *operator*, if given, is the blend mode used when the finished
       group is composited back -- e.g. operator='add' turns a whole
       multi-stroke glow into true additive blending against the
       background in one step, rather than each layer additively
       blending against the ones under it (which double-brightens
       overlaps and looks patchy). This is the group-based alternative
       to wrapping every layer individually with lua_with_operator.
    """
    a = alpha if isinstance(alpha, str) else repr(float(alpha))
    lines = [lua_push_group(cr), body]
    if operator and operator.lower() != "over":
        op_const = _operator_const(operator)
        lines.append(
            f"cairo_pop_group_to_source({cr})\n"
            f"if type(cairo_set_operator) == 'function' and {op_const} ~= nil then "
            f"cairo_set_operator({cr}, {op_const}) end\n"
            f"cairo_paint_with_alpha({cr}, {a})\n"
            f"if type(cairo_set_operator) == 'function' and CAIRO_OPERATOR_OVER ~= nil then "
            f"cairo_set_operator({cr}, CAIRO_OPERATOR_OVER) end"
        )
    else:
        lines.append(lua_pop_group_paint_alpha(a, cr))
    return "\n".join(lines)


def lua_mask_gradient(
    *,
    color_hex: str = "#ffffff",
    fill_mode: str = "linear",
    color_end_hex: str = "#ffffff",
    stops=None,
    x: "str | float" = 0,
    y: "str | float" = 0,
    w: "str | float" = 0,
    h: "str | float" = 0,
    angle_deg: "str | float" = 0,
    cx: "str | float" = 0,
    cy: "str | float" = 0,
    radius: "str | float" = 0,
    spread: "str | float" = 1.0,
    cr: str = "cr",
) -> str:
    """Build a gradient pattern and use it as an alpha MASK over whatever
    fill/source is already set on *cr*, instead of as the source itself.
    The gradient's own colour is irrelevant to the mask alpha channel --
    only each stop's alpha matters -- so pass two stops with the same
    colour but different alpha (e.g. 1 -> 0) to fade a shape out along an
    axis: a trailing history-graph edge, or a top-down vignette.

    Caller must have already set the real fill source on *cr* (solid or
    via lua_set_source) and built the path to be masked before this runs;
    this only emits pattern-build + cairo_mask + destroy.
    """
    from .color import lua_set_source, lua_destroy_gradient_if_needed

    # lua_set_source always assigns into local `_grad` and also calls
    # cairo_set_source(cr, _grad) as a side effect; for a mask we want the
    # pattern built but NOT set as the source (mask draws with whatever
    # source is already current), so build it under fill_mode as given and
    # simply don't use the trailing cairo_set_source(...) line.
    built = lua_set_source(
        color_hex=color_hex,
        fill_mode=fill_mode,
        color_end_hex=color_end_hex,
        stops=stops,
        x=x, y=y, w=w, h=h,
        angle_deg=angle_deg,
        cx=cx, cy=cy, radius=radius,
        spread=spread,
        cr=cr,
    )
    build_lines = built.splitlines()
    # Drop the final `cairo_set_source(cr, _grad)` line -- mask consumes
    # _grad directly and must not disturb the caller's real source.
    build_lines = [ln for ln in build_lines if not ln.strip().startswith("cairo_set_source(")]
    destroy = lua_destroy_gradient_if_needed(fill_mode)
    lines = build_lines + [f"cairo_mask({cr}, _grad)"]
    if destroy:
        lines.append(destroy)
    return "\n".join(lines)


def lua_mask_surface(surface_var: str, x: "str | float" = 0, y: "str | float" = 0, cr: str = "cr") -> str:
    """Mask whatever source is current on *cr* through an image surface's
    alpha channel (e.g. a loaded PNG icon shape) -- surface_var is the
    Lua variable holding a `cairo_image_surface_t*`, such as the `.surface`
    field returned by the framework's load_image_cached()."""
    x_e = x if isinstance(x, str) else repr(float(x))
    y_e = y if isinstance(y, str) else repr(float(y))
    return f"cairo_mask_surface({cr}, {surface_var}, {x_e}, {y_e})" 

