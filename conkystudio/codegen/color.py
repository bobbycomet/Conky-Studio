"""Hex string <-> Cairo float-triple colour conversion for codegen.

Also emits Cairo gradient pattern setup for linear / radial fills so every
visual generator can opt into gradients without re-implementing stop logic.

v1.1: gradients are no longer limited to 2 stops, and can now set a
CAIRO_EXTEND_* mode. Both are opt-in and fully backward compatible --
existing callers that only pass color_hex/color_end_hex get byte-identical
output to before, since the new stops/extend_mode params default to the
old 2-stop/'pad' behaviour (Cairo's own default extend for gradients is
already PAD, so the extend line is only emitted when something else is
requested).
"""
from __future__ import annotations

from typing import Optional, Sequence, Union

# (offset 0..1, hex colour, alpha) -- alpha may be None to fall back to the
# fill's overall alpha, same as the old 2-stop behaviour did implicitly.
GradientStop = tuple[Union[str, float], str, Optional[Union[str, float]]]

_EXTEND_MODES = {
    "pad": "CAIRO_EXTEND_PAD",
    "none": "CAIRO_EXTEND_NONE",
    "repeat": "CAIRO_EXTEND_REPEAT",
    "reflect": "CAIRO_EXTEND_REFLECT",
}


def hex_to_rgb01(hex_str: str) -> tuple[float, float, float]:
    """'#4fd1c5' -> (0.310, 0.820, 0.773). Tolerant of missing '#' and 3-digit shorthand."""
    s = (hex_str or "#FFFFFF").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        s = "FFFFFF"
    try:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
    except ValueError:
        r = g = b = 1.0
    return (round(r, 4), round(g, 4), round(b, 4))


def lua_rgb_literal(hex_str: str) -> str:
    """'#4fd1c5' -> '0.3098, 0.8196, 0.7725' -- ready to splice into a
    cairo_set_source_rgba(cr, <this>, alpha) call."""
    r, g, b = hex_to_rgb01(hex_str)
    return f"{r}, {g}, {b}"


def lua_pattern_stops(stops: Sequence[GradientStop], default_alpha: str = "1") -> str:
    """Emit N `cairo_pattern_add_color_stop_rgba(_grad, ...)` lines for an
    arbitrary list of (offset, hex[, alpha]) stops against the *_grad*
    local created by lua_set_source. offset is 0..1 (Python number or a
    Lua-expression string, same convention as the rest of this module).
    Per-stop alpha may be omitted/None to fall back to *default_alpha*."""
    lines = []
    for stop in stops:
        offset, hex_color = stop[0], stop[1]
        alpha = stop[2] if len(stop) > 2 and stop[2] is not None else default_alpha
        off_e = offset if isinstance(offset, str) else repr(float(offset))
        a_e = alpha if isinstance(alpha, str) else repr(float(alpha))
        r, g, b = hex_to_rgb01(hex_color)
        lines.append(
            f"cairo_pattern_add_color_stop_rgba(_grad, {off_e}, {r}, {g}, {b}, {a_e})"
        )
    return "\n".join(lines)


def lua_pattern_extend(extend_mode: str = "pad") -> str:
    """`cairo_pattern_set_extend(_grad, CAIRO_EXTEND_*)` line for the
    current _grad pattern, or '' for 'pad' -- Cairo's own default for
    gradient patterns, so there's nothing to emit unless the caller wants
    something else. 'repeat'/'reflect' turn a short gradient into a
    striped/barber-pole fill (e.g. a moving "charging" bar); 'none' lets
    the pattern's own edge colour show through as fully transparent past
    its extent instead of holding the last stop."""
    mode = (extend_mode or "pad").lower()
    if mode == "pad":
        return ""
    const = _EXTEND_MODES.get(mode, "CAIRO_EXTEND_PAD")
    return f"cairo_pattern_set_extend(_grad, {const})"


