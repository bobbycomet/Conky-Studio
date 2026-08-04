"""
Extra visual nodes: process table, multi-core strip, decorative orbit field.

Import from nodes/__init__.py. Generators in codegen/visual_generators_extra.py.
"""
from __future__ import annotations

from conkystudio.nodes.registry import (
    NodeSpec, PropertySpec, register,
    FLOAT, INT, COLOR, BOOL, ENUM, STRING, FONT,
    KIND_PERCENT, KIND_NUMBER, NUMERIC_KINDS,
)

VISUAL_COLOR = "#8a5fd6"

_GRADIENT_FILL = [
    PropertySpec(
        key="fill_mode", label="Fill mode", kind=ENUM, default="solid",
        choices=["solid", "linear", "radial"],
        choice_labels=["Solid", "Linear gradient", "Radial gradient"],
        group="Style",
    ),
    PropertySpec(key="color_end", label="End colour", kind=COLOR, default="#1a3a4a", group="Style"),
    PropertySpec(key="gradient_angle", label="Gradient angle", kind=FLOAT, default=0.0,
                 minimum=-360, maximum=360, step=1, group="Style"),
    PropertySpec(key="gradient_spread", label="Radial spread", kind=FLOAT, default=1.0,
                 minimum=0.1, maximum=3.0, step=0.05, group="Style"),
]


register(NodeSpec(
    type="visual.top_table", category="visual", label="Top Processes Table",
    color=VISUAL_COLOR, icon="list", subcategory="Graphs", simple_mode=True,
    description="Classic Conky-style table of the busiest processes: rank, name, CPU%, MEM%. "
                "Reads Conky ${top …} natively (no script). Set Rows to how many lines to show.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="rows", label="Rows", kind=INT, default=5, minimum=1, maximum=15, group="Table"),
        PropertySpec(key="row_height", label="Row height", kind=INT, default=18, minimum=10, maximum=40, group="Table"),
        PropertySpec(key="col_rank_w", label="Rank column width", kind=INT, default=28, minimum=16, maximum=80, group="Table"),
        PropertySpec(key="col_name_w", label="Name column width", kind=INT, default=140, minimum=40, maximum=600, group="Table"),
        PropertySpec(key="col_cpu_w", label="CPU column width", kind=INT, default=48, minimum=30, maximum=120, group="Table"),
        PropertySpec(key="col_mem_w", label="MEM column width", kind=INT, default=48, minimum=30, maximum=120, group="Table"),
        PropertySpec(key="show_header", label="Show header", kind=BOOL, default=True, group="Table"),
        PropertySpec(key="font_family", label="Font", kind=FONT, default="Sans", group="Style"),
        PropertySpec(key="font_size", label="Size", kind=INT, default=11, minimum=6, maximum=32, group="Style"),
        PropertySpec(key="color", label="Text colour", kind=COLOR, default="#e8eaed", group="Style"),
        PropertySpec(key="header_color", label="Header colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="alt_row_color", label="Alt row tint", kind=COLOR, default="#1a222c", group="Style"),
        PropertySpec(key="show_alt_rows", label="Tint alternating rows", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
    ],
))

register(NodeSpec(
    type="visual.core_strip", category="visual", label="CPU Core Strip",
    color=VISUAL_COLOR, icon="bar", subcategory="Gauges & Bars", simple_mode=True,
    description="Horizontal strip of per-core CPU usage bars. Polls ${cpu cpu1}…${cpu cpuN} "
                "inside the draw function (no extra source nodes required).",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="core_count", label="Cores", kind=INT, default=8, minimum=1, maximum=64, group="Shape",
                     help="Number of vertical bars. Core i uses ${cpu cpu i}."),
        PropertySpec(key="bar_width", label="Bar width", kind=INT, default=10, minimum=2, maximum=80, group="Shape"),
        PropertySpec(key="bar_height", label="Bar height", kind=INT, default=48, minimum=8, maximum=400, group="Shape"),
        PropertySpec(key="gap", label="Gap between bars", kind=INT, default=3, minimum=0, maximum=40, group="Shape"),
        PropertySpec(key="color", label="Fill colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="track_color", label="Track colour", kind=COLOR, default="#33313a", group="Style"),
        PropertySpec(key="heat_map", label="Heat-map colours", kind=BOOL, default=False, group="Style",
                     help="If on, bar colour shifts cool→hot by usage (ignores Fill colour)."),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
        PropertySpec(key="show_labels", label="Show core numbers", kind=BOOL, default=False, group="Style"),
        PropertySpec(key="font_size", label="Label size", kind=INT, default=8, minimum=6, maximum=16, group="Style"),
        *_GRADIENT_FILL,
    ],
))

register(NodeSpec(
    type="visual.orbit_field", category="visual", label="Orbit Field",
    color=VISUAL_COLOR, icon="spiral", subcategory="Effects", simple_mode=False,
    description="Decorative dots orbiting a centre. Speed and radius respond to an optional "
                "bound Trigger (e.g. CPU%). Showcase / Sci-Fi chrome without Custom Lua.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Orbit radius", kind=INT, default=70, minimum=8, maximum=2000, group="Shape"),
        PropertySpec(key="dot_count", label="Dots", kind=INT, default=12, minimum=3, maximum=48, group="Shape"),
        PropertySpec(key="dot_radius", label="Dot size", kind=FLOAT, default=2.5, minimum=0.5, maximum=20, step=0.5, group="Shape"),
        PropertySpec(key="rings", label="Ring count", kind=INT, default=1, minimum=1, maximum=4, group="Shape"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=0.85, minimum=0, maximum=1, step=0.05, group="Style"),
        PropertySpec(key="speed_dps", label="Base speed (deg/sec)", kind=FLOAT, default=25.0,
                     minimum=-720, maximum=720, group="Animation"),
        PropertySpec(key="trigger", label="Trigger", kind=FLOAT, default=0.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=0, maximum=10000, group="Drive",
                     help="Optional. Scales orbit speed (and slightly radius) with this value."),
        PropertySpec(key="trigger_scale", label="Trigger speed scale", kind=FLOAT, default=0.5,
                     minimum=0, maximum=5, step=0.05, group="Drive",
                     help="Extra speed factor = 1 + (trigger/100) × scale."),
        *_GRADIENT_FILL,
    ],
))
