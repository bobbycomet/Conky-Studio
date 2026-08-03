"""Hex string <-> Cairo float-triple colour conversion for codegen.

Also emits Cairo gradient pattern setup for linear / radial fills so every
visual generator can opt into gradients without re-implementing stop logic.
"""
from __future__ import annotations

from typing import Optional


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


def lua_set_source(
    *,
    color_hex: str,
    alpha: str | float = 1,
    fill_mode: str = "solid",
    color_end_hex: Optional[str] = None,
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
    """Return Lua that sets the current source on *cr* to solid or 2-stop gradient.

    Geometry values may be Lua expressions (strings) or Python numbers.
    When mode is linear/radial, creates local _grad; destroy after fill/stroke
    via lua_destroy_gradient_if_needed().
    """
    mode = (fill_mode or "solid").lower()
    a = alpha if isinstance(alpha, str) else repr(float(alpha))

    if mode == "solid" or not color_end_hex:
        rgb = lua_rgb_literal(color_hex)
        return f"cairo_set_source_rgba({cr}, {rgb}, {a})"

    r0, g0, b0 = hex_to_rgb01(color_hex)
    r1, g1, b1 = hex_to_rgb01(color_end_hex)

    if mode == "radial":
        cx_e = cx if isinstance(cx, str) else repr(float(cx))
        cy_e = cy if isinstance(cy, str) else repr(float(cy))
        rad_e = radius if isinstance(radius, str) else repr(float(radius))
        sp_e = spread if isinstance(spread, str) else repr(float(spread))
        return (
            f"local _grad = cairo_pattern_create_radial("
            f"{cx_e}, {cy_e}, 0, {cx_e}, {cy_e}, ({rad_e}) * ({sp_e}))\n"
            f"cairo_pattern_add_color_stop_rgba(_grad, 0, {r0}, {g0}, {b0}, {a})\n"
            f"cairo_pattern_add_color_stop_rgba(_grad, 1, {r1}, {g1}, {b1}, {a})\n"
            f"cairo_set_source({cr}, _grad)"
        )

    x_e = x if isinstance(x, str) else repr(float(x))
    y_e = y if isinstance(y, str) else repr(float(y))
    w_e = w if isinstance(w, str) else repr(float(w))
    h_e = h if isinstance(h, str) else repr(float(h))
    ang_e = angle_deg if isinstance(angle_deg, str) else repr(float(angle_deg))

    return (
        f"local _gx = ({x_e}) + ({w_e}) / 2\n"
        f"local _gy = ({y_e}) + ({h_e}) / 2\n"
        f"local _glen = math.max(({w_e}), ({h_e})) / 2\n"
        f"local _grad_a = math.rad({ang_e})\n"
        f"local _grad = cairo_pattern_create_linear(\n"
        f"  _gx - math.cos(_grad_a) * _glen, _gy - math.sin(_grad_a) * _glen,\n"
        f"  _gx + math.cos(_grad_a) * _glen, _gy + math.sin(_grad_a) * _glen)\n"
        f"cairo_pattern_add_color_stop_rgba(_grad, 0, {r0}, {g0}, {b0}, {a})\n"
        f"cairo_pattern_add_color_stop_rgba(_grad, 1, {r1}, {g1}, {b1}, {a})\n"
        f"cairo_set_source({cr}, _grad)"
    )


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
]

