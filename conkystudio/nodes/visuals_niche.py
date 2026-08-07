"""
More visual nodes -- picked to fill gaps the existing set doesn't cover
rather than reskin what's already there (checked against visuals.py,
visuals_extra.py, visuals_more.py, and the visual.plugin.* entries in
plugins.json before writing any of this):

  visual.spinning_fan    -- rotating blades, speed driven by a bound
                            value. Ties in directly with Fan Sensors
                            (script_family "fan_sensors") -- nothing
                            currently visualizes fan RPM/percent as
                            anything other than a number/bar/gauge.
  visual.radial_spectrum -- Equalizer Bars bent into a ring. Different
                            geometry from every other bar/gauge node.
  visual.vinyl_spinner   -- decorative spinning record for Now Playing
                            layouts; Album Art shows the art itself,
                            this is chrome around it.
  visual.matrix_rain     -- falling-character digital rain, fully
                            procedural (time + index derived, no
                            per-frame random state).
  visual.flip_digit      -- split-flap/departure-board style card with
                            a real fold animation on value change.
  visual.radar_chart     -- polar/spider chart. The only node here that
                            plots more than one bound value on one shape.
  visual.loading_dots    -- tiny bouncing-ellipsis "still working"
                            indicator.

Import from nodes/__init__.py. Generators in
codegen/visual_generators_niche.py -- wire it up the same way
visual_generators_extra.py / visual_generators_more.py are wired (a
register(visual_generator) call from register_extensions.py, or from
the tail of lua_gen.py after the decorator exists).
"""
from __future__ import annotations

from conkystudio.nodes.registry import (
    NodeSpec, PropertySpec, register,
    FLOAT, INT, COLOR, BOOL, ENUM, STRING, FONT,
    NUMERIC_KINDS, ALL_KINDS,
)

VISUAL_COLOR = "#8a5fd6"

_RADAR_MAX_AXES = 6
_RADAR_DEFAULT_LABELS = ["CPU", "RAM", "GPU", "Disk", "Net", "Temp"]


# ---------------------------------------------------------------------
# Spinning Fan
# ---------------------------------------------------------------------
register(NodeSpec(
    type="visual.spinning_fan", category="visual", label="Spinning Fan",
    color=VISUAL_COLOR, icon="spiral", subcategory="Effects", simple_mode=True,
    description="A drawn fan -- hub plus 2-9 curved blades -- that actually spins, speed driven "
                "by a bound value (pairs naturally with a Fan RPM/Fan % source from Fan Sensors). "
                "Unbound, it idles at Idle rev/sec. Direction and blade count are yours; there's "
                "no photo behind it, so it always matches your theme's palette.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="blade_count", label="Blades", kind=INT, default=5, minimum=2, maximum=9, group="Shape"),
        PropertySpec(key="blade_length", label="Blade length", kind=FLOAT, default=60.0, minimum=6, maximum=1000, group="Shape"),
        PropertySpec(key="blade_width", label="Blade width", kind=FLOAT, default=22.0, minimum=2, maximum=400, group="Shape"),
        PropertySpec(key="hub_radius", label="Hub radius", kind=FLOAT, default=10.0, minimum=1, maximum=200, group="Shape"),
        PropertySpec(key="speed_pct", label="Speed %", kind=FLOAT, default=50.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=0, maximum=100, group="Drive",
                     help="0-100-ish. Scales rotation between Idle rev/sec and Max rev/sec. Bind a Fan % source here."),
        PropertySpec(key="base_rps", label="Idle rev/sec (at 0%)", kind=FLOAT, default=0.3, minimum=0, maximum=20, step=0.05, group="Drive"),
        PropertySpec(key="max_rps", label="Rev/sec at 100%", kind=FLOAT, default=6.0, minimum=0, maximum=40, step=0.1, group="Drive"),
        PropertySpec(key="clockwise", label="Clockwise", kind=BOOL, default=True, group="Drive"),
        PropertySpec(key="blade_color", label="Blade colour", kind=COLOR, default="#9aa2ad", group="Style"),
        PropertySpec(key="hub_color", label="Hub colour", kind=COLOR, default="#1a222c", group="Style"),
        PropertySpec(key="heat_map", label="Heat-map blade colour by speed", kind=BOOL, default=False, group="Style"),
        PropertySpec(key="motion_blur", label="Motion-blur ghost blades", kind=BOOL, default=True, group="Style",
                     help="Faint trailing blades behind the real ones -- reads as spinning even at "
                          "a slow Conky refresh interval, instead of stepping frame to frame."),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
    ],
))

