"""
Three more Cairo-drawn visual nodes, in the same shape as visuals_extra.py:

  visual.needle_gauge   -- classic analog dial (speedometer style), with
                           colored warning zones and tick marks.
  visual.segmented_ring -- discrete dashed-ring gauge (sci-fi HUD look),
                           distinct from arc_gauge's continuous fill.
  visual.equalizer_bars -- decorative animated EQ/spectrum bars, each bar
                           on its own phase so it doesn't look like one
                           bar copy-pasted sideways; optionally driven by
                           a bound Trigger the same way orbit_field is.

Generators are in codegen/visual_generators_more.py. Import this module
from nodes/__init__.py (or via register_extensions.py) so register()
runs at startup.
"""
from __future__ import annotations

from conkystudio.nodes.registry import (
    NodeSpec, PropertySpec, register,
    FLOAT, INT, COLOR, BOOL, ENUM, FONT, STRING,
    NUMERIC_KINDS,
)
from conkystudio.codegen.gradient_integration import (
    gradient_property_specs,
    blend_property_spec,
    scale_property_spec,
)

VISUAL_COLOR = "#8a5fd6"
_SCALE = [scale_property_spec()]

register(NodeSpec(
    type="visual.needle_gauge", category="visual", label="Needle Gauge",
    color=VISUAL_COLOR, icon="gauge", subcategory="Gauges & Bars", simple_mode=True,
    description="Analog speedometer-style dial: sweep arc, tick marks, three colour zones, "
                "and a rotating needle. A more literal 'dashboard gauge' look than Arc Gauge's "
                "clean progress-ring style -- pick whichever matches your theme.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=INT, default=80, minimum=16, maximum=2000, group="Shape"),
        PropertySpec(key="start_angle", label="Start angle", kind=FLOAT, default=135.0,
                     minimum=-360, maximum=360, group="Shape",
                     help="Degrees, clockwise from 3 o'clock. Default 135/45 gives the classic "
                          "270°-sweep speedometer opening at the bottom."),
        PropertySpec(key="end_angle", label="End angle", kind=FLOAT, default=45.0,
                     minimum=-360, maximum=360, group="Shape"),
        PropertySpec(key="value", label="Value", kind=FLOAT, default=50.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=-1e9, maximum=1e9, group="Data"),
        PropertySpec(key="min_value", label="Min value", kind=FLOAT, default=0.0, group="Data"),
        PropertySpec(key="max_value", label="Max value", kind=FLOAT, default=100.0, group="Data"),
        PropertySpec(key="track_width", label="Track width", kind=FLOAT, default=10.0, minimum=1, maximum=200, group="Shape"),
        PropertySpec(key="tick_count", label="Major ticks", kind=INT, default=8, minimum=2, maximum=40, group="Ticks"),
        PropertySpec(key="show_minor_ticks", label="Minor ticks", kind=BOOL, default=True, group="Ticks"),
        PropertySpec(key="use_zones", label="Colour warning zones", kind=BOOL, default=True, group="Zones",
                     help="Splits the track into green / amber / red bands by percent-of-range."),
        PropertySpec(key="zone_warn_pct", label="Amber starts at %", kind=FLOAT, default=60.0,
                     minimum=0, maximum=100, group="Zones"),
        PropertySpec(key="zone_danger_pct", label="Red starts at %", kind=FLOAT, default=85.0,
                     minimum=0, maximum=100, group="Zones"),
        PropertySpec(key="track_color", label="Track colour", kind=COLOR, default="#33313a", group="Style"),
        PropertySpec(key="zone_ok_color", label="Zone: OK", kind=COLOR, default="#4fd1c5", group="Zones"),
        PropertySpec(key="zone_warn_color", label="Zone: Warning", kind=COLOR, default="#e8b84f", group="Zones"),
        PropertySpec(key="zone_danger_color", label="Zone: Danger", kind=COLOR, default="#ff6b6b", group="Zones"),
        PropertySpec(key="needle_color", label="Needle colour", kind=COLOR, default="#e8eaed", group="Style"),
        PropertySpec(key="hub_color", label="Hub colour", kind=COLOR, default="#1a222c", group="Style"),
        PropertySpec(key="tick_color", label="Tick colour", kind=COLOR, default="#9aa2ad", group="Style"),
        PropertySpec(key="show_value_text", label="Show value text", kind=BOOL, default=True, group="Label"),
        PropertySpec(key="font_family", label="Font", kind=FONT, default="Sans", group="Label"),
        PropertySpec(key="font_size", label="Text size", kind=INT, default=14, minimum=6, maximum=48, group="Label"),
        PropertySpec(key="value_suffix", label="Suffix", kind=STRING, default="", group="Label"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
        *_SCALE,
    ],
))

register(NodeSpec(
    type="visual.equalizer_bars", category="visual", label="Equalizer Bars",
    color=VISUAL_COLOR, icon="bar", subcategory="Effects", simple_mode=False,
    description="Decorative animated EQ/spectrum bars -- each bar runs its own sine phase so it "
                "doesn't read as one shape tiled sideways. Optionally bind Trigger (e.g. Playback "
                "Progress %, CPU %) to scale how energetic the motion looks; with nothing bound it "
                "idles at a gentle ambient level. There's no real audio FFT here (Conky has no "
                "spectrum source) -- this is chrome, the same honest trade-off as Orbit Field.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y (baseline)", kind=INT, default=140, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="bar_count", label="Bars", kind=INT, default=16, minimum=2, maximum=64, group="Shape"),
        PropertySpec(key="bar_width", label="Bar width", kind=INT, default=6, minimum=1, maximum=80, group="Shape"),
        PropertySpec(key="gap", label="Gap between bars", kind=INT, default=3, minimum=0, maximum=40, group="Shape"),
        PropertySpec(key="max_height", label="Max height", kind=INT, default=60, minimum=4, maximum=1000, group="Shape"),
        PropertySpec(key="min_height", label="Idle height", kind=INT, default=4, minimum=0, maximum=500, group="Shape"),
        PropertySpec(key="rounded_caps", label="Rounded bar caps", kind=BOOL, default=True, group="Shape"),
        PropertySpec(key="mirror", label="Mirror above/below baseline", kind=BOOL, default=False, group="Shape",
                     help="On: draws up AND down from Y, classic waveform look. Off: bars grow up only."),
        PropertySpec(key="speed", label="Animation speed", kind=FLOAT, default=1.0, minimum=0.05, maximum=8.0,
                     step=0.05, group="Animation"),
        PropertySpec(key="trigger", label="Trigger", kind=FLOAT, default=0.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=0, maximum=10000, group="Drive",
                     help="Optional 0-100-ish value. Higher = taller, more energetic motion. "
                          "Leave unbound for a calm ambient idle animation."),
        PropertySpec(key="idle_energy", label="Idle energy (no trigger bound)", kind=FLOAT, default=25.0,
                     minimum=0, maximum=100, group="Drive"),
        PropertySpec(key="color", label="Bar colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="heat_map", label="Heat-map colours by height", kind=BOOL, default=False, group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=0.9, minimum=0, maximum=1, step=0.05, group="Style"),
        *gradient_property_specs(),
        blend_property_spec(),
        *_SCALE,
    ],
))



