"""
Visual node specs. Each one has a matching Lua-emitting function in
codegen/lua_gen.py named draw_<type-with-dots-as-underscores> -- e.g.
"visual.arc_gauge" is emitted by lua_gen.draw_visual_arc_gauge(). The
codegen module asserts at import time that every registered visual type
has a generator, so a node you can drag onto the canvas can never be one
that silently produces nothing.

Colours are stored as "#RRGGBB" hex strings (what QColorDialog hands
back), converted to Cairo's 0..1 float triples only at codegen time --
see codegen/color.py.

Any property with bindable=True can be left as a plain constant OR wired
to a data-source node's output; codegen emits either the literal value or
a cache-read/conky_parse expression depending on whether an edge exists
for that (node, prop) pair (see Project.edge_for_prop).
"""
from __future__ import annotations

from conkystudio.nodes.registry import (
    NodeSpec, PropertySpec, register,
    FLOAT, INT, COLOR, BOOL, ENUM, STRING, PATH, FONT, CODE,
    KIND_PERCENT, KIND_CELSIUS, KIND_NUMBER, KIND_TEXT, KIND_CATEGORY, NUMERIC_KINDS, ALL_KINDS,
)

VISUAL_COLOR = "#8a5fd6"  # violet -- distinguishes visual/drawing nodes from sources at a glance

# Optional 2-stop gradient fill (solid | linear | radial). Appended to
# fill-capable shapes/gauges. Generators read fill_mode / color_end /
# gradient_angle / gradient_spread via codegen.color.lua_set_source.
_GRADIENT_FILL = [
    PropertySpec(
        key="fill_mode", label="Fill mode", kind=ENUM, default="solid",
        choices=["solid", "linear", "radial"],
        choice_labels=["Solid", "Linear gradient", "Radial gradient"],
        group="Style",
        help="Solid uses Fill colour only. Linear/Radial blend Fill colour → End colour.",
    ),
    PropertySpec(
        key="color_end", label="End colour", kind=COLOR, default="#1a3a4a",
        group="Style",
        help="Second gradient stop. Ignored when Fill mode is Solid.",
    ),
    PropertySpec(
        key="gradient_angle", label="Gradient angle", kind=FLOAT, default=0.0,
        minimum=-360, maximum=360, step=1, group="Style",
        help="Linear direction in degrees (0 = left→right, 90 = top→bottom).",
    ),
    PropertySpec(
        key="gradient_spread", label="Radial spread", kind=FLOAT, default=1.0,
        minimum=0.1, maximum=3.0, step=0.05, group="Style",
        help="Radial only: outer stop distance as a multiple of the shape radius.",
    ),
]



# --------------------------------------------------------------- Text Label
register(NodeSpec(
    type="visual.text", category="visual", label="Text Label", color=VISUAL_COLOR, icon="type", subcategory="Text",
    description="Draws a string, optionally bound to a data source (numbers are auto-formatted).",
    properties=[
        PropertySpec(key="value", label="Value", kind=STRING, default="Label", bindable=True,
                     accepts=ALL_KINDS,
                     help="Plain text if left unwired, or wire any source/logic output (numbers auto-format)."),
        PropertySpec(key="prefix", label="Prefix", kind=STRING, default="", group="Format"),
        PropertySpec(key="suffix", label="Suffix", kind=STRING, default="", group="Format"),
        PropertySpec(key="decimals", label="Decimal places", kind=INT, default=0, minimum=0, maximum=4, group="Format",
                     help="Only applies when Value is bound to a numeric source."),
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="align", label="Align", kind=ENUM, default="left", choices=["left", "center", "right"], group="Position"),
        PropertySpec(key="font_family", label="Font", kind=FONT, default="Sans", group="Style"),
        PropertySpec(key="font_size", label="Size", kind=INT, default=16, minimum=6, maximum=200, group="Style"),
        PropertySpec(key="bold", label="Bold", kind=BOOL, default=False, group="Style"),
        PropertySpec(key="italic", label="Italic", kind=BOOL, default=False, group="Style"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#FFFFFF", group="Style"),
        PropertySpec(key="halo", label="Readability halo", kind=BOOL, default=False, group="Style",
                     help="Soft light outline behind the text, for busy/light backgrounds (see the parchment theme)."),
    ],
))

