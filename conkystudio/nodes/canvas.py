"""
The Canvas node is a special, always-present, non-deletable pseudo-node
(id == "canvas") shown at the top of the graph. It exists so window/FPS
settings are edited through the exact same property-panel mechanism as
every other node, instead of a separate modal dialog -- one less thing
to learn. Its fields map 1:1 onto model.project.CanvasSettings and are
consumed directly by codegen/conky_conf_gen.py, not by lua_gen.py (it
produces no draw function of its own).
"""
from __future__ import annotations

from conkystudio.nodes.registry import NodeSpec, PropertySpec, register, ENUM, INT, BOOL, STRING, FLOAT
from conkystudio.model.project import CANVAS_NODE_ID  # re-exported for convenience

register(
    NodeSpec(
        type="canvas.root",
        category="canvas",
        label="Canvas",
        description="Window size, position, and frame rate for the whole HUD.",
        color="#c9a227",
        icon="monitor",
        properties=[
            PropertySpec(key="width", label="Width (px)", kind=INT, default=460, minimum=64, maximum=7680, step=1, group="Size"),
            PropertySpec(key="height", label="Height (px)", kind=INT, default=640, minimum=64, maximum=4320, step=1, group="Size"),
            PropertySpec(
                key="alignment", label="Screen anchor", kind=ENUM, default="top_left",
                choices=["top_left", "top_right", "top_middle", "bottom_left", "bottom_right",
                         "bottom_middle", "middle_left", "middle_right", "middle_middle"],
                group="Size",
                help="Matches Conky's own `alignment` setting.",
            ),
            PropertySpec(key="gap_x", label="Gap X (px)", kind=INT, default=24, minimum=0, maximum=2000, group="Size"),
            PropertySpec(key="gap_y", label="Gap Y (px)", kind=INT, default=24, minimum=0, maximum=2000, group="Size"),
            PropertySpec(
                key="fps", label="Draw rate (FPS)", kind=INT, default=30, minimum=1, maximum=144, step=1,
                group="Performance",
                help="How often Cairo redraws. Higher looks smoother (glow/spiral/pulse effects) but costs more CPU.",
            ),
            PropertySpec(
                key="stats_hz", label="Sensor refresh (Hz)", kind=FLOAT, default=2.0, minimum=0.1, maximum=30.0, step=0.1,
                group="Performance",
                help="How often data sources are actually re-read. Kept independent of draw rate: "
                     "redrawing a glow's phase 30x/sec doesn't mean CPU temp needs re-reading 30x/sec too.",
            ),
            PropertySpec(
                key="window_type", label="Window layering", kind=ENUM, default="auto",
                choices=["auto", "normal", "desktop", "dock"],
                choice_labels=["Auto-detect (recommended)", "Normal (undecorated, always-below)", "Desktop", "Dock"],
                group="Window",
                help="Auto uses session-specific defaults (X11 and Plasma/wlroots Wayland → normal). "
                     "GNOME Wayland cannot host overlays regardless of this setting — see Tools → Hardware & Session. "
                     "Override only if a HUD flickers or won't stay anchored on a supported session.",
            ),
            PropertySpec(key="transparent", label="Transparent background", kind=BOOL, default=True, group="Window",
                         help="Requires a compositor (picom, or your DE's built-in one) for true per-pixel alpha."),
            PropertySpec(key="window_class", label="Window class", kind=STRING, default="conky-studio", group="Window"),
            PropertySpec(
                key="show_windows_panel",
                label="Multi-window / multi-monitor",
                kind=BOOL,
                default=False,
                group="Window",
                help="Show the Windows panel dock. This only controls panel visibility — "
                     "it does not enable or disable multi-window data. Uncheck to hide the "
                     "panel if you only need a single monitor.",
            ),
        ],
    )
)