# ---------------------------------------------------------------------
# Radial Spectrum
# ---------------------------------------------------------------------
register(NodeSpec(
    type="visual.radial_spectrum", category="visual", label="Radial Spectrum",
    color=VISUAL_COLOR, icon="spiral", subcategory="Effects", simple_mode=False,
    description="Equalizer Bars bent into a ring -- spokes radiate out from a center circle, each "
                "on its own phase. Same honest trade-off as Equalizer Bars/Orbit Field: no real "
                "audio FFT, just chrome that looks alive and optionally answers to a bound Trigger "
                "(Now Playing progress %, CPU %, whatever fits).",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="inner_radius", label="Inner radius", kind=FLOAT, default=30.0, minimum=2, maximum=2000, group="Shape"),
        PropertySpec(key="bar_count", label="Spokes", kind=INT, default=24, minimum=4, maximum=96, group="Shape"),
        PropertySpec(key="bar_width_deg", label="Spoke width (deg)", kind=FLOAT, default=6.0, minimum=1, maximum=40, group="Shape"),
        PropertySpec(key="min_length", label="Min length", kind=FLOAT, default=4.0, minimum=0, maximum=500, group="Shape"),
        PropertySpec(key="max_length", label="Max length", kind=FLOAT, default=45.0, minimum=2, maximum=2000, group="Shape"),
        PropertySpec(key="rounded_caps", label="Rounded tips", kind=BOOL, default=True, group="Shape"),
        PropertySpec(key="speed", label="Animation speed", kind=FLOAT, default=1.0, minimum=0.05, maximum=8.0, step=0.05, group="Animation"),
        PropertySpec(key="trigger", label="Trigger", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=0, maximum=10000, group="Drive",
                     help="Optional. Higher = spokes reach further out. Unbound = calm idle."),
        PropertySpec(key="idle_energy", label="Idle energy (no trigger bound)", kind=FLOAT, default=25.0, minimum=0, maximum=100, group="Drive"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="heat_map", label="Heat-map colours by length", kind=BOOL, default=False, group="Style"),
        PropertySpec(key="draw_center", label="Draw center disc", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="center_color", label="Center disc colour", kind=COLOR, default="#1a222c", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=0.9, minimum=0, maximum=1, step=0.05, group="Style"),
    ],
))