# --------------------------------------------------------------- Arc / Ring Gauge
register(NodeSpec(
    type="visual.arc_gauge", category="visual", label="Arc / Ring Gauge", color=VISUAL_COLOR, icon="ring", subcategory="Gauges & Bars",
    description="A radial gauge: full ring, partial arc, or classic gauge sweep.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=50.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=0, maximum=10000),
        PropertySpec(key="min_value", label="Min", kind=FLOAT, default=0.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="max_value", label="Max", kind=FLOAT, default=100.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="cx", label="Center X", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=INT, default=70, minimum=4, maximum=2000, group="Shape"),
        PropertySpec(key="thickness", label="Thickness", kind=INT, default=10, minimum=1, maximum=200, group="Shape"),
        PropertySpec(key="start_angle_deg", label="Start angle", kind=INT, default=-90, minimum=-360, maximum=360, group="Shape"),
        PropertySpec(key="sweep_deg", label="Sweep angle", kind=INT, default=360, minimum=1, maximum=360, group="Shape",
                     help="360 = full ring. 270 = classic gauge with a gap at the bottom."),
        PropertySpec(key="cap_style", label="End caps", kind=ENUM, default="round", choices=["butt", "round"], group="Shape"),
        PropertySpec(key="color", label="Fill colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="track_color", label="Track colour", kind=COLOR, default="#33313a", group="Style"),
        PropertySpec(key="track_alpha", label="Track opacity", kind=FLOAT, default=0.6, minimum=0, maximum=1, step=0.05, group="Style"),
        PropertySpec(key="show_value_text", label="Show value as text", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="value_font_size", label="Value text size", kind=INT, default=20, minimum=6, maximum=200, group="Style"),
        PropertySpec(key="value_suffix", label="Value text suffix", kind=STRING, default="%", group="Style"),
    
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Bar
register(NodeSpec(
    type="visual.bar", category="visual", label="Bar", color=VISUAL_COLOR, icon="bar", subcategory="Gauges & Bars",
    description="A linear meter: solid, segmented (LED-style), or the slanted trapezoid skin "
                "measured from the Skyrim theme's Tiny_Bar_2.png.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=50.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=0, maximum=10000),
        PropertySpec(key="min_value", label="Min", kind=FLOAT, default=0.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="max_value", label="Max", kind=FLOAT, default=100.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="width", label="Width", kind=INT, default=220, minimum=4, maximum=5000, group="Shape"),
        PropertySpec(key="height", label="Height", kind=INT, default=18, minimum=2, maximum=4000, group="Shape"),
        PropertySpec(key="orientation", label="Orientation", kind=ENUM, default="horizontal",
                     choices=["horizontal", "vertical"], group="Shape"),
        PropertySpec(key="style", label="Style", kind=ENUM, default="solid",
                     choices=["solid", "segmented", "trapezoid"], group="Shape"),
        PropertySpec(key="segment_count", label="Segments", kind=INT, default=22, minimum=2, maximum=2500, group="Shape",
                     help="Only used when Style = segmented."),
        PropertySpec(key="corner_radius", label="Corner radius", kind=INT, default=4, minimum=0, maximum=200, group="Shape",
                     help="Only used when Style = solid."),
        PropertySpec(key="color", label="Fill colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="track_color", label="Track colour", kind=COLOR, default="#33313a", group="Style"),
        PropertySpec(key="pulse_when_critical", label="Pulse when >= threshold", kind=BOOL, default=False, group="Alert",
                     help="Flashes brighter once Value crosses the threshold below -- e.g., a health bar "
                          "in the red, or a temperature bar running hot."),
        PropertySpec(key="critical_threshold", label="Critical threshold", kind=FLOAT, default=85.0, minimum=0, maximum=10000, group="Alert"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Glow / Pulse
register(NodeSpec(
    type="visual.glow_pulse", category="visual", label="Glow / Pulse", color=VISUAL_COLOR, icon="glow",
    subcategory="Effects",
    description="Soft multi-pass halo. Default is a circular ring. Set an Image to glow around that "
                "PNG’s silhouette (works with transparency—extra passes scale the same alpha mask). "
                "Or pick a Shape mode to pulse a star/triangle outline. Optional Trigger gates the glow.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius / size", kind=INT, default=60, minimum=2, maximum=2000, group="Shape",
                     help="Circle radius, or half-size box for image/shape modes."),
        PropertySpec(key="mode", label="Glow shape", kind=ENUM, default="circle",
                     choices=["circle", "image", "star", "triangle"],
                     choice_labels=["Circle", "Image silhouette", "Star", "Triangle"],
                     group="Shape"),
        PropertySpec(key="path", label="Image file", kind=PATH, default="", group="Image",
                     help="Used when Glow shape = Image. PNG with alpha recommended. Copied into images/ at build."),
        PropertySpec(key="star_points", label="Star points", kind=INT, default=5, minimum=3, maximum=12, group="Shape"),
        PropertySpec(key="star_inner_ratio", label="Star inner ratio", kind=FLOAT, default=0.4, minimum=0.1, maximum=0.9, step=0.05, group="Shape"),
        PropertySpec(key="layers", label="Glow layers", kind=INT, default=4, minimum=1, maximum=12, group="Shape"),
        PropertySpec(key="spread", label="Spread", kind=FLOAT, default=0.35, minimum=0.05, maximum=1.5, step=0.05, group="Shape",
                     help="How far the outer layers expand past the base size (fraction of radius)."),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="pulse_hz", label="Pulse speed (Hz)", kind=FLOAT, default=0.5, minimum=0.01, maximum=10, step=0.05, group="Animation"),
        PropertySpec(key="alpha_min", label="Min opacity", kind=FLOAT, default=0.15, minimum=0, maximum=1, step=0.05, group="Animation"),
        PropertySpec(key="alpha_max", label="Max opacity", kind=FLOAT, default=0.55, minimum=0, maximum=1, step=0.05, group="Animation"),
        PropertySpec(key="trigger", label="Trigger", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=0, maximum=10000, group="Alert"),
        PropertySpec(key="trigger_threshold", label="Trigger threshold", kind=FLOAT, default=80.0, minimum=0, maximum=10000, group="Alert"),
        PropertySpec(key="trigger_mode", label="Trigger direction", kind=ENUM, default="above",
                     choices=["above", "below"], group="Alert"),
    
        *_GRADIENT_FILL,
    ],
))
# --------------------------------------------------------------- Spiral
register(NodeSpec(
    type="visual.spiral", category="visual", label="Spiral", color=VISUAL_COLOR, icon="spiral", subcategory="Effects",
    description="A rotating spiral of ticks or a continuous line -- radar sweeps, loading rings, "
                "decorative orbit motifs.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="turns", label="Turns", kind=FLOAT, default=2.5, minimum=0.1, maximum=20, step=0.1, group="Shape"),
        PropertySpec(key="radius_start", label="Inner radius", kind=INT, default=8, minimum=0, maximum=2000, group="Shape"),
        PropertySpec(key="radius_end", label="Outer radius", kind=INT, default=90, minimum=1, maximum=2000, group="Shape"),
        PropertySpec(key="dash_count", label="Dash count", kind=INT, default=0, minimum=0, maximum=200, group="Shape",
                     help="0 draws one continuous stroked spiral. Above 0 draws that many short ticks "
                          "along the spiral path instead, like a radar sweep."),
        PropertySpec(key="line_width", label="Line width", kind=FLOAT, default=2.0, minimum=0.2, maximum=40, step=0.2, group="Shape"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#4fd1c5", group="Style"),
        *_GRADIENT_FILL,
        PropertySpec(key="rotation_speed_dps", label="Rotation speed (deg/sec)", kind=FLOAT, default=30.0,
                     minimum=-720, maximum=720, group="Animation", help="0 = static, negative = reverse direction."),
    ],
))

# --------------------------------------------------------------- Image / Icon
register(NodeSpec(
    type="visual.image_icon", category="visual", label="Image / Icon", color=VISUAL_COLOR, icon="image", subcategory="Icons & Images",
    description="Draws a PNG or SVG (via Conky's RSVG Lua binding), fit to a size box. Optionally "
                "swaps to a different image once a bound value crosses a threshold -- the same "
                "pattern the Skyrim theme uses to swap in Survival_Warm/Cold artwork for Body Temp, "
                "or that a weather category token drives for its hand-drawn weather icons.",
    properties=[
        PropertySpec(key="path", label="Image file", kind=PATH, default="", group="Image",
                     help="PNG or SVG. Copied into the theme's images/ folder at build time."),
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="size", label="Size (box)", kind=INT, default=48, minimum=2, maximum=2000, group="Shape"),
        PropertySpec(key="rotation_deg", label="Rotation", kind=FLOAT, default=0.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=0, maximum=360, group="Shape",
                     help="Wire a source here for a spinning gauge needle or gear; leave as a "
                          "constant for a fixed tilt."),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
        PropertySpec(key="swap_trigger", label="Swap trigger", kind=FLOAT, default=0.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=0, maximum=10000, group="Conditional",
                     help="Wire a numeric source here to drive the threshold swap below -- "
                          "e.g. Body Temp swapping in warm/cold survival artwork. For weather-"
                          "category art with no image files needed, use a Weather Icon node instead."),
        PropertySpec(key="swap_above_path", label="Swap image if >= threshold", kind=PATH, default="", group="Conditional"),
        PropertySpec(key="swap_above_threshold", label="Threshold", kind=FLOAT, default=70.0, minimum=0, maximum=10000, group="Conditional"),
        PropertySpec(key="swap_below_path", label="Swap image if <= threshold", kind=PATH, default="", group="Conditional"),
        PropertySpec(key="swap_below_threshold", label="Threshold", kind=FLOAT, default=35.0, minimum=0, maximum=10000, group="Conditional"),
    ],
))

# --------------------------------------------------------------- Weather Icon
register(NodeSpec(
    type="visual.weather_icon", category="visual", label="Weather Icon", color=VISUAL_COLOR, icon="cloud", subcategory="Icons & Images",
    description="A hand-drawn vector icon (sun/cloud/rain/snow/storm/fog/wind/dust) chosen by "
                "category -- no image files needed. Ported directly from the Skyrim theme's "
                "draw_weather_icon(). Wire a Weather Category source into Category.",
    properties=[
        PropertySpec(key="category", label="Category", kind=ENUM, default="clear", bindable=True,
                     accepts=(KIND_CATEGORY,),
                     choices=["clear", "cloud", "overcast", "fog", "wind", "rain", "storm",
                              "snow", "cold", "hot", "dust", "unknown"],
                     help="Constant value used when nothing is wired in, handy for previewing a "
                          "specific icon while designing."),
        PropertySpec(key="cx", label="Center X", kind=INT, default=30, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=30, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="size", label="Size", kind=INT, default=28, minimum=6, maximum=400, group="Shape"),
        PropertySpec(key="color", label="Ink colour", kind=COLOR, default="#B8A888", group="Style",
                     help="Used for cloud/rain/fog/wind/dust strokes; clear/hot suns and snow/cold "
                          "lines use their own fixed warm/cool tones the same way the original does."),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- History Graph
register(NodeSpec(
    type="visual.history_graph", category="visual", label="History Graph", color=VISUAL_COLOR, icon="graph", subcategory="Graphs",
    description="A scrolling line/area chart of a value over time, e.g. network throughput or "
                "CPU load history -- the sparkline pattern from batcomputer.lua's push_hist().",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=0, maximum=100000),
        PropertySpec(key="title_label", label="Title / caption", kind=STRING, default="", bindable=True,
                     accepts=ALL_KINDS, group="Label",
                     help="Optional caption drawn above the graph. Wire a source or type constant text."),
        PropertySpec(key="title_font_size", label="Title size", kind=INT, default=11, minimum=6, maximum=48, group="Label"),
        PropertySpec(key="title_color", label="Title colour", kind=COLOR, default="#9aa2ad", group="Label"),
        PropertySpec(key="min_value", label="Min", kind=FLOAT, default=0.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="max_value", label="Max", kind=FLOAT, default=100.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="width", label="Width", kind=INT, default=200, minimum=8, maximum=4000, group="Shape"),
        PropertySpec(key="height", label="Height", kind=INT, default=60, minimum=8, maximum=2000, group="Shape"),
        PropertySpec(key="history_length", label="Samples kept", kind=INT, default=48, minimum=4, maximum=600, group="Shape",
                     help="Ring buffer length. Fills at Canvas's Sensor refresh rate, not the draw FPS."),
        PropertySpec(key="fill", label="Fill area under line", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="color", label="Line colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="track_color", label="Frame colour", kind=COLOR, default="#33313a", group="Style"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Album Art
register(NodeSpec(
    type="visual.album_art", category="visual", label="Album Art", color=VISUAL_COLOR, icon="image",
    subcategory="Media",
    description="Now-playing cover art via playerctl + curl, adapted from fetch-art2.sh. Unlike a "
                "regular Image/Icon node (which copies one fixed file at build time), this re-fetches "
                "and re-reads the art at the Canvas's sensor-refresh rate, since the same file path "
                "gets new content every time the track changes.",
    properties=[
        PropertySpec(key="player", label="Player name", kind=STRING, default="spotify", group="Player"),
        PropertySpec(key="poll_interval", label="Check every (sec)", kind=INT, default=2, minimum=1, maximum=60, group="Player"),
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="size", label="Size (box)", kind=INT, default=96, minimum=8, maximum=2000, group="Shape"),
        PropertySpec(key="corner_radius", label="Corner radius", kind=INT, default=0, minimum=0, maximum=400, group="Shape",
                     help="0 = square corners. Clips the art to a rounded rect, e.g. to mimic Spotify's own artwork style."),
        PropertySpec(key="fallback_path", label="Fallback image", kind=PATH, default="", group="Image",
                     help="Shown while nothing is playing, or if art fails to fetch. Optional."),
    ],
))

# --------------------------------------------------------------- Icon Glyph
register(NodeSpec(
    type="visual.icon_glyph", category="visual", label="Icon Glyph", color=VISUAL_COLOR, icon="type",
    subcategory="Icons & Images",
    description="Draws a single character from an installed icon font (Feather, Font Awesome, "
                "Material Icons, ...) -- the same technique weather-text-icon.sh uses to show "
                "weather glyphs instead of raster/vector art. Paste the glyph's literal character "
                "(copy it from the icon font's cheat-sheet page) or its Unicode codepoint.",
    properties=[
        PropertySpec(key="character", label="Character", kind=STRING, default="\u2600", bindable=True,
                     accepts=(KIND_TEXT, KIND_CATEGORY),
                     help="A single glyph character, or a 4-digit hex codepoint like e922. Wire a "
                          "Weather Category source in and use Codepoint mode with a mapping "
                          "convention if your icon font follows one, or just pick a fixed glyph."),
        PropertySpec(key="input_mode", label="Input is", kind=ENUM, default="character",
                     choices=["character", "codepoint"],
                     help="'codepoint' treats the value as hex, e.g. 'e922' -> that Unicode character."),
        PropertySpec(key="font_family", label="Icon font", kind=FONT, default="Sans", group="Style",
                     help="Must be installed (Tools -> Install Font if it isn't yet)."),
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="size", label="Size", kind=INT, default=32, minimum=6, maximum=400, group="Style"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#FFFFFF", group="Style"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Text List
register(NodeSpec(
    type="visual.text_list", category="visual", label="Text List", color=VISUAL_COLOR, icon="list",
    subcategory="Text",
    description="A block of multiple lines, word-wrapped and capped to a max line count -- the "
                "pattern behind the Zotero/calendar/notes panels: bind a Custom Script source whose "
                "output has multiple lines (e.g. zotero.sh's saved list, or calcurse output).",
    properties=[
        PropertySpec(key="value", label="Value", kind=STRING, default="Line one\nLine two", bindable=True,
                     accepts=ALL_KINDS, help="Newline-separated text; numbers stringify. Usually a Custom Script source."),
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="max_lines", label="Max lines shown", kind=INT, default=10, minimum=1, maximum=100, group="Shape"),
        PropertySpec(key="line_height", label="Line height (px)", kind=INT, default=18, minimum=6, maximum=200, group="Shape"),
        PropertySpec(key="font_family", label="Font", kind=FONT, default="Sans", group="Style"),
        PropertySpec(key="font_size", label="Size", kind=INT, default=12, minimum=6, maximum=100, group="Style"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#FFFFFF", group="Style"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Moon Phase
register(NodeSpec(
    type="visual.moon_phase", category="visual", label="Moon Phase", color=VISUAL_COLOR, icon="moon",
    subcategory="Effects",
    description="Phase-accurate moon disc with illumination and next full/new. Approximates upcoming total lunar eclipses (blood moons) and solar-eclipse seasons; Southern hemisphere flips the waxing/waning limb. Timings are approximate (±1 day)."
                "full/new moon. Pure math + Cairo (no network). Ported from the standalone moon "
                "widget / Sci-Fi HUD.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=50, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=160, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Moon radius", kind=INT, default=36, minimum=8, maximum=400, group="Shape"),
        PropertySpec(key="show_labels", label="Show text labels", kind=BOOL, default=True, group="Labels"),
        PropertySpec(key="label_gap", label="Label gap from moon", kind=INT, default=26, minimum=4, maximum=200, group="Labels"),
        PropertySpec(key="font_family", label="Font", kind=FONT, default="Sans", group="Labels"),
        PropertySpec(key="font_size", label="Name size", kind=INT, default=15, minimum=8, maximum=48, group="Labels"),
        PropertySpec(key="detail_font_size", label="Detail size", kind=INT, default=12, minimum=8, maximum=32, group="Labels"),
        PropertySpec(key="color", label="Lit face colour", kind=COLOR, default="#26fdf1", group="Style"),
        *_GRADIENT_FILL,
        PropertySpec(key="dark_color", label="Dark face colour", kind=COLOR, default="#0a2226", group="Style"),
        PropertySpec(key="rim_color", label="Rim colour", kind=COLOR, default="#0fb7ad", group="Style"),
        PropertySpec(key="text_color", label="Label colour", kind=COLOR, default="#5fd8ce", group="Style"),
        PropertySpec(key="show_brackets", label="Corner brackets", kind=BOOL, default=True, group="Frame"),
        PropertySpec(key="bracket_pad", label="Bracket padding", kind=INT, default=12, minimum=0, maximum=80, group="Frame",
                     help="How far outside the moon (and labels) the bracket box extends."),
        PropertySpec(key="bracket_length", label="Bracket arm length", kind=INT, default=18, minimum=4, maximum=200, group="Frame",
                     help="Length of each L-shaped corner arm in pixels."),
        PropertySpec(key="bracket_thickness", label="Bracket thickness", kind=FLOAT, default=2.0, minimum=0.5, maximum=12, step=0.5, group="Frame"),
        PropertySpec(key="southern_hemisphere", label="Southern hemisphere", kind=BOOL, default=False, group="Astronomy"),
    ],
))

# --------------------------------------------------------------- Corner Brackets
register(NodeSpec(
    type="visual.corner_brackets", category="visual", label="Corner Brackets", color=VISUAL_COLOR, icon="frame",
    subcategory="Effects",
    description="HUD-style L-shaped corner marks framing a rectangular region. Same motif as the "
                "moon widget / Sci-Fi HUD card frame — place anywhere and size independently.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="width", label="Width", kind=INT, default=200, minimum=16, maximum=5000, group="Shape"),
        PropertySpec(key="height", label="Height", kind=INT, default=120, minimum=16, maximum=5000, group="Shape"),
        PropertySpec(key="arm_length", label="Arm length", kind=INT, default=20, minimum=4, maximum=400, group="Shape",
                     help="How long each corner arm is. Clamped so it never exceeds half the box."),
        PropertySpec(key="thickness", label="Line thickness", kind=FLOAT, default=2.0, minimum=0.5, maximum=20, step=0.5, group="Shape"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#26fdf1", group="Style"),
        *_GRADIENT_FILL,
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=0.6, minimum=0, maximum=1, step=0.05, group="Style"),
        PropertySpec(key="top_left", label="Top-left", kind=BOOL, default=True, group="Corners"),
        PropertySpec(key="top_right", label="Top-right", kind=BOOL, default=True, group="Corners"),
        PropertySpec(key="bottom_left", label="Bottom-left", kind=BOOL, default=True, group="Corners"),
        PropertySpec(key="bottom_right", label="Bottom-right", kind=BOOL, default=True, group="Corners"),
    ],
))

# --------------------------------------------------------------- Radar Sweep
register(NodeSpec(
    type="visual.radar_sweep", category="visual", label="Radar Sweep", color=VISUAL_COLOR, icon="radar",
    subcategory="Effects",
    description="Concentric range rings, crosshairs, a rotating sweep beam with a fading trail, "
                "and optional fixed blips that flare as the beam passes — the ambient radar under "
                "the reactor gauge in the Sci-Fi / JARVIS HUD.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=INT, default=68, minimum=8, maximum=2000, group="Shape"),
        PropertySpec(key="ring_count", label="Range rings", kind=INT, default=3, minimum=1, maximum=12, group="Shape"),
        PropertySpec(key="show_crosshairs", label="Show crosshairs", kind=BOOL, default=True, group="Shape"),
        PropertySpec(key="trail_length", label="Sweep trail length", kind=INT, default=24, minimum=4, maximum=90, group="Animation",
                     help="How many faded beam segments trail behind the leading edge."),
        PropertySpec(key="sweep_speed_dps", label="Sweep speed (deg/sec)", kind=FLOAT, default=90.0,
                     minimum=-720, maximum=720, group="Animation",
                     help="0 = static. Negative reverses direction."),
        PropertySpec(key="color", label="Primary colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="dim_color", label="Ring / cross colour", kind=COLOR, default="#0fb7ad", group="Style"),
        PropertySpec(key="blip_color", label="Blip colour", kind=COLOR, default="#ffcf5c", group="Style"),
        PropertySpec(key="blip_count", label="Blip count", kind=INT, default=3, minimum=0, maximum=12, group="Blips",
                     help="0 disables blips. Positions are deterministic from the seed below."),
        PropertySpec(key="blip_seed", label="Blip layout seed", kind=INT, default=1, minimum=0, maximum=9999, group="Blips",
                     help="Change this to rearrange the fixed blip positions."),
    ],
))

# --------------------------------------------------------------- Reactor Gauge
register(NodeSpec(
    type="visual.reactor_gauge", category="visual", label="Reactor Gauge", color=VISUAL_COLOR, icon="gauge",
    subcategory="Gauges & Bars",
    description="Large central dial from the Sci-Fi / JARVIS HUD: dual counter-rotating dashed "
                "rings, tick marks, a thick value arc, orbiting accent dots, and a big centred "
                "readout. Wire Value to any numeric source (e.g. mean of vitals, CPU, GPU).",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=42.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=0, maximum=10000),
        PropertySpec(key="min_value", label="Min", kind=FLOAT, default=0.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="max_value", label="Max", kind=FLOAT, default=100.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="cx", label="Center X", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=INT, default=96, minimum=24, maximum=2000, group="Shape"),
        PropertySpec(key="label", label="Centre label", kind=STRING, default="REACTOR OUTPUT %", group="Labels"),
        PropertySpec(key="show_value_text", label="Show value number", kind=BOOL, default=True, group="Labels"),
        PropertySpec(key="value_suffix", label="Value suffix", kind=STRING, default="%", group="Labels",
                     help="Appended after the number in the centre readout -- e.g. '%', ' RPM', ' MHz', "
                          "'\u00b0C'. The readout always shows the raw bound value (not a normalized "
                          "percentage), so set this to match whatever source you wired into Value."),
        PropertySpec(key="value_font_size", label="Value text size", kind=INT, default=46, minimum=10, maximum=200, group="Labels"),
        PropertySpec(key="label_font_size", label="Label text size", kind=INT, default=11, minimum=6, maximum=48, group="Labels"),
        PropertySpec(key="font_family", label="Font", kind=FONT, default="Orbitron", group="Labels"),
        PropertySpec(key="outer_speed_dps", label="Outer ring speed (deg/sec)", kind=FLOAT, default=12.0,
                     minimum=-360, maximum=360, group="Animation"),
        PropertySpec(key="inner_speed_dps", label="Inner ring speed (deg/sec)", kind=FLOAT, default=-27.0,
                     minimum=-360, maximum=360, group="Animation",
                     help="Negative = opposite direction to the outer ring."),
        PropertySpec(key="color", label="Primary colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="dim_color", label="Dim / track colour", kind=COLOR, default="#0fb7ad", group="Style"),
        PropertySpec(key="accent_color", label="Orbit dot colour", kind=COLOR, default="#ffcf5c", group="Style"),
        PropertySpec(key="warn_color", label="Critical colour", kind=COLOR, default="#ff3b3b", group="Alert"),
        PropertySpec(key="critical_threshold", label="Critical at ≥", kind=FLOAT, default=90.0, minimum=0, maximum=10000, group="Alert",
                     help="When Value reaches this (in the same units as Max), the arc and number "
                          "switch to the critical colour and pulse."),
        PropertySpec(key="pulse_when_critical", label="Pulse when critical", kind=BOOL, default=True, group="Alert"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Analog Clock
register(NodeSpec(
    type="visual.analog_clock", category="visual", label="Analog Clock", color=VISUAL_COLOR, icon="clock",
    subcategory="Effects",
    description="A real wall-clock face driven by the system clock: hour/minute/second hands, "
                "tick marks, optional hour numerals, and an optional digital readout under the dial. "
                "Uses wall_clock() so hand motion stays correct under load.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=120, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=INT, default=80, minimum=16, maximum=2000, group="Shape"),
        PropertySpec(key="show_seconds", label="Show seconds hand", kind=BOOL, default=True, group="Hands"),
        PropertySpec(key="smooth_seconds", label="Smooth seconds", kind=BOOL, default=True, group="Hands",
                     help="When on, the seconds hand sweeps continuously using fractional wall time. "
                          "When off, it jumps once per whole second."),
        PropertySpec(key="show_numerals", label="Show hour numerals", kind=BOOL, default=True, group="Face"),
        PropertySpec(key="show_minute_ticks", label="Show minute ticks", kind=BOOL, default=True, group="Face"),
        PropertySpec(key="show_digital", label="Show digital time", kind=BOOL, default=False, group="Face",
                     help="Draws HH:MM:SS (or HH:MM) centred under the dial."),
        PropertySpec(key="digital_with_seconds", label="Digital includes seconds", kind=BOOL, default=True, group="Face"),
        PropertySpec(key="font_family", label="Numeral / digital font", kind=FONT, default="Share Tech Mono", group="Face"),
        PropertySpec(key="numeral_size", label="Numeral size", kind=INT, default=14, minimum=6, maximum=80, group="Face"),
        PropertySpec(key="digital_size", label="Digital size", kind=INT, default=12, minimum=6, maximum=80, group="Face"),
        PropertySpec(key="face_color", label="Face fill", kind=COLOR, default="#0a2226", group="Style"),
        *_GRADIENT_FILL,
        PropertySpec(key="rim_color", label="Rim colour", kind=COLOR, default="#0fb7ad", group="Style"),
        PropertySpec(key="tick_color", label="Tick colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="numeral_color", label="Numeral colour", kind=COLOR, default="#5fd8ce", group="Style"),
        PropertySpec(key="hour_hand_color", label="Hour hand", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="minute_hand_color", label="Minute hand", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="second_hand_color", label="Second hand", kind=COLOR, default="#ffcf5c", group="Style"),
        PropertySpec(key="hub_color", label="Centre hub", kind=COLOR, default="#ffcf5c", group="Style"),
        PropertySpec(key="rim_thickness", label="Rim thickness", kind=FLOAT, default=2.0, minimum=0.5, maximum=20, step=0.5, group="Shape"),
    ],
))

# --------------------------------------------------------------- Star
register(NodeSpec(
    type="visual.star", category="visual", label="Star", color=VISUAL_COLOR, icon="star",
    subcategory="Shapes",
    description="A filled/stroked star that can switch silhouette: classic pointy star, pentagram "
                "(five-point unicursal), Star of David (two overlapping triangles), or a tall "
                "Christmas-tree star. Point count and inner radius control the regular-star look.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=80, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=80, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Outer radius", kind=INT, default=48, minimum=4, maximum=2000, group="Shape"),
        PropertySpec(key="style", label="Style", kind=ENUM, default="regular",
                     choices=["regular", "pentagram", "star_of_david", "christmas"],
                     choice_labels=["Regular star", "Pentagram", "Star of David", "Christmas tree star"],
                     group="Shape"),
        PropertySpec(key="points", label="Points", kind=INT, default=5, minimum=3, maximum=16, group="Shape",
                     help="Only used for Regular star. Pentagram is fixed at 5; Star of David is two triangles; "
                          "Christmas is a tall 4/5-point motif."),
        PropertySpec(key="inner_ratio", label="Inner radius ratio", kind=FLOAT, default=0.4, minimum=0.05, maximum=0.95, step=0.05, group="Shape",
                     help="How deep the notches are on a Regular star (0.4 ≈ classic). Ignored by other styles."),
        PropertySpec(key="rotation_deg", label="Rotation", kind=FLOAT, default=-90.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=-360, maximum=360, group="Shape",
                     help="Default -90 points a tip straight up."),
        PropertySpec(key="fill", label="Fill", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="stroke", label="Stroke", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="line_width", label="Stroke width", kind=FLOAT, default=2.0, minimum=0.5, maximum=40, step=0.5, group="Style"),
        PropertySpec(key="color", label="Fill colour", kind=COLOR, default="#ffcf5c", group="Style"),
        PropertySpec(key="stroke_color", label="Stroke colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
    
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Triangle
register(NodeSpec(
    type="visual.triangle", category="visual", label="Triangle", color=VISUAL_COLOR, icon="triangle",
    subcategory="Shapes",
    description="A filled/stroked triangle — equilateral by default, or free-form via three corner offsets.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=80, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=80, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="size", label="Size", kind=INT, default=64, minimum=4, maximum=4000, group="Shape",
                     help="Bounding size for an equilateral triangle (ignored when Use free corners is on)."),
        PropertySpec(key="rotation_deg", label="Rotation", kind=FLOAT, default=-90.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=-360, maximum=360, group="Shape"),
        PropertySpec(key="free_corners", label="Use free corners", kind=BOOL, default=False, group="Shape",
                     help="When on, the three corner offsets below replace the equilateral layout."),
        PropertySpec(key="x1", label="Corner 1 X offset", kind=INT, default=0, minimum=-4000, maximum=4000, group="Corners"),
        PropertySpec(key="y1", label="Corner 1 Y offset", kind=INT, default=-40, minimum=-4000, maximum=4000, group="Corners"),
        PropertySpec(key="x2", label="Corner 2 X offset", kind=INT, default=-35, minimum=-4000, maximum=4000, group="Corners"),
        PropertySpec(key="y2", label="Corner 2 Y offset", kind=INT, default=24, minimum=-4000, maximum=4000, group="Corners"),
        PropertySpec(key="x3", label="Corner 3 X offset", kind=INT, default=35, minimum=-4000, maximum=4000, group="Corners"),
        PropertySpec(key="y3", label="Corner 3 Y offset", kind=INT, default=24, minimum=-4000, maximum=4000, group="Corners"),
        PropertySpec(key="fill", label="Fill", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="stroke", label="Stroke", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="line_width", label="Stroke width", kind=FLOAT, default=2.0, minimum=0.5, maximum=40, step=0.5, group="Style"),
        PropertySpec(key="color", label="Fill colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="stroke_color", label="Stroke colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Circle
register(NodeSpec(
    type="visual.circle", category="visual", label="Circle", color=VISUAL_COLOR, icon="circle",
    subcategory="Shapes",
    description="A filled/stroked circle or ring (ellipse when width ≠ height).",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=80, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=80, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=INT, default=40, minimum=1, maximum=2000, group="Shape",
                     help="Used when Width/Height are 0. Otherwise those override for an ellipse."),
        PropertySpec(key="width", label="Width (ellipse)", kind=INT, default=0, minimum=0, maximum=4000, group="Shape",
                     help="0 = use Radius for a circle. Set both Width and Height for an ellipse."),
        PropertySpec(key="height", label="Height (ellipse)", kind=INT, default=0, minimum=0, maximum=4000, group="Shape"),
        PropertySpec(key="start_angle_deg", label="Start angle", kind=INT, default=0, minimum=-360, maximum=360, group="Shape"),
        PropertySpec(key="sweep_deg", label="Sweep angle", kind=INT, default=360, minimum=1, maximum=360, group="Shape",
                     help="360 = full circle. Smaller values draw an arc/pie slice."),
        PropertySpec(key="pie", label="Close as pie slice", kind=BOOL, default=False, group="Shape",
                     help="When Sweep < 360, draw radii back to the centre (pie) instead of a bare arc."),
        PropertySpec(key="fill", label="Fill", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="stroke", label="Stroke", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="line_width", label="Stroke width", kind=FLOAT, default=2.0, minimum=0.5, maximum=40, step=0.5, group="Style"),
        PropertySpec(key="color", label="Fill colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="stroke_color", label="Stroke colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
    
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Wall Calendar
register(NodeSpec(
    type="visual.wall_calendar", category="visual", label="Wall Calendar", color=VISUAL_COLOR, icon="calendar",
    subcategory="Text",
    description="A month wall calendar: title, weekday headers, and a day grid with today "
                "highlighted. Driven by the system date (no network). Opacity controls the "
                "whole widget for overlay use.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cell_w", label="Cell width", kind=INT, default=36, minimum=16, maximum=120, group="Shape"),
        PropertySpec(key="cell_h", label="Cell height", kind=INT, default=28, minimum=14, maximum=100, group="Shape"),
        PropertySpec(key="show_title", label="Show month title", kind=BOOL, default=True, group="Layout"),
        PropertySpec(key="show_weekdays", label="Show weekday headers", kind=BOOL, default=True, group="Layout"),
        PropertySpec(key="week_start", label="Week starts on", kind=ENUM, default="monday",
                     choices=["monday", "sunday"], group="Layout"),
        PropertySpec(key="show_outside_days", label="Show other-month days", kind=BOOL, default=False, group="Layout",
                     help="Grey out days from the previous/next month that fall in the first/last week."),
        PropertySpec(key="font_family", label="Font", kind=FONT, default="Sans", group="Style"),
        PropertySpec(key="title_size", label="Title size", kind=INT, default=16, minimum=8, maximum=48, group="Style"),
        PropertySpec(key="day_size", label="Day number size", kind=INT, default=13, minimum=8, maximum=32, group="Style"),
        PropertySpec(key="weekday_size", label="Weekday header size", kind=INT, default=11, minimum=8, maximum=24, group="Style"),
        PropertySpec(key="title_color", label="Title colour", kind=COLOR, default="#FFFFFF", group="Style"),
        PropertySpec(key="weekday_color", label="Weekday colour", kind=COLOR, default="#9aa2ad", group="Style"),
        PropertySpec(key="day_color", label="Day colour", kind=COLOR, default="#e8eaed", group="Style"),
        PropertySpec(key="today_color", label="Today colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="today_fill", label="Today fill", kind=COLOR, default="#4fd1c5", group="Style"),
        *_GRADIENT_FILL,
        PropertySpec(key="outside_color", label="Other-month colour", kind=COLOR, default="#5c636d", group="Style"),
        PropertySpec(key="grid_color", label="Grid colour", kind=COLOR, default="#33313a", group="Style"),
        PropertySpec(key="show_grid", label="Show grid lines", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="today_style", label="Today style", kind=ENUM, default="fill",
                     choices=["fill", "ring", "bold"], group="Style",
                     help="fill = filled cell, ring = outline, bold = larger/bolder number only."),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style",
                     help="Overall transparency of the calendar (title, grid, and numbers)."),
    ],
))

# --------------------------------------------------------------- Custom Lua
# Bindable in1..in12: wire Studio sources/logic into imported or hand-written
# Cairo. Generator injects locals in1..in12. Legacy import auto-wires common
# sensors and patches reads to prefer bound values when present.
_CUSTOM_LUA_INPUT_LABELS = {
    1: "Input 1 (often CPU %)",
    2: "Input 2 (often RAM %)",
    3: "Input 3 (often Disk %)",
    4: "Input 4 (often CPU temp)",
    5: "Input 5 (often GPU util)",
    6: "Input 6 (often GPU temp)",
    7: "Input 7",
    8: "Input 8",
    9: "Input 9",
    10: "Input 10",
    11: "Input 11",
    12: "Input 12",
}
_CUSTOM_LUA_INPUTS = [
    PropertySpec(
        key=f"in{i}",
        label=_CUSTOM_LUA_INPUT_LABELS.get(i, f"Input {i}"),
        kind=FLOAT, default=0.0,
        bindable=True,
        accepts=(KIND_PERCENT, KIND_CELSIUS, KIND_NUMBER, KIND_TEXT, KIND_CATEGORY),
        group="Data inputs",
        help=(
            f"Wire a source or logic node here. Available in Lua as local in{i}. "
            "Legacy imports auto-assign common sensors to early slots; bound values "
            "override internal conky_parse/cache reads when the bridge is active."
        ),
    )
    for i in range(1, 13)
]
register(NodeSpec(
    type="visual.custom_lua", category="visual", label="Custom Lua", color=VISUAL_COLOR, icon="code",
    subcategory="Advanced", simple_mode=False,
    description="Raw Cairo drawing code inside this node's draw call (cr, W, H already in scope). "
                "Wire sources or logic into Input 1–12 (locals in1..in12). Legacy import auto-wires "
                "common vitals into these inputs and patches the Lua so bound values win over "
                "internal conky_parse/cache reads. Offset X/Y shifts the block without editing Lua.",
    properties=[
        PropertySpec(key="x", label="Offset X", kind=INT, default=0, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Offset Y", kind=INT, default=0, minimum=-4000, maximum=4000, group="Position"),
        *_CUSTOM_LUA_INPUTS,
        PropertySpec(key="code", label="Lua code", kind=CODE,
                     default="-- cr, W, H are in scope\n"
                             "-- Wired sources appear as locals in1..in12\n"
                             "-- Prefer: local cpu = tonumber(in1) or safe_number('${cpu}', 0)\n",
                     help="Runs inside local function(cr, W, H). Bound Data inputs are injected "
                          "as locals in1..in12 before your code. Framework helpers (clamp, lerp, "
                          "rounded_rect, load_image_cached, wall_clock, ...) are available."),
    ],
))


# --------------------------------------------------------------- Rectangle
register(NodeSpec(
    type="visual.rectangle", category="visual", label="Rectangle", color=VISUAL_COLOR,
    icon="square", subcategory="Shapes", simple_mode=True,
    description="Filled/stroked rectangle or rounded rect — panels, cards, backdrop chips.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="width", label="Width", kind=INT, default=160, minimum=1, maximum=5000, group="Shape"),
        PropertySpec(key="height", label="Height", kind=INT, default=80, minimum=1, maximum=4000, group="Shape"),
        PropertySpec(key="corner_radius", label="Corner radius", kind=INT, default=0, minimum=0, maximum=400, group="Shape"),
        PropertySpec(key="fill", label="Fill", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="stroke", label="Stroke", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="line_width", label="Stroke width", kind=FLOAT, default=1.5, minimum=0.5, maximum=40, step=0.5, group="Style"),
        PropertySpec(key="color", label="Fill colour", kind=COLOR, default="#1a222c", group="Style"),
        PropertySpec(key="stroke_color", label="Stroke colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Horizontal Line
register(NodeSpec(
    type="visual.hline", category="visual", label="Horizontal Line", color=VISUAL_COLOR,
    icon="minus", subcategory="Shapes", simple_mode=True,
    description="Horizontal rule — section dividers under titles.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=40, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="length", label="Length", kind=INT, default=200, minimum=1, maximum=5000, group="Shape"),
        PropertySpec(key="line_width", label="Thickness", kind=FLOAT, default=1.5, minimum=0.5, maximum=40, step=0.5, group="Style"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=0.85, minimum=0, maximum=1, step=0.05, group="Style"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Vertical Line
register(NodeSpec(
    type="visual.vline", category="visual", label="Vertical Line", color=VISUAL_COLOR,
    icon="minus", subcategory="Shapes", simple_mode=True,
    description="Vertical rule — column gutters and side rails.",
    properties=[
        PropertySpec(key="x", label="X", kind=INT, default=40, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="length", label="Length", kind=INT, default=120, minimum=1, maximum=5000, group="Shape"),
        PropertySpec(key="line_width", label="Thickness", kind=FLOAT, default=1.5, minimum=0.5, maximum=40, step=0.5, group="Style"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#26fdf1", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=0.85, minimum=0, maximum=1, step=0.05, group="Style"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- Crosshair
register(NodeSpec(
    type="visual.crosshair", category="visual", label="Crosshair", color=VISUAL_COLOR,
    icon="plus", subcategory="Shapes", simple_mode=True,
    description="Centered cross — HUD reticles and radar centres.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="size", label="Arm length", kind=INT, default=24, minimum=2, maximum=2000, group="Shape"),
        PropertySpec(key="gap", label="Centre gap", kind=INT, default=4, minimum=0, maximum=200, group="Shape"),
        PropertySpec(key="line_width", label="Thickness", kind=FLOAT, default=1.5, minimum=0.5, maximum=20, step=0.5, group="Style"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#26fdf1", group="Style"),
        *_GRADIENT_FILL,
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=0.9, minimum=0, maximum=1, step=0.05, group="Style"),
    ],
))

# --------------------------------------------------------------- Ring Track
register(NodeSpec(
    type="visual.ring_track", category="visual", label="Ring Track", color=VISUAL_COLOR,
    icon="ring", subcategory="Gauges & Bars", simple_mode=True,
    description="Static ring or arc track (no value). Layer under Arc Gauge or as pure chrome.",
    properties=[
        PropertySpec(key="cx", label="Center X", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=INT, default=70, minimum=4, maximum=2000, group="Shape"),
        PropertySpec(key="thickness", label="Thickness", kind=INT, default=8, minimum=1, maximum=200, group="Shape"),
        PropertySpec(key="start_angle_deg", label="Start angle", kind=INT, default=-90, minimum=-360, maximum=360, group="Shape"),
        PropertySpec(key="sweep_deg", label="Sweep angle", kind=INT, default=360, minimum=1, maximum=360, group="Shape"),
        PropertySpec(key="cap_style", label="End caps", kind=ENUM, default="round",
                     choices=["butt", "round"], group="Shape"),
        PropertySpec(key="color", label="Colour", kind=COLOR, default="#33313a", group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=0.7, minimum=0, maximum=1, step=0.05, group="Style"),
        *_GRADIENT_FILL,
    ],
))

# --------------------------------------------------------------- LED Dot
register(NodeSpec(
    type="visual.led_dot", category="visual", label="LED Dot", color=VISUAL_COLOR,
    icon="circle", subcategory="Gauges & Bars", simple_mode=True,
    description="Small status light. On colour when Value ≥ threshold, else off colour.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="threshold", label="On when ≥", kind=FLOAT, default=0.5, minimum=0, maximum=10000, group="Logic"),
        PropertySpec(key="cx", label="Center X", kind=INT, default=40, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=40, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=INT, default=6, minimum=1, maximum=200, group="Shape"),
        PropertySpec(key="color_on", label="On colour", kind=COLOR, default="#4fd1c5", group="Style"),
        *_GRADIENT_FILL,
        PropertySpec(key="color_off", label="Off colour", kind=COLOR, default="#33313a", group="Style"),
        PropertySpec(key="glow", label="Glow when on", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="opacity", label="Opacity", kind=FLOAT, default=1.0, minimum=0, maximum=1, step=0.05, group="Style"),
    ],
))

# --------------------------------------------------------------- Sparkline
register(NodeSpec(
    type="visual.sparkline", category="visual", label="Sparkline", color=VISUAL_COLOR,
    icon="graph", subcategory="Graphs",
    description="A compact, borderless trend line -- the same ring-buffer mechanism as History "
                "Graph, but sized and styled for a dense dashboard row rather than a standalone "
                "chart: no frame, thinner line, and an Auto-scale option that fits the line to "
                "whatever range the last N samples actually covered instead of a fixed Min/Max.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="auto_scale", label="Auto-scale to recent range", kind=BOOL, default=True, group="Range",
                     help="Fits the line to the min/max of the samples currently on screen. Turn "
                          "off to use fixed Min/Max instead -- e.g. to keep several sparklines "
                          "visually comparable to each other."),
        PropertySpec(key="min_value", label="Min", kind=FLOAT, default=0.0, minimum=0, maximum=10000, group="Range",
                     help="Only used when Auto-scale is off."),
        PropertySpec(key="max_value", label="Max", kind=FLOAT, default=100.0, minimum=0, maximum=10000, group="Range",
                     help="Only used when Auto-scale is off."),
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="width", label="Width", kind=INT, default=120, minimum=8, maximum=4000, group="Shape"),
        PropertySpec(key="height", label="Height", kind=INT, default=28, minimum=6, maximum=2000, group="Shape"),
        PropertySpec(key="history_length", label="Samples kept", kind=INT, default=32, minimum=4, maximum=600, group="Shape"),
        PropertySpec(key="line_width", label="Line width", kind=FLOAT, default=1.5, minimum=0.2, maximum=20, step=0.2, group="Style"),
        PropertySpec(key="fill", label="Faint fill under line", kind=BOOL, default=False, group="Style"),
        PropertySpec(key="color", label="Line colour", kind=COLOR, default="#4fd1c5", group="Style"),
    ],
))

# --------------------------------------------------------------- Multi-Series Line Graph
register(NodeSpec(
    type="visual.multi_line_graph", category="visual", label="Multi-Series Line Graph", color=VISUAL_COLOR,
    icon="graph", subcategory="Graphs",
    description="Up to three History-Graph-style trend lines sharing one set of axes and one "
                "fixed Min/Max -- e.g. CPU vs. GPU temperature over time, or upload vs. download "
                "speed. Any series left unwired simply isn't drawn, so it's fine to use this with "
                "only one or two of the three slots filled.",
    properties=[
        PropertySpec(key="title_label", label="Title / caption", kind=STRING, default="", bindable=True,
                     accepts=ALL_KINDS, group="Label",
                     help="Optional caption above the multi-series graph."),
        PropertySpec(key="title_font_size", label="Title size", kind=INT, default=11, minimum=6, maximum=48, group="Label"),
        PropertySpec(key="title_color", label="Title colour", kind=COLOR, default="#9aa2ad", group="Label"),
        PropertySpec(key="value_a", label="Series A", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9, group="Series"),
        PropertySpec(key="color_a", label="Series A colour", kind=COLOR, default="#4fd1c5", group="Series"),
        PropertySpec(key="value_b", label="Series B", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9, group="Series"),
        PropertySpec(key="color_b", label="Series B colour", kind=COLOR, default="#e0b34d", group="Series"),
        PropertySpec(key="value_c", label="Series C", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9, group="Series"),
        PropertySpec(key="color_c", label="Series C colour", kind=COLOR, default="#e05f5f", group="Series"),
        PropertySpec(key="min_value", label="Min", kind=FLOAT, default=0.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="max_value", label="Max", kind=FLOAT, default=100.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="x", label="X", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="y", label="Y", kind=INT, default=20, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="width", label="Width", kind=INT, default=220, minimum=8, maximum=4000, group="Shape"),
        PropertySpec(key="height", label="Height", kind=INT, default=70, minimum=8, maximum=2000, group="Shape"),
        PropertySpec(key="history_length", label="Samples kept", kind=INT, default=48, minimum=4, maximum=600, group="Shape"),
        PropertySpec(key="line_width", label="Line width", kind=FLOAT, default=2.0, minimum=0.2, maximum=20, step=0.2, group="Style"),
        PropertySpec(key="track_color", label="Frame colour", kind=COLOR, default="#33313a", group="Style"),
    ],
))

# --------------------------------------------------------------- Segmented Gauge
register(NodeSpec(
    type="visual.segmented_gauge", category="visual", label="Segmented Gauge", color=VISUAL_COLOR,
    icon="ring", subcategory="Gauges & Bars",
    description="An LED-bar-style radial gauge: discrete lit/unlit arc segments instead of a "
                "smooth sweep, the arc equivalent of Bar's 'segmented' style.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=50.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=0, maximum=10000),
        PropertySpec(key="min_value", label="Min", kind=FLOAT, default=0.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="max_value", label="Max", kind=FLOAT, default=100.0, minimum=0, maximum=10000, group="Range"),
        PropertySpec(key="cx", label="Center X", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="cy", label="Center Y", kind=INT, default=100, minimum=-4000, maximum=4000, group="Position"),
        PropertySpec(key="radius", label="Radius", kind=INT, default=70, minimum=4, maximum=2000, group="Shape"),
        PropertySpec(key="thickness", label="Thickness", kind=INT, default=12, minimum=1, maximum=200, group="Shape"),
        PropertySpec(key="start_angle_deg", label="Start angle", kind=INT, default=-90, minimum=-360, maximum=360, group="Shape"),
        PropertySpec(key="sweep_deg", label="Sweep angle", kind=INT, default=270, minimum=1, maximum=360, group="Shape"),
        PropertySpec(key="segment_count", label="Segments", kind=INT, default=12, minimum=2, maximum=100, group="Shape"),
        PropertySpec(key="gap_deg", label="Gap between segments", kind=FLOAT, default=4.0, minimum=0, maximum=30, step=0.5, group="Shape"),
        PropertySpec(key="color", label="Lit colour", kind=COLOR, default="#4fd1c5", group="Style"),
        PropertySpec(key="track_color", label="Unlit colour", kind=COLOR, default="#33313a", group="Style"),
        PropertySpec(key="show_value_text", label="Show value as text", kind=BOOL, default=True, group="Style"),
        PropertySpec(key="value_font_size", label="Value text size", kind=INT, default=20, minimum=6, maximum=200, group="Style"),
        PropertySpec(key="value_suffix", label="Value text suffix", kind=STRING, default="%", group="Style"),
    ],
))


