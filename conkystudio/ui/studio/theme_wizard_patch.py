"""
v1.0.6 Theme Wizard helpers — complexity tiers, logic demo edge, showcase extras.

Place next to theme_wizard.py:

    conkystudio/ui/studio/theme_wizard.py
    conkystudio/ui/studio/theme_wizard_patch.py

Imported by theme_wizard.py. Safe if extension nodes are missing (_has_node gates).
"""
from __future__ import annotations

from conkystudio.model.project import Project, NodeInstance, new_id

COMPLEXITY_TIERS = ("Simple", "Full", "Showcase")

DEFAULT_OPTIONS_BY_TIER = {
    "Simple": {
        "chrome": False, "leds": False, "graphs": False,
        "brackets": False, "glow": False,
    },
    "Full": {
        "chrome": True, "leds": True, "graphs": True,
        "brackets": True, "glow": True,
    },
    "Showcase": {
        "chrome": True, "leds": True, "graphs": True,
        "brackets": True, "glow": True,
        "orbit": True, "core_strip": True, "top_table": True, "smooth": True,
    },
}


def _has_node(type_id: str) -> bool:
    try:
        from conkystudio.nodes import registry
        return registry.has(type_id)
    except Exception:
        return False


def merge_options_for_tier(tier: str, user_options: dict | None) -> dict:
    """Tier defaults, then user checkbox overrides."""
    base = dict(DEFAULT_OPTIONS_BY_TIER.get(tier, DEFAULT_OPTIONS_BY_TIER["Full"]))
    if user_options:
        base.update(user_options)
    if tier == "Showcase":
        base.setdefault("orbit", True)
        base.setdefault("core_strip", True)
        base.setdefault("top_table", True)
        base.setdefault("smooth", True)
    return base


def ensure_logic_demo_edge(p: Project, style: dict | None = None) -> None:
    """
    Guarantee at least one Source → Logic → Visual chain.
    Idempotent if a logic node is already wired in the graph.
    """
    style = style or {"accent": "#4fd1c5", "track": "#33313a", "warn": "#ff6b6b"}
    try:
        from conkystudio.nodes import registry
        for e in p.edges:
            n = p.node(e.src_node)
            if n and registry.has(n.type) and registry.get(n.type).category == "logic":
                return
    except Exception:
        pass

    cpu = next((n for n in p.nodes if n.type == "source.cpu_percent"), None)
    if cpu is None:
        cpu = p.add_node(NodeInstance(
            id=new_id("n"), type="source.cpu_percent", x=-420, y=200,
            label="Demo: CPU %",
        ))

    logic_out = cpu
    if _has_node("logic.smooth"):
        smooth = p.add_node(NodeInstance(
            id=new_id("n"), type="logic.smooth", x=-220, y=200,
            label="Demo: Smooth",
            props={"alpha": 0.2, "init_from_input": True},
        ))
        p.add_edge(cpu.id, smooth.id, "value")
        logic_out = smooth

    gate = logic_out
    if _has_node("logic.hysteresis"):
        hyst = p.add_node(NodeInstance(
            id=new_id("n"), type="logic.hysteresis", x=-40, y=200,
            label="Demo: Hot?",
            props={"high": 85.0, "low": 70.0},
        ))
        p.add_edge(logic_out.id, hyst.id, "value")
        gate = hyst
    elif _has_node("logic.threshold"):
        gate = p.add_node(NodeInstance(
            id=new_id("n"), type="logic.threshold", x=-40, y=200,
            props={"comparison": ">=", "threshold": 85.0},
        ))
        p.add_edge(logic_out.id, gate.id, "value")

    if _has_node("visual.led_dot"):
        led = p.add_node(NodeInstance(
            id=new_id("n"), type="visual.led_dot", z=p.next_z(),
            x=120, y=200, label="Demo: Warn LED",
            props={
                "cx": 36, "cy": 36, "radius": 7, "threshold": 0.5,
                "color_on": style.get("warn", "#ff6b6b"),
                "color_off": style.get("track", "#33313a"),
                "glow": True,
            },
        ))
        p.add_edge(gate.id, led.id, "value")


def add_showcase_extras(
    p: Project,
    style: dict,
    width: int,
    height: int,
    options: dict,
) -> None:
    """Orbit field, core strip, top table when Showcase (or option flags) request them."""
    accent = style.get("accent", "#4fd1c5")
    font = style.get("font", "Sans")
    dim = style.get("text_dim", "#9aa2ad")
    track = style.get("track", "#33313a")

    if options.get("core_strip") and _has_node("visual.core_strip"):
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.core_strip", z=p.next_z(),
            x=48, y=height - 100,
            props={
                "x": 48, "y": height - 90, "core_count": 8,
                "bar_width": 12, "bar_height": 40, "gap": 3,
                "color": accent, "track_color": track,
                "heat_map": True, "show_labels": True,
            },
        ))
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.text", z=p.next_z(), x=48, y=height - 120,
            props={
                "value": "CPU CORES", "x": 48, "y": height - 108,
                "font_family": font, "font_size": 10, "color": dim,
            },
        ))

    if options.get("top_table") and _has_node("visual.top_table"):
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.top_table", z=p.next_z(),
            x=width - 360, y=height - 160,
            props={
                "x": width - 340, "y": height - 150, "rows": 5,
                "font_family": font, "font_size": 11,
                "color": "#e8eaed", "header_color": accent,
            },
        ))

    if options.get("orbit") and _has_node("visual.orbit_field"):
        orbit = p.add_node(NodeInstance(
            id=new_id("n"), type="visual.orbit_field", z=p.next_z(),
            x=width // 2 - 80, y=80,
            props={
                "cx": width // 2, "cy": min(160, height // 4),
                "radius": 55, "dot_count": 14, "rings": 2,
                "color": accent, "speed_dps": 30, "opacity": 0.7,
            },
        ))
        cpu = next((n for n in p.nodes if n.type == "source.cpu_percent"), None)
        if cpu is not None:
            p.add_edge(cpu.id, orbit.id, "trigger")