# ---------------------------------------------------------------------
# Vinyl Spinner
# ---------------------------------------------------------------------
register(NodeSpec(
    type="visual.vinyl_spinner", category="visual", label="Vinyl Spinner",
    color=VISUAL_COLOR, icon="circle", subcategory="Media", simple_mode=True,
    description="A spinning record -- grooves, label, spindle hole, optional tonearm and specular "
                "sheen. Bind Spin gate to a playback-state source (< 0.5 = paused) and it freezes "
                "in place instead of jumping to a new angle next refresh; unbound, it just spins "
                "forever. The label center is left empty on purpose -- lay an Image/Icon node with "
                "your album art on top if you want one, it won't fight with Album Art's own node.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=FLOAT, default=90.0, minimum=8, maximum=2000, group="Shape"),
        PropertySpec(key="label_radius", label="Label radius", kind=FLOAT, default=32.0, minimum=2, maximum=1000, group="Shape"),
        PropertySpec(key="spindle_radius", label="Spindle hole radius", kind=FLOAT, default=3.0, minimum=0, maximum=100, group="Shape"),
        PropertySpec(key="groove_count", label="Groove rings", kind=INT, default=14, minimum=0, maximum=60, group="Shape"),
        PropertySpec(key="rpm", label="RPM", kind=FLOAT, default=33.3, minimum=0, maximum=200, step=0.1, group="Drive"),
        PropertySpec(key="spin_gate", label="Spin gate", kind=FLOAT, default=1.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=0, maximum=1, group="Drive",
                     help="≥0.5 spins, <0.5 holds still at its current angle. Leave unbound to always spin."),
        PropertySpec(key="disc_color", label="Disc colour", kind=COLOR, default="#15161a", group="Style"),
        PropertySpec(key="groove_color", label="Groove colour", kind=COLOR, default="#2c2e35", group="Style"),
        PropertySpec(key="label_color", label="Label colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="show_tonearm", label="Show tonearm", kind=BOOL, default=False, group="Style"),
        PropertySpec(key="tonearm_color", label="Tonearm colour", kind=COLOR, default="#9aa2ad", group="Style"),
        PropertySpec(key="specular", label="Specular sheen", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
    ],
))

# ---------------------------------------------------------------------
# Matrix Rain
# ---------------------------------------------------------------------
register(NodeSpec(
    type="visual.matrix_rain", category="visual", label="Matrix Rain",
    color=VISUAL_COLOR, icon="text", subcategory="Effects", simple_mode=False,
    description="Falling-character digital rain, Matrix-style, clipped to a W x H box. Fully "
                "procedural -- column speed and glyph choice are derived from time and column "
                "index, so it never needs seeded random state and animates smoothly regardless of "
                "Conky's update interval. Pure decoration, no data behind it.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="width", label="Width", kind=INT, default=160, minimum=8, maximum=4000, group="Shape"),
        PropertySpec(key="height", label="Height", kind=INT, default=200, minimum=8, maximum=4000, group="Shape"),
        PropertySpec(key="font_size", label="Glyph size", kind=INT, default=14, minimum=6, maximum=48, group="Shape"),
        PropertySpec(key="column_gap", label="Column spacing", kind=INT, default=2, minimum=0, maximum=40, group="Shape"),
        PropertySpec(key="trail_length", label="Trail length (glyphs)", kind=INT, default=10, minimum=2, maximum=40, group="Animation"),
        PropertySpec(key="speed", label="Fall speed", kind=FLOAT, default=1.0, minimum=0.05, maximum=8.0, step=0.05, group="Animation"),
        PropertySpec(key="flicker_hz", label="Glyph flicker rate", kind=FLOAT, default=6.0, minimum=0.5, maximum=30.0, group="Animation",
                     help="How often the glyph at a given cell re-rolls, independent of fall speed."),
        PropertySpec(key="charset", label="Character set", kind=STRING, default="01$%#@&*+=-:.", group="Style",
                     help="Any characters your theme font can render -- keep it short and glyph-y."),
        PropertySpec(key="color", label="Head colour", kind=COLOR, default="#39ff14", group="Style"),
        PropertySpec(key="tail_color", label="Trail colour", kind=COLOR, default="#0b6b12", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=0.9, minimum=0, maximum=1, step=0.05, group="Style"),
    ],
))

# ---------------------------------------------------------------------
# Flip Card
# ---------------------------------------------------------------------
register(NodeSpec(
    type="visual.flip_digit", category="visual", label="Flip Card",
    color=VISUAL_COLOR, icon="text", subcategory="Text", simple_mode=True,
    description="Split-flap (departure-board) style card. Bind any text or number source; when its "
                "value changes, the old card's top half folds down and shrinks away to reveal the "
                "new value underneath. Great for a clock's seconds digit or anything that changes "
                "in discrete steps -- a constantly-drifting value (raw CPU%) will just look like "
                "it's always mid-flip, so pair it with something that ticks.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="width", label="Width", kind=INT, default=56, minimum=10, maximum=1000, group="Shape"),
        PropertySpec(key="height", label="Height", kind=INT, default=72, minimum=10, maximum=1000, group="Shape"),
        PropertySpec(key="corner_radius", label="Corner radius", kind=FLOAT, default=6.0, minimum=0, maximum=200, group="Shape"),
        PropertySpec(key="value", label="Value", kind=STRING, default="0", bindable=True, accepts=ALL_KINDS, group="Data"),
        PropertySpec(key="flip_duration", label="Flip duration (sec)", kind=FLOAT, default=0.35, minimum=0.05, maximum=3.0, step=0.05, group="Animation"),
        PropertySpec(key="font_family", label="Font", kind=FONT, default="Sans", group="Style"),
        PropertySpec(key="font_size", label="Font size", kind=INT, default=36, minimum=6, maximum=200, group="Style"),
        PropertySpec(key="card_color", label="Card colour", kind=COLOR, default="#1a222c", group="Style"),
        PropertySpec(key="text_color", label="Text colour", kind=COLOR, default="#e8eaed", group="Style"),
        PropertySpec(key="divider_color", label="Divider colour", kind=COLOR, default="#0c0f14", group="Style"),
        PropertySpec(key="flap_color", label="Flap colour", kind=COLOR, default="#262c38", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
    ],
))

