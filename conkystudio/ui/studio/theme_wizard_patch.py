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

# v2: every option a theme in codegen/theme_presets.py checks via
# opt.get(...), with a Simple/Full/Showcase default. Simple stays a flat
# "everything off" tier on purpose -- a theme's Simple build should be
# readable as *just* its signature element, nothing else. Full turns on
# the "solid, useful HUD" set: framing chrome, one status LED wired
# through a real logic chain, a trend graph, a second readout, and
# (new) gradient fills instead of flat colour. Showcase adds every
# animated flourish a theme has (its one signature_effect node, a
# smoothed/EMA-driven hero gauge, per-core strip, live process table,
# and a footer ticker line) on top of everything Full already has.
#
# OPTION_METADATA below is what a checkbox-panel UI should iterate to
# render per-tier toggles with a human label/help string, instead of
# hard-coding checkbox widgets per key.
DEFAULT_OPTIONS_BY_TIER = {
    "Simple": {
        "chrome": False, "leds": False, "graphs": False,
        "brackets": False, "glow": False,
        "gradient_fills": False, "secondary_gauge": False,
        "signature_effect": False, "footer_ticker": False,
        "orbit": False, "core_strip": False, "top_table": False, "smooth": False,
    },
    "Full": {
        "chrome": True, "leds": True, "graphs": True,
        "brackets": True, "glow": True,
        "gradient_fills": True, "secondary_gauge": True,
        "signature_effect": False, "footer_ticker": False,
        "orbit": False, "core_strip": False, "top_table": False, "smooth": True,
    },
    "Showcase": {
        "chrome": True, "leds": True, "graphs": True,
        "brackets": True, "glow": True,
        "gradient_fills": True, "secondary_gauge": True,
        "signature_effect": True, "footer_ticker": True,
        "orbit": True, "core_strip": True, "top_table": True, "smooth": True,
    },
}

# (key, label, help, min_tier) -- min_tier is the lowest tier at which the
# checkbox is shown at all (Simple never exposes any of these; a theme's
# Simple build ignores every option and always renders the same minimal
# layout, which is the whole point of the tier).
OPTION_METADATA: tuple[tuple[str, str, str, str], ...] = (
    ("chrome", "Framing chrome", "Corner brackets / dividers / background panel around the layout.", "Full"),
    ("brackets", "Corner brackets", "HUD-style corner marks framing the main readout.", "Full"),
    ("leds", "Status LED", "One alert LED wired through a real Source → Logic → Visual chain.", "Full"),
    ("graphs", "Trend graph", "A history graph or sparkline of a live value.", "Full"),
    ("secondary_gauge", "Secondary readout", "A second gauge/value next to the hero element (e.g. RAM beside CPU).", "Full"),
    ("gradient_fills", "Gradient fills", "Bars and gauges blend Colour → End colour instead of flat fill.", "Full"),
    ("glow", "Glow / pulse", "Soft animated halo around alert or hero elements.", "Full"),
    ("smooth", "Smoothed motion", "EMA-smooths the hero gauge's drive value so motion reads as fluid, not stepped.", "Full"),
    ("signature_effect", "Signature flourish", "The theme's one standout animated piece (radar sweep, matrix rain, vinyl spinner, spinning fan, ...).", "Showcase"),
    ("orbit", "Orbit / ring motion", "Decorative orbiting dots or rings around the hero element.", "Showcase"),
    ("core_strip", "Per-core CPU strip", "One bar per CPU core.", "Showcase"),
    ("top_table", "Live process table", "Busiest processes by CPU, rank/name/CPU%/MEM%.", "Showcase"),
    ("footer_ticker", "Footer ticker", "A small always-on line of extra live text (uptime, hostname, process count, ...).", "Showcase"),
)


def options_for_tier_ui(tier: str) -> list[dict]:
    """Checkbox rows a tier's options panel should show: key, label, help,
    default, and whether it's enabled (True) or unavailable (False) at this
    tier. Simple returns an empty list -- nothing to configure."""
    if tier == "Simple":
        return []
    tier_order = {"Simple": 0, "Full": 1, "Showcase": 2}
    rows = []
    for key, label, help_text, min_tier in OPTION_METADATA:
        if tier_order.get(tier, 1) < tier_order.get(min_tier, 1):
            continue
        rows.append({
            "key": key, "label": label, "help": help_text,
            "default": DEFAULT_OPTIONS_BY_TIER.get(tier, {}).get(key, False),
        })
    return rows


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
