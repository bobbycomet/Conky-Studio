"""
Denser layout builders for non-Batman categories (Full / Showcase).

Call from existing LAYOUT_BUILDERS after the original sparse builder, or
replace the sparse body when complexity != Simple.

These functions are additive: they place extra chrome + new nodes without
removing the original panel functions from theme_wizard.py.
"""
from __future__ import annotations

from conkystudio.model.project import Project, NodeInstance, new_id

try:
    from conkystudio.ui.studio.theme_wizard_patch import (
        ensure_logic_demo_edge,
        add_showcase_extras,
    )
except ImportError:
    try:
        from conkystudio.extensions.ui.theme_wizard_patch import (  # type: ignore
            ensure_logic_demo_edge,
            add_showcase_extras,
        )
    except ImportError:
        def ensure_logic_demo_edge(p, style=None):
            pass

        def add_showcase_extras(p, style, width, height, options):
            pass


def _has(t: str) -> bool:
    try:
        from conkystudio.nodes import registry
        return registry.has(t)
    except Exception:
        return False


def densify_layout(
    p: Project,
    style: dict,
    panels: list,
    width: int,
    height: int,
    options: dict,
    complexity: str = "Full",
) -> None:
    """Run after the category builder to layer complexity features."""
    if complexity == "Simple":
        return

    ensure_logic_demo_edge(p, style)

    # Corner brackets if available and requested
    if options.get("brackets") and _has("visual.corner_brackets"):
        pad, arm = 10, 28
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.corner_brackets", z=0, x=0, y=0,
            props={
                "x": pad, "y": pad,
                "width": width - pad * 2, "height": height - pad * 2,
                "arm_length": arm, "thickness": 2.0,
                "color": style.get("accent", "#4fd1c5"), "opacity": 0.4,
            },
        ))

    # Secondary header rule
    if options.get("chrome") and _has("visual.hline"):
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.hline", z=1, x=40, y=70,
            props={
                "x": 48, "y": 72, "length": min(480, width // 3),
                "line_width": 1.0, "color": style.get("accent", "#4fd1c5"),
                "opacity": 0.35,
            },
        ))

    if complexity == "Showcase":
        add_showcase_extras(p, style, width, height, options)


def build_scifi_dense_extras(p: Project, style: dict, width: int, height: int) -> None:
    """Sci-Fi specific: crosshair + ring tracks around centre."""
    cx, cy = width // 2, height // 2
    accent = style.get("accent", "#26fdf1")
    track = style.get("track", "#0a3a40")
    if _has("visual.crosshair"):
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.crosshair", z=p.next_z(), x=cx, y=cy,
            props={"cx": cx, "cy": cy, "size": 32, "gap": 6, "color": accent, "opacity": 0.5},
        ))
    if _has("visual.ring_track"):
        for rad, op in ((90, 0.35), (110, 0.25), (130, 0.18)):
            p.add_node(NodeInstance(
                id=new_id("n"), type="visual.ring_track", z=p.next_z(),
                x=cx - rad, y=cy - rad,
                props={
                    "cx": cx, "cy": cy, "radius": rad, "thickness": 2,
                    "start_angle_deg": -120, "sweep_deg": 300,
                    "color": track, "opacity": op,
                },
            ))
    if _has("visual.orbit_field"):
        orbit = p.add_node(NodeInstance(
            id=new_id("n"), type="visual.orbit_field", z=p.next_z(),
            x=cx - 60, y=cy - 60,
            props={
                "cx": cx, "cy": cy, "radius": 75, "dot_count": 16, "rings": 2,
                "color": accent, "speed_dps": 40, "opacity": 0.75,
            },
        ))
        cpu = next((n for n in p.nodes if n.type == "source.cpu_percent"), None)
        if cpu:
            p.add_edge(cpu.id, orbit.id, "trigger")


def build_terminal_dense_extras(p: Project, style: dict, width: int, height: int) -> None:
    """Terminal: top processes table + core strip, monospace feel."""
    font = style.get("font", "Monospace")
    accent = style.get("accent", "#4caf7d")
    if _has("visual.top_table"):
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.top_table", z=p.next_z(),
            x=40, y=height - 180,
            props={
                "x": 40, "y": height - 170, "rows": 6,
                "font_family": font, "font_size": 11,
                "color": accent, "header_color": accent,
                "show_alt_rows": False,
            },
        ))
    if _has("visual.core_strip"):
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.core_strip", z=p.next_z(),
            x=width - 220, y=height - 100,
            props={
                "x": width - 200, "y": height - 90, "core_count": 8,
                "bar_width": 10, "bar_height": 48, "gap": 2,
                "color": accent, "heat_map": False, "show_labels": True,
                "font_size": 8,
            },
        ))