# ---------------------------------------------------------------------
# Radar Chart
# ---------------------------------------------------------------------
def _radar_axis_props() -> list:
    props = []
    for i in range(1, _RADAR_MAX_AXES + 1):
        props.append(PropertySpec(
            key=f"value_{i}", label=f"Value {i}", kind=FLOAT, default=50.0,
            bindable=True, accepts=NUMERIC_KINDS, minimum=-1e9, maximum=1e9, group="Axes",
        ))
        props.append(PropertySpec(
            key=f"label_{i}", label=f"Label {i}", kind=STRING,
            default=_RADAR_DEFAULT_LABELS[i - 1], group="Axes",
        ))
    return props


register(NodeSpec(
    type="visual.radar_chart", category="visual", label="Radar Chart",
    color=VISUAL_COLOR, icon="spiral", subcategory="Graphs", simple_mode=True,
    description="Polar/spider chart comparing up to 6 bound values on one shape -- the only node "
                "here that plots more than one series at once. Set Axis count to how many of the "
                "Value slots are actually wired; the rest are ignored, not drawn.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=FLOAT, default=80.0, minimum=8, maximum=2000, group="Shape"),
        PropertySpec(key="axis_count", label="Axis count", kind=INT, default=5, minimum=3, maximum=_RADAR_MAX_AXES, group="Shape"),
        PropertySpec(key="min_value", label="Min value", kind=FLOAT, default=0.0, group="Scale"),
        PropertySpec(key="max_value", label="Max value", kind=FLOAT, default=100.0, group="Scale"),
        PropertySpec(key="grid_rings", label="Grid rings", kind=INT, default=4, minimum=0, maximum=10, group="Grid"),
        PropertySpec(key="grid_color", label="Grid colour", kind=COLOR, default="#33313a", group="Grid"),
        PropertySpec(key="fill_color", label="Fill colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="fill_opacity", label="Fill opacity", kind=FLOAT, default=0.35, minimum=0, maximum=1, step=0.05, group="Style"),
        PropertySpec(key="line_width", label="Line width", kind=FLOAT, default=2.0, minimum=0.5, maximum=20, step=0.5, group="Style"),
        PropertySpec(key="show_dots", label="Show vertex dots", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="show_labels", label="Show axis labels", kind=BOOL, default=True, group="Label"),
        PropertySpec(key="font_family", label="Font", kind=FONT, default="Sans", group="Label"),
        PropertySpec(key="font_size", label="Label size", kind=INT, default=11, minimum=6, maximum=32, group="Label"),
        PropertySpec(key="label_color", label="Label colour", kind=COLOR, default="#9aa2ad", group="Label"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
        *_radar_axis_props(),
    ],
))

# ---------------------------------------------------------------------
# Loading Dots
# ---------------------------------------------------------------------
register(NodeSpec(
    type="visual.loading_dots", category="visual", label="Loading Dots",
    color=VISUAL_COLOR, icon="circle", subcategory="Effects", simple_mode=True,
    description="Three bouncing dots, classic 'still working' ellipsis. Tiny and cheap, and honest "
                "about not representing any real data -- use it next to a source that can stall "
                "(weather fetch, now-playing lookup) rather than as permanent chrome.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y (baseline)", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="dot_radius", label="Dot radius", kind=FLOAT, default=4.0, minimum=1, maximum=60, group="Shape"),
        PropertySpec(key="gap", label="Gap", kind=FLOAT, default=14.0, minimum=2, maximum=200, group="Shape"),
        PropertySpec(key="bounce_height", label="Bounce height", kind=FLOAT, default=8.0, minimum=0, maximum=200, group="Animation"),
        PropertySpec(key="speed", label="Speed", kind=FLOAT, default=2.0, minimum=0.1, maximum=10, step=0.1, group="Animation"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#e8eaed", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
    ],
))
