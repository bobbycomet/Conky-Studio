"""
Shared helpers for theme_presets.py.

Every theme builder in theme_presets.py is a plain function that takes a
Project and calls into these helpers instead of hand-rolling
NodeInstance(...)/add_node/add_edge boilerplate for every node. This is
the same NodeInstance/new_id/add_node/add_edge API theme_wizard_patch.py
already uses -- nothing new is asked of Project or the node system here.

Nothing in this file is theme-specific. Palettes, layouts, and node
choices live in theme_presets.py; this is just plumbing + a few
generalized versions of patterns theme_wizard_patch.py already
established (ensure_logic_demo_edge, add_showcase_extras) so seven
themes don't each reimplement "smooth -> hysteresis -> LED".
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from conkystudio.model.project import Project, NodeInstance, new_id


def has_node(type_id: str) -> bool:
    try:
        from conkystudio.nodes import registry
        return registry.has(type_id)
    except Exception:
        return False


def pin_sensor_poll_mode(p: Project, mode: str = "execi") -> None:
    """Force every Sensors-subcategory source node already in `p` (CPU/GPU/
    disk temp, fan RPM, GPU util/VRAM -- see nodes/sources_external.py) to
    the given polling mode, regardless of how the node was created (mk(),
    demo_logic_chain(), or a raw NodeInstance(...) call in a layout
    builder). The registry's own default for those nodes is background-
    daemon (the right choice for a real, high-FPS HUD), but every theme
    builder that runs through the wizard is a teaching artifact: a
    newcomer inspecting a wizard-built sensor node's Properties panel
    should see the simpler, one-line `execi` mechanism first, with the
    zero-stutter daemon mode left as an opt-in upgrade rather than
    something the wizard springs on them silently. Call this once, after
    a theme/layout is fully built, so nothing built afterward can quietly
    undo it."""
    try:
        from conkystudio.nodes import registry
    except Exception:
        return
    for n in p.nodes:
        if not registry.has(n.type):
            continue
        spec = registry.get(n.type)
        if spec.category == "source" and spec.subcategory == "Sensors":
            n.props["poll_mode"] = mode


def mk(
    p: Project,
    type_id: str,
    x: int,
    y: int,
    props: Optional[dict] = None,
    *,
    z: Optional[int] = None,
    label: Optional[str] = None,
) -> Optional[NodeInstance]:
    """Add a node if its type is registered; no-op (returns None) otherwise,
    so a theme still builds on an install missing an optional extension
    module instead of raising mid-build."""
    if not has_node(type_id):
        return None
    node = NodeInstance(
        id=new_id("n"),
        type=type_id,
        x=x,
        y=y,
        z=(z if z is not None else p.next_z()),
        label=label,
        props=dict(props or {}),
    )
    return p.add_node(node)


def wire(p: Project, src: Optional[NodeInstance], dst: Optional[NodeInstance], prop_key: str) -> None:
    """Connect src's output into dst's prop_key, skipping quietly if either
    side is missing (e.g. an optional node type wasn't registered)."""
    if src is None or dst is None:
        return
    p.add_edge(src.id, dst.id, prop_key)


def gradient(style: dict, *, angle: float = 90.0, mode: str = "linear", spread: float = 1.0) -> dict:
    """Fill-mode prop dict for any node carrying _GRADIENT_FILL / GRADIENT_FILL_PROP_DICTS
    props (fill_mode / color_end / gradient_angle / gradient_spread)."""
    return {
        "fill_mode": mode,
        "color_end": style.get("accent2", style.get("accent", "#4fd1c5")),
        "gradient_angle": angle,
        "gradient_spread": spread,
    }


def maybe_gradient(style: dict, enabled: bool, **kw) -> dict:
    return gradient(style, **kw) if enabled else {}


# ---------------------------------------------------------------------
# Demo Source -> Logic -> Visual chain, generalized from
# theme_wizard_patch.ensure_logic_demo_edge so every theme can point the
# chain at ITS OWN alert target (an LED, an icon swap, a bar's pulse)
# instead of always spawning a fresh CPU->LED pair.
# ---------------------------------------------------------------------
def demo_logic_chain(
    p: Project,
    *,
    x0: int = -420,
    y: int = 260,
    source_type: str = "source.cpu_percent",
    source_props: Optional[dict] = None,
    smooth: bool = True,
    smooth_alpha: float = 0.2,
    gate_high: float = 85.0,
    gate_low: float = 70.0,
    label_prefix: str = "Demo",
) -> tuple[Optional[NodeInstance], Optional[NodeInstance]]:
    """Builds Source -> [Smooth] -> Hysteresis, returns (smoothed_value_node,
    gate_node). Either may be the same node as the source if smoothing/gating
    is unavailable. Caller wires smoothed_value_node into a gauge's Value
    and gate_node into an LED / pulse / icon-swap trigger."""
    src = mk(p, source_type, x0, y, dict(source_props or {}), label=f"{label_prefix}: source")
    value_out = src

    if smooth and has_node("logic.smooth"):
        sm = mk(p, "logic.smooth", x0 + 200, y,
                {"alpha": smooth_alpha, "init_from_input": True},
                label=f"{label_prefix}: smooth")
        wire(p, src, sm, "value")
        value_out = sm

    gate_out = value_out
    if has_node("logic.hysteresis"):
        hy = mk(p, "logic.hysteresis", x0 + 380, y,
                {"high": gate_high, "low": gate_low},
                label=f"{label_prefix}: gate")
        wire(p, value_out, hy, "value")
        gate_out = hy
    elif has_node("logic.threshold"):
        th = mk(p, "logic.threshold", x0 + 380, y,
                {"comparison": ">=", "threshold": gate_high})
        wire(p, value_out, th, "value")
        gate_out = th

    return value_out, gate_out


# ---------------------------------------------------------------------
# Common chrome pieces every theme can drop in identically -- position
# math and prop plumbing differ per shape, so these stay tiny wrappers
# rather than one giant parameterized mega-function.
# ---------------------------------------------------------------------
def frame_brackets(p: Project, style: dict, x: int, y: int, w: int, h: int, *, opacity: float = 0.55) -> None:
    mk(p, "visual.corner_brackets", x, y, {
        "x": x, "y": y, "width": w, "height": h,
        "arm_length": max(14, min(w, h) // 8), "thickness": 2.0,
        "color": style["accent"], "opacity": opacity,
    })


def title_row(p: Project, style: dict, x: int, y: int, text: str, *, size: int = 20, font_key: str = "font_display") -> None:
    mk(p, "visual.text", x, y, {
        "value": text, "x": x, "y": y, "align": "left",
        "font_family": style.get(font_key, style.get("font", "Sans")),
        "font_size": size, "bold": True, "color": style["text"],
    })


def caption_row(p: Project, style: dict, x: int, y: int, text: str, *, size: int = 10, color_key: str = "text_dim") -> None:
    mk(p, "visual.text", x, y, {
        "value": text, "x": x, "y": y, "align": "left",
        "font_family": style.get("font", "Sans"), "font_size": size,
        "color": style.get(color_key, "#9aa2ad"),
    })


def stat_bar_row(
    p: Project,
    style: dict,
    x: int,
    y: int,
    width: int,
    label: str,
    source: Optional[NodeInstance],
    *,
    height: int = 10,
    gradient_on: bool = False,
    grad_angle: float = 0.0,
    bar_style: str = "solid",
) -> Optional[NodeInstance]:
    """Caption above a horizontal Bar, wired to `source`'s output if given."""
    caption_row(p, style, x, y, label, size=10)
    bar = mk(p, "visual.bar", x, y + 13, {
        "x": x, "y": y + 13, "width": width, "height": height,
        "style": bar_style, "min_value": 0, "max_value": 100,
        "color": style["accent"], "track_color": style["track"],
        **maybe_gradient(style, gradient_on, angle=grad_angle),
    })
    wire(p, source, bar, "value")
    return bar


def footer_clock_date(
    p: Project,
    style: dict,
    x: int,
    y: int,
    *,
    align: str = "left",
    font_key: str = "font",
    size: int = 13,
    fmt: str = "%A, %B %d  ·  %H:%M",
) -> None:
    """A single Date/Time source feeding one Text label -- the small
    always-on footer every theme wants somewhere."""
    dt = mk(p, "source.datetime", x - 300, y, {"strftime_format": fmt}, label="Footer: date/time")
    label = mk(p, "visual.text", x, y, {
        "value": "", "x": x, "y": y, "align": align,
        "font_family": style.get(font_key, style.get("font", "Sans")),
        "font_size": size, "color": style.get("text_dim", "#9aa2ad"),
    })
    wire(p, dt, label, "value")