def lua_set_source(
    *,
    color_hex: str,
    alpha: str | float = 1,
    fill_mode: str = "solid",
    color_end_hex: Optional[str] = None,
    stops: Optional[Sequence[GradientStop]] = None,
    extend_mode: str = "pad",
    x: str | float = 0,
    y: str | float = 0,
    w: str | float = 0,
    h: str | float = 0,
    angle_deg: str | float = 0,
    cx: str | float = 0,
    cy: str | float = 0,
    radius: str | float = 0,
    spread: str | float = 1.0,
    cr: str = "cr",
) -> str:
    """Return Lua that sets the current source on *cr* to solid or a
    linear/radial gradient.

    Geometry values may be Lua expressions (strings) or Python numbers.

    Gradient stops: pass *stops* as a list of (offset, hex[, alpha])
    tuples for an arbitrary N-stop gradient. If *stops* is omitted, falls
    back to the original 2-stop behaviour using color_hex/color_end_hex
    as offsets 0 and 1 -- existing callers need no changes.

    extend_mode: 'pad' (default), 'repeat', 'reflect', or 'none' -- see
    lua_pattern_extend().

    When mode is linear/radial, creates local _grad; destroy after
    fill/stroke via lua_destroy_gradient_if_needed().
    """
    mode = (fill_mode or "solid").lower()
    a = alpha if isinstance(alpha, str) else repr(float(alpha))

    if mode == "solid" or (not color_end_hex and not stops):
        rgb = lua_rgb_literal(color_hex)
        return f"cairo_set_source_rgba({cr}, {rgb}, {a})"

    if stops:
        stop_lines = lua_pattern_stops(stops, default_alpha=a)
    else:
        r0, g0, b0 = hex_to_rgb01(color_hex)
        r1, g1, b1 = hex_to_rgb01(color_end_hex)
        stop_lines = (
            f"cairo_pattern_add_color_stop_rgba(_grad, 0, {r0}, {g0}, {b0}, {a})\n"
            f"cairo_pattern_add_color_stop_rgba(_grad, 1, {r1}, {g1}, {b1}, {a})"
        )

    extend_line = lua_pattern_extend(extend_mode)

    if mode == "radial":
        cx_e = cx if isinstance(cx, str) else repr(float(cx))
        cy_e = cy if isinstance(cy, str) else repr(float(cy))
        rad_e = radius if isinstance(radius, str) else repr(float(radius))
        sp_e = spread if isinstance(spread, str) else repr(float(spread))
        parts = [
            f"local _grad = cairo_pattern_create_radial("
            f"{cx_e}, {cy_e}, 0, {cx_e}, {cy_e}, ({rad_e}) * ({sp_e}))",
            stop_lines,
        ]
        if extend_line:
            parts.append(extend_line)
        parts.append(f"cairo_set_source({cr}, _grad)")
        return "\n".join(parts)

    x_e = x if isinstance(x, str) else repr(float(x))
    y_e = y if isinstance(y, str) else repr(float(y))
    w_e = w if isinstance(w, str) else repr(float(w))
    h_e = h if isinstance(h, str) else repr(float(h))
    ang_e = angle_deg if isinstance(angle_deg, str) else repr(float(angle_deg))

    parts = [
        f"local _gx = ({x_e}) + ({w_e}) / 2",
        f"local _gy = ({y_e}) + ({h_e}) / 2",
        f"local _glen = math.max(({w_e}), ({h_e})) / 2",
        f"local _grad_a = math.rad({ang_e})",
        f"local _grad = cairo_pattern_create_linear(",
        f"  _gx - math.cos(_grad_a) * _glen, _gy - math.sin(_grad_a) * _glen,",
        f"  _gx + math.cos(_grad_a) * _glen, _gy + math.sin(_grad_a) * _glen)",
        stop_lines,
    ]
    if extend_line:
        parts.append(extend_line)
    parts.append(f"cairo_set_source({cr}, _grad)")
    return "\n".join(parts)


def lua_destroy_gradient_if_needed(fill_mode: str = "solid") -> str:
    mode = (fill_mode or "solid").lower()
    if mode in ("linear", "radial"):
        return "if _grad then cairo_pattern_destroy(_grad) end"
    return ""


def lua_with_fill_source(
    *,
    body: str,
    color_hex: str,
    alpha: str | float = 1,
    fill_mode: str = "solid",
    color_end_hex: Optional[str] = None,
    stops: Optional[Sequence[GradientStop]] = None,
    extend_mode: str = "pad",
    x: str | float = 0,
    y: str | float = 0,
    w: str | float = 0,
    h: str | float = 0,
    angle_deg: str | float = 0,
    cx: str | float = 0,
    cy: str | float = 0,
    radius: str | float = 0,
    spread: str | float = 1.0,
    cr: str = "cr",
) -> str:
    setup = lua_set_source(
        color_hex=color_hex,
        alpha=alpha,
        fill_mode=fill_mode,
        color_end_hex=color_end_hex,
        stops=stops,
        extend_mode=extend_mode,
        x=x, y=y, w=w, h=h,
        angle_deg=angle_deg,
        cx=cx, cy=cy, radius=radius,
        spread=spread,
        cr=cr,
    )
    destroy = lua_destroy_gradient_if_needed(fill_mode)
    lines = [setup] + [ln for ln in body.splitlines()]
    if destroy:
        lines.append(destroy)
    return "\n".join(lines)


# Property dicts for visuals.py — convert to PropertySpec and append.
GRADIENT_FILL_PROP_DICTS = [
    {
        "key": "fill_mode",
        "label": "Fill mode",
        "kind": "enum",
        "default": "solid",
        "choices": ["solid", "linear", "radial"],
        "choice_labels": ["Solid", "Linear gradient", "Radial gradient"],
        "group": "Style",
        "help": "Solid uses Colour only. Linear/Radial blend Colour to End colour.",
    },
    {
        "key": "color_end",
        "label": "End colour",
        "kind": "color",
        "default": "#1a3a4a",
        "group": "Style",
        "help": "Second stop for linear/radial. Ignored when Fill mode is Solid.",
    },
    {
        "key": "gradient_angle",
        "label": "Gradient angle",
        "kind": "float",
        "default": 0.0,
        "minimum": -360,
        "maximum": 360,
        "step": 1,
        "group": "Style",
        "help": "Linear direction in degrees (0 = left to right, 90 = top to bottom).",
    },
    {
        "key": "gradient_spread",
        "label": "Radial spread",
        "kind": "float",
        "default": 1.0,
        "minimum": 0.1,
        "maximum": 3.0,
        "step": 0.05,
        "group": "Style",
        "help": "Radial only: outer stop as a multiple of the shape radius.",
    },
    {
        "key": "gradient_extend",
        "label": "Extend",
        "kind": "enum",
        "default": "pad",
        "choices": ["pad", "repeat", "reflect", "none"],
        "choice_labels": ["Pad (default)", "Repeat", "Reflect", "None"],
        "group": "Style",
        "help": (
            "What happens past the gradient's own extent. Repeat/Reflect turn a "
            "short gradient into a stripe pattern -- e.g. a moving charge/scan "
            "effect on a bar. Ignored when Fill mode is Solid."
        ),
    },
]

