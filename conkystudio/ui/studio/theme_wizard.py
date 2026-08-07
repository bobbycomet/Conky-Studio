"""
Project -> New HUD -> Theme Wizard: category + resolution + panel
checkboxes generate a starter graph, instead of the plainer
_starter_project() single CPU-gauge example. Data-driven on purpose --
CATEGORY_STYLES and LAYOUT_BUILDERS are both small dicts, so adding an
eighth category or more panels later is additive, not a rewrite.

Every panel builder takes draw coordinates and MUST feed them into the
draw-position props (cx/cy or x/y) of every visual node it creates, not
just into the NodeInstance's own x/y (which only places the box on the
node-graph editor canvas).

Layouts are full-canvas and denser than the original demos: chrome
(rectangles, lines, ring tracks, LEDs), dual metrics, history graphs,
and optional logic (threshold → LED) when those node types exist.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QButtonGroup, QRadioButton, QPushButton, QGroupBox, QGridLayout,
    QScrollArea, QWidget, QFrame,
)

from conkystudio.model.project import Project, NodeInstance, new_id, CanvasSettings
from conkystudio.ui.studio.theme_wizard_patch import (
    merge_options_for_tier,
    ensure_logic_demo_edge,
    add_showcase_extras,
    DEFAULT_OPTIONS_BY_TIER,
)

RESOLUTIONS = {
    "1920x1080": (1920, 1080),
    "2560x1440": (2560, 1440),
    "3440x1440": (3440, 1440),
    "3840x2160": (3840, 2160),
}

CATEGORY_STYLES = {
    "Minimal": {
        "accent": "#e8eaed", "track": "#2a2f38", "panel": "#14181e",
        "flourish": False, "font": "Sans",
        "text_dim": "#9aa2ad", "warn": "#ff6b6b", "layout": "minimal",
    },
    "Gaming": {
        "accent": "#8a5fd6", "track": "#241f38", "panel": "#120e1c",
        "flourish": True, "font": "Sans",
        "text_dim": "#b8a0e0", "warn": "#ff4d6d", "layout": "gaming",
    },
    "RPG": {
        "accent": "#c9a227", "track": "#3a2f1c", "panel": "#1a1510",
        "flourish": True, "font": "Sans",
        "text_dim": "#d4c4a0", "warn": "#c44", "layout": "rpg",
    },
    "Sci-Fi": {
        "accent": "#26fdf1", "track": "#0a3a40", "panel": "#061418",
        "flourish": True, "font": "Share Tech Mono",
        "text_dim": "#5fd8ce", "warn": "#ff3b3b", "layout": "scifi",
    },
    "Cyberpunk": {
        "accent": "#e0378a", "track": "#2a1030", "panel": "#120810",
        "flourish": True, "font": "Sans",
        "text_dim": "#f0a0c8", "warn": "#00f0ff", "layout": "cyberpunk",
    },
    "Terminal": {
        "accent": "#4caf7d", "track": "#0f1a12", "panel": "#080c09",
        "flourish": False, "font": "Monospace",
        "text_dim": "#7dba94", "warn": "#c9a227", "layout": "terminal",
    },
    "Fantasy": {
        "accent": "#b8a888", "track": "#2f2a1c", "panel": "#16140f",
        "flourish": True, "font": "Sans",
        "text_dim": "#d4c8b0", "warn": "#8b4513", "layout": "fantasy",
    },
    "Batman": {
        "accent": "#3fd6ff", "track": "#0a2a35", "panel": "#050e12",
        "flourish": True, "font": "Share Tech Mono",
        "warn": "#ff3b3b", "text_dim": "#4fb8d6", "layout": "batman",
    },
}
CATEGORY_ORDER = ["Minimal", "Gaming", "RPG", "Sci-Fi", "Cyberpunk", "Terminal", "Fantasy", "Batman"]

# Core system panels
PANEL_ORDER = [
    "Weather", "CPU", "GPU", "RAM", "Disk", "Battery",
    "Network", "Clock", "Calendar", "Music", "Moon", "System",
]

# Extra chrome / behaviour toggles (not data panels)
OPTION_ORDER = [
    ("chrome", "Panel chrome (rects / lines)"),
    ("leds", "Status LEDs (threshold)"),
    ("graphs", "History graphs"),
    ("brackets", "Corner brackets"),
    ("glow", "Glow accents"),
]

DEFAULT_PANELS = ["Weather", "CPU", "GPU", "RAM", "Clock", "Network", "System"]
DEFAULT_OPTIONS = {"chrome": True, "leds": True, "graphs": True, "brackets": True, "glow": True}


def _has_node(type_id: str) -> bool:
    try:
        from conkystudio.nodes import registry
        return registry.has(type_id)
    except Exception:
        return False


def _opts(options: dict | None) -> dict:
    o = dict(DEFAULT_OPTIONS)
    if options:
        o.update(options)
    return o


# ---------------------------------------------------------------------------
# Chrome helpers (use new shape nodes when available)
# ---------------------------------------------------------------------------

def _panel_bg(p: Project, x: int, y: int, w: int, h: int, style: dict, z: int | None = None):
    if not _has_node("visual.rectangle"):
        return
    p.add_node(NodeInstance(
        id=new_id("n"), type="visual.rectangle",
        z=z if z is not None else 0,
        x=x - 20, y=y - 20,
        props={
            "x": x, "y": y, "width": w, "height": h,
            "corner_radius": 8, "fill": True, "stroke": True,
            "line_width": 1.0,
            "color": style.get("panel", "#14181e"),
            "stroke_color": style["track"],
            "opacity": 0.92,
        },
    ))


def _hline(p: Project, x: int, y: int, length: int, style: dict, opacity: float = 0.5):
    if not _has_node("visual.hline"):
        return
    p.add_node(NodeInstance(
        id=new_id("n"), type="visual.hline", z=1, x=x, y=y,
        props={
            "x": x, "y": y, "length": length, "line_width": 1.0,
            "color": style["accent"], "opacity": opacity,
        },
    ))


def _outer_brackets(p: Project, width: int, height: int, style: dict, pad: int = 8, arm: int = 24):
    if not _has_node("visual.corner_brackets"):
        return
    p.add_node(NodeInstance(id=new_id("n"), type="visual.corner_brackets", z=0, x=0, y=0, props={
        "x": pad, "y": pad, "width": width - pad * 2, "height": height - pad * 2,
        "arm_length": arm, "thickness": 2.0, "color": style["accent"], "opacity": 0.45,
    }))


def _header(p: Project, title: str, subtitle: str, style: dict, width: int):
    font = style["font"]
    accent, dim = style["accent"], style.get("text_dim", "#9aa2ad")
    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=40, y=20, props={
        "value": title, "x": 48, "y": 36,
        "font_family": font, "font_size": 16, "bold": True, "color": accent,
    }))
    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=40, y=40, props={
        "value": subtitle, "x": 48, "y": 54,
        "font_family": font, "font_size": 10, "color": dim,
    }))
    _hline(p, 48, 64, min(420, width // 3), style, 0.35)
    clock_src = p.add_node(NodeInstance(id=new_id("n"), type="source.datetime", x=-200, y=20,
                            props={"strftime_format": "%H:%M:%S"}))
    clock_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=width - 200, y=20, props={
        "value": "", "x": width - 48, "y": 44, "align": "right",
        "font_family": font, "font_size": 14, "bold": True, "color": accent,
    }))
    p.add_edge(clock_src.id, clock_lbl.id, "value")


def _status_led(p: Project, src_id: str, cx: int, cy: int, style: dict, threshold: float = 85.0):
    """LED that turns warn-colour when bound value ≥ threshold (needs logic + led)."""
    if not _has_node("visual.led_dot"):
        return
    led = p.add_node(NodeInstance(
        id=new_id("n"), type="visual.led_dot", z=p.next_z(), x=cx - 10, y=cy - 10,
        props={
            "cx": cx, "cy": cy, "radius": 5,
            "threshold": threshold,
            "color_on": style.get("warn", "#ff6b6b"),
            "color_off": style["track"],
            "glow": True, "opacity": 1.0,
        },
    ))
    # Wire source directly if LED accepts numeric; threshold is on the LED itself
    p.add_edge(src_id, led.id, "value")


def _add_arc_vital(p: Project, source_type: str, label: str, cx: float, cy: float, style: dict,
                   suffix: str = "%", min_v=0, max_v=100, radius: int = 42,
                   options: dict | None = None):
    options = _opts(options)
    src = p.add_node(NodeInstance(id=new_id("n"), type=source_type, x=cx - 280, y=cy))
    if options.get("chrome") and _has_node("visual.ring_track"):
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.ring_track", z=p.next_z(), x=cx - 60, y=cy - 60,
            props={
                "cx": int(cx), "cy": int(cy), "radius": radius + 6, "thickness": 3,
                "start_angle_deg": -90, "sweep_deg": 360,
                "color": style["track"], "opacity": 0.55,
            },
        ))
    gauge = p.add_node(NodeInstance(id=new_id("n"), type="visual.arc_gauge", z=p.next_z(), x=cx - 60, y=cy - 60, props={
        "cx": int(cx), "cy": int(cy), "radius": radius, "thickness": 9,
        "min_value": min_v, "max_value": max_v,
        "color": style["accent"], "track_color": style["track"], "value_suffix": suffix,
        "show_value_text": True, "value_font_size": 16,
    }))
    p.add_edge(src.id, gauge.id, "value")
    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=cx - 40, y=cy + radius + 8, props={
        "value": label, "x": int(cx), "y": int(cy + radius + 18), "align": "center",
        "font_family": style["font"], "font_size": 10, "color": style.get("text_dim", "#9aa2ad"),
    }))
    if options.get("glow") and style.get("flourish") and _has_node("visual.glow_pulse"):
        p.add_node(NodeInstance(id=new_id("n"), type="visual.glow_pulse", z=p.next_z(), x=cx - 60, y=cy - 60, props={
            "cx": int(cx), "cy": int(cy), "radius": radius, "color": style["accent"],
            "pulse_hz": 0.3, "alpha_min": 0.08, "alpha_max": 0.28, "layers": 3,
        }))
    if options.get("leds"):
        _status_led(p, src.id, int(cx + radius + 14), int(cy - radius + 4), style, 85.0)
    return src


def _add_bar_vital(p: Project, source_type: str, label: str, x: float, y: float, style: dict,
                   w: int = 300, options: dict | None = None):
    options = _opts(options)
    src = p.add_node(NodeInstance(id=new_id("n"), type=source_type, x=x - 280, y=y))
    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y, props={
        "value": label, "x": int(x), "y": int(y),
        "font_family": style["font"], "font_size": 12, "bold": True, "color": style["accent"],
    }))
    bar = p.add_node(NodeInstance(id=new_id("n"), type="visual.bar", z=p.next_z(), x=x, y=y + 16, props={
        "x": int(x + 120), "y": int(y - 4), "width": w - 120, "height": 10,
        "style": "segmented", "segment_count": 20,
        "color": style["accent"], "track_color": style["track"],
        "pulse_when_critical": True, "critical_threshold": 90.0,
    }))
    p.add_edge(src.id, bar.id, "value")
    if options.get("leds"):
        _status_led(p, src.id, int(x + w + 16), int(y + 2), style, 85.0)
    return src


def _panel_weather(p: Project, x: float, y: float, style: dict, options: dict | None = None):
    options = _opts(options)
    if options.get("chrome"):
        _panel_bg(p, int(x - 12), int(y - 12), 280, 120, style)
    cat = p.add_node(NodeInstance(id=new_id("n"), type="source.weather_category", x=x - 260, y=y,
                      props={"poll_mode": "daemon", "poll_interval": 1800}))
    cond = p.add_node(NodeInstance(id=new_id("n"), type="source.weather_condition", x=x - 260, y=y + 60,
                       props={"poll_mode": "daemon", "poll_interval": 1800}))
    icon = p.add_node(NodeInstance(id=new_id("n"), type="visual.weather_icon", z=p.next_z(), x=x, y=y,
                       props={"cx": int(x + 30), "cy": int(y + 30), "size": 40, "color": style["accent"]}))
    label = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y + 60, props={
        "value": "placeholder", "x": int(x + 70), "y": int(y + 24),
        "font_family": style["font"], "font_size": 12, "color": "#FFFFFF",
    }))
    p.add_edge(cat.id, icon.id, "category")
    p.add_edge(cond.id, label.id, "value")
    # Temp source is weather_temp_f in the registry (not weather_temp)
    if _has_node("source.weather_temp_f"):
        temp = p.add_node(NodeInstance(id=new_id("n"), type="source.weather_temp_f", x=x - 260, y=y + 120,
                           props={"poll_mode": "daemon", "poll_interval": 1800}))
        temp_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y + 90, props={
            "value": "", "suffix": " °F", "x": int(x + 70), "y": int(y + 48),
            "font_family": style["font"], "font_size": 18, "bold": True, "color": style["accent"],
            "decimals": 0,
        }))
        p.add_edge(temp.id, temp_lbl.id, "value")


def _panel_clock(p: Project, x: float, y: float, style: dict, options: dict | None = None):
    options = _opts(options)
    if options.get("chrome"):
        _panel_bg(p, int(x - 12), int(y - 12), 280, 90, style)
    src = p.add_node(NodeInstance(id=new_id("n"), type="source.datetime", x=x - 260, y=y,
                      props={"strftime_format": "%H:%M"}))
    date_src = p.add_node(NodeInstance(id=new_id("n"), type="source.datetime", x=x - 260, y=y + 40,
                           props={"strftime_format": "%a %d %b"}))
    label = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y, props={
        "value": "placeholder", "x": int(x), "y": int(y + 28),
        "font_family": style["font"], "font_size": 32, "bold": True, "color": style["accent"],
    }))
    date_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y + 40, props={
        "value": "", "x": int(x), "y": int(y + 56),
        "font_family": style["font"], "font_size": 12, "color": style.get("text_dim", "#9aa2ad"),
    }))
    p.add_edge(src.id, label.id, "value")
    p.add_edge(date_src.id, date_lbl.id, "value")
    if options.get("chrome") and _has_node("visual.analog_clock"):
        p.add_node(NodeInstance(
            id=new_id("n"), type="visual.analog_clock", z=p.next_z(),
            x=x + 180, y=y - 10,
            props={
                "cx": int(x + 230), "cy": int(y + 40), "radius": 36,
                "show_seconds": True, "show_numerals": False, "show_digital": False,
                "rim_color": style["accent"], "tick_color": style["accent"],
                "face_color": style.get("panel", "#0a2226"),
                "hour_hand_color": style["accent"], "minute_hand_color": style["accent"],
                "second_hand_color": style.get("warn", "#ffcf5c"),
            },
        ))


def _panel_calendar(p: Project, x: float, y: float, style: dict, options: dict | None = None):
    options = _opts(options)
    if options.get("chrome"):
        _panel_bg(p, int(x - 12), int(y - 12), 300, 260, style)
    if _has_node("visual.wall_calendar"):
        p.add_node(NodeInstance(id=new_id("n"), type="visual.wall_calendar", z=p.next_z(), x=x, y=y, props={
            "x": int(x), "y": int(y), "cell_w": 32, "cell_h": 24,
            "font_family": style["font"],
            "title_color": style["accent"], "today_color": style["accent"],
            "today_fill": style["accent"], "day_color": "#e8eaed",
            "weekday_color": style.get("text_dim", "#9aa2ad"),
            "grid_color": style["track"], "show_grid": True,
        }))
    else:
        p.add_node(NodeInstance(id=new_id("n"), type="visual.text_list", z=p.next_z(), x=x, y=y, props={
            "value": "Today:\n- (bind a Custom Script\n  or edit this list)",
            "x": int(x), "y": int(y), "max_lines": 6,
            "font_family": style["font"], "font_size": 12, "color": "#FFFFFF",
        }))


def _panel_music(p: Project, x: float, y: float, style: dict, options: dict | None = None):
    options = _opts(options)
    if options.get("chrome"):
        _panel_bg(p, int(x - 12), int(y - 12), 360, 100, style)
    title = p.add_node(NodeInstance(id=new_id("n"), type="source.nowplaying_title", x=x - 260, y=y,
                        props={"poll_mode": "execi"}))
    artist = p.add_node(NodeInstance(id=new_id("n"), type="source.nowplaying_artist", x=x - 260, y=y + 60,
                         props={"poll_mode": "execi"}))
    p.add_node(NodeInstance(id=new_id("n"), type="visual.album_art", z=p.next_z(), x=x, y=y, props={
        "x": int(x), "y": int(y), "size": 72,
    }))
    title_label = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y + 80, props={
        "value": "placeholder", "x": int(x + 84), "y": int(y + 28),
        "font_family": style["font"], "font_size": 13, "color": "#FFFFFF",
    }))
    artist_label = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y + 110, props={
        "value": "placeholder", "x": int(x + 84), "y": int(y + 50),
        "font_family": style["font"], "font_size": 11, "color": style.get("text_dim", "#9aa2ad"),
    }))
    p.add_edge(title.id, title_label.id, "value")
    p.add_edge(artist.id, artist_label.id, "value")


def _panel_moon(p: Project, x: float, y: float, style: dict, options: dict | None = None):
    options = _opts(options)
    if options.get("chrome"):
        _panel_bg(p, int(x - 12), int(y - 12), 160, 130, style)
    if _has_node("visual.moon_phase"):
        p.add_node(NodeInstance(id=new_id("n"), type="visual.moon_phase", z=p.next_z(), x=x, y=y, props={
            "cx": int(x + 60), "cy": int(y + 55), "radius": 32,
            "show_labels": True, "show_brackets": False,
            "color": style["accent"], "rim_color": style.get("text_dim", style["accent"]),
            "text_color": style.get("text_dim", "#9aa2ad"), "font_family": style["font"],
        }))
    else:
        p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y, props={
            "value": "MOON", "x": int(x), "y": int(y + 20),
            "font_family": style["font"], "font_size": 14, "color": style["accent"],
        }))


def _sys_block(p: Project, x: float, y: float, style: dict, options: dict | None = None):
    options = _opts(options)
    if options.get("chrome"):
        _panel_bg(p, int(x - 12), int(y - 12), 300, 110, style)
    font, dim = style["font"], style.get("text_dim", "#9aa2ad")
    host = p.add_node(NodeInstance(id=new_id("n"), type="source.hostname", x=x - 260, y=y))
    host_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y, props={
        "value": "", "prefix": "HOST  ", "x": int(x), "y": int(y),
        "font_family": font, "font_size": 11, "color": dim,
    }))
    p.add_edge(host.id, host_lbl.id, "value")
    up = p.add_node(NodeInstance(id=new_id("n"), type="source.uptime", x=x - 260, y=y + 28))
    up_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y + 28, props={
        "value": "", "prefix": "UP    ", "x": int(x), "y": int(y + 28),
        "font_family": font, "font_size": 11, "color": dim,
    }))
    p.add_edge(up.id, up_lbl.id, "value")
    kern = p.add_node(NodeInstance(id=new_id("n"), type="source.kernel", x=x - 260, y=y + 56))
    kern_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y + 56, props={
        "value": "", "prefix": "KERN  ", "x": int(x), "y": int(y + 56),
        "font_family": font, "font_size": 11, "color": dim,
    }))
    p.add_edge(kern.id, kern_lbl.id, "value")
    procs = p.add_node(NodeInstance(id=new_id("n"), type="source.process_count", x=x - 260, y=y + 84))
    procs_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y + 84, props={
        "value": "", "prefix": "PROC  ", "x": int(x), "y": int(y + 84),
        "font_family": font, "font_size": 11, "color": dim, "decimals": 0,
    }))
    p.add_edge(procs.id, procs_lbl.id, "value")


def _net_graph(p: Project, x: float, y: float, w: int, h: int, style: dict,
               label: str = "NETWORK", options: dict | None = None):
    options = _opts(options)
    if not options.get("graphs"):
        return
    if options.get("chrome"):
        _panel_bg(p, int(x - 12), int(y - 28), w + 24, h + 44, style)
    down = p.add_node(NodeInstance(id=new_id("n"), type="source.net_down", x=x - 200, y=y))
    graph = p.add_node(NodeInstance(id=new_id("n"), type="visual.history_graph", z=p.next_z(), x=x, y=y, props={
        "x": int(x), "y": int(y), "width": w, "height": h,
        "color": style["accent"], "track_color": style["track"], "max_value": 2048, "fill": True,
        "history_length": 48,
    }))
    p.add_edge(down.id, graph.id, "value")
    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y - 16, props={
        "value": label, "x": int(x), "y": int(y - 8),
        "font_family": style["font"], "font_size": 9, "color": style.get("text_dim", "#9aa2ad"),
    }))
    # Optional uplink value text
    up = p.add_node(NodeInstance(id=new_id("n"), type="source.net_up", x=x - 200, y=y + 40))
    up_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x + w - 80, y=y - 16, props={
        "value": "", "prefix": "↑ ", "suffix": " KiB/s", "x": int(x + w), "y": int(y - 8),
        "align": "right", "font_family": style["font"], "font_size": 9,
        "color": style.get("text_dim", "#9aa2ad"), "decimals": 0,
    }))
    p.add_edge(up.id, up_lbl.id, "value")


def _battery_block(p: Project, x: float, y: float, style: dict, options: dict | None = None):
    options = _opts(options)
    if options.get("chrome"):
        _panel_bg(p, int(x - 12), int(y - 12), 280, 70, style)
    src = p.add_node(NodeInstance(id=new_id("n"), type="source.battery_percent", x=x - 260, y=y,
                      props={"device": "BAT0"}))
    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y, props={
        "value": "BATTERY", "x": int(x), "y": int(y),
        "font_family": style["font"], "font_size": 11, "bold": True, "color": style["accent"],
    }))
    bar = p.add_node(NodeInstance(id=new_id("n"), type="visual.bar", z=p.next_z(), x=x, y=y + 20, props={
        "x": int(x), "y": int(y + 22), "width": 200, "height": 12,
        "style": "solid", "corner_radius": 3,
        "color": style["accent"], "track_color": style["track"],
        "pulse_when_critical": True, "critical_threshold": 20.0,
    }))
    p.add_edge(src.id, bar.id, "value")
    pct = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x + 210, y=y + 20, props={
        "value": "", "suffix": "%", "x": int(x + 220), "y": int(y + 34),
        "font_family": style["font"], "font_size": 14, "bold": True, "color": style["accent"],
        "decimals": 0,
    }))
    p.add_edge(src.id, pct.id, "value")
    if options.get("leds"):
        _status_led(p, src.id, int(x + 260), int(y + 30), style, 15.0)


def _disk_block(p: Project, x: float, y: float, style: dict, options: dict | None = None):
    options = _opts(options)
    _add_bar_vital(p, "source.disk_percent", "DISK", x, y, style, w=320, options=options)


def _default_panels(panels: list) -> list:
    return panels or list(DEFAULT_PANELS)


# ---------------------------------------------------------------------------
# Category layouts
# ---------------------------------------------------------------------------

def _build_minimal_layout(p: Project, style: dict, panels: list, width: int, height: int,
                          options: dict | None = None) -> None:
    options = _opts(options)
    if options.get("brackets"):
        _outer_brackets(p, width, height, style, arm=16)
    _header(p, "SYSTEM", "minimal monitor", style, width)

    x, y = 48, 100
    if options.get("chrome"):
        h = 56 * sum(1 for k in ("CPU", "RAM", "GPU", "Disk") if k in panels) + 40
        _panel_bg(p, x - 16, y - 24, min(480, width // 2 - 40), max(h, 80), style)

    if "CPU" in panels:
        _add_bar_vital(p, "source.cpu_percent", "CPU", x, y, style, w=min(420, width // 2 - 80), options=options); y += 56
    if "RAM" in panels:
        _add_bar_vital(p, "source.ram_percent", "RAM", x, y, style, w=min(420, width // 2 - 80), options=options); y += 56
    if "GPU" in panels:
        _add_bar_vital(p, "source.gpu_util", "GPU", x, y, style, w=min(420, width // 2 - 80), options=options); y += 56
    if "Disk" in panels:
        _disk_block(p, x, y, style, options); y += 56
    if "Battery" in panels:
        _battery_block(p, x, y + 10, style, options); y += 90
    if "System" in panels:
        _sys_block(p, x, y + 20, style, options)

    rx = width - 360
    if "Clock" in panels:
        _panel_clock(p, rx, 100, style, options)
    if "Weather" in panels:
        _panel_weather(p, rx, 220, style, options)
    if "Moon" in panels:
        _panel_moon(p, rx, 370, style, options)
    if "Calendar" in panels:
        _panel_calendar(p, rx, 520, style, options)
    if "Music" in panels:
        _panel_music(p, 48, height - 160, style, options)
    if "Network" in panels:
        _net_graph(p, width // 2 - 200, height - 150, 400, 90, style, "NET", options)


def _build_gaming_layout(p: Project, style: dict, panels: list, width: int, height: int,
                         options: dict | None = None) -> None:
    options = _opts(options)
    if options.get("brackets"):
        _outer_brackets(p, width, height, style, arm=32)
    _header(p, "PERFORMANCE", "gaming overlay", style, width)

    gauges = []
    if "CPU" in panels:
        gauges.append(("source.cpu_percent", "CPU", "%"))
    if "GPU" in panels:
        gauges.append(("source.gpu_util", "GPU", "%"))
    if "RAM" in panels:
        gauges.append(("source.ram_percent", "RAM", "%"))
    if "Disk" in panels:
        gauges.append(("source.disk_percent", "DISK", "%"))
    n = max(1, len(gauges))
    span = min(width - 120, n * 170)
    start = (width - span) / 2 + 80
    for i, (stype, label, suf) in enumerate(gauges):
        _add_arc_vital(p, stype, label, start + i * (span / n), 220, style, suffix=suf, radius=48, options=options)

    if _has_node("visual.reactor_gauge") and gauges:
        src = p.add_node(NodeInstance(id=new_id("n"), type=gauges[0][0], x=-200, y=400))
        rg = p.add_node(NodeInstance(id=new_id("n"), type="visual.reactor_gauge", z=p.next_z(), x=width // 2 - 100, y=400, props={
            "cx": width // 2, "cy": height // 2 + 40, "radius": 70,
            "color": style["accent"], "dim_color": style["track"], "accent_color": style.get("warn", "#ff4d6d"),
            "label": "LOAD", "font_family": style["font"], "value_font_size": 36,
            "pulse_when_critical": True, "critical_threshold": 90.0,
        }))
        p.add_edge(src.id, rg.id, "value")

    if "Battery" in panels:
        _battery_block(p, 48, 360, style, options)
    if "Weather" in panels:
        _panel_weather(p, width - 300, 100, style, options)
    if "System" in panels:
        _sys_block(p, width - 300, 280, style, options)
    if "Music" in panels:
        _panel_music(p, 48, height - 180, style, options)
    if "Network" in panels:
        _net_graph(p, width // 2 - 220, height - 140, 440, 90, style, "NETWORK", options)


def _build_rpg_layout(p: Project, style: dict, panels: list, width: int, height: int,
                      options: dict | None = None) -> None:
    options = _opts(options)
    if options.get("brackets"):
        _outer_brackets(p, width, height, style, arm=20)
    _header(p, "STATUS", "character sheet", style, width)

    x, y = 60, 110
    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y - 30, props={
        "value": "VITALS", "x": int(x), "y": int(y - 24),
        "font_family": style["font"], "font_size": 12, "bold": True, "color": style["accent"],
    }))
    if options.get("chrome"):
        _panel_bg(p, x - 16, y - 40, 420, 240, style)
    if "CPU" in panels:
        _add_bar_vital(p, "source.cpu_percent", "STRENGTH", x, y, style, w=360, options=options); y += 52
    if "RAM" in panels:
        _add_bar_vital(p, "source.ram_percent", "STAMINA", x, y, style, w=360, options=options); y += 52
    if "GPU" in panels:
        _add_bar_vital(p, "source.gpu_util", "FOCUS", x, y, style, w=360, options=options); y += 52
    if "Disk" in panels:
        _add_bar_vital(p, "source.disk_percent", "INVENTORY", x, y, style, w=360, options=options); y += 52
    if "Battery" in panels:
        _battery_block(p, x, y + 10, style, options)

    rx = width - 400
    if "Moon" in panels:
        _panel_moon(p, rx, 110, style, options)
    if "Weather" in panels:
        _panel_weather(p, rx, 280, style, options)
    if "Calendar" in panels:
        _panel_calendar(p, rx, 430, style, options)
    if "Music" in panels:
        _panel_music(p, 60, height - 170, style, options)
    if "System" in panels:
        _sys_block(p, 60, height - 300, style, options)
    if "Network" in panels:
        _net_graph(p, width // 2 - 180, height - 140, 360, 80, style, "WORLD LINK", options)


def _build_scifi_layout(p: Project, style: dict, panels: list, width: int, height: int,
                        options: dict | None = None) -> None:
    options = _opts(options)
    if options.get("brackets"):
        _outer_brackets(p, width, height, style, arm=28)
    _header(p, "SYSTEM INTERFACE", "sci-fi telemetry", style, width)

    ly = 130
    if "CPU" in panels:
        _add_arc_vital(p, "source.cpu_percent", "CPU", 140, ly, style, radius=40, options=options); ly += 130
    if "GPU" in panels:
        _add_arc_vital(p, "source.gpu_util", "GPU", 140, ly, style, radius=40, options=options); ly += 130
    if "RAM" in panels:
        _add_arc_vital(p, "source.ram_percent", "MEM", 140, ly, style, radius=40, options=options); ly += 130
    if "Disk" in panels:
        _add_arc_vital(p, "source.disk_percent", "DSK", 140, ly, style, radius=36, options=options)

    cx, cy = width // 2, height // 2 - 20
    if _has_node("visual.reactor_gauge"):
        src = p.add_node(NodeInstance(id=new_id("n"), type="source.cpu_percent", x=-200, y=cy))
        rg = p.add_node(NodeInstance(id=new_id("n"), type="visual.reactor_gauge", z=p.next_z(), x=cx - 100, y=cy - 100, props={
            "cx": cx, "cy": cy, "radius": 88,
            "color": style["accent"], "dim_color": style["track"],
            "accent_color": style.get("warn", "#ffcf5c"),
            "label": "REACTOR OUTPUT %", "font_family": style["font"],
            "pulse_when_critical": True, "critical_threshold": 90.0,
        }))
        p.add_edge(src.id, rg.id, "value")
    if _has_node("visual.radar_sweep"):
        p.add_node(NodeInstance(id=new_id("n"), type="visual.radar_sweep", z=p.next_z(), x=cx - 70, y=cy + 120, props={
            "cx": cx, "cy": cy + 200, "radius": 64,
            "color": style["accent"], "dim_color": style["track"],
            "blip_color": style.get("warn", "#ffcf5c"),
        }))
    if options.get("chrome") and _has_node("visual.crosshair"):
        p.add_node(NodeInstance(id=new_id("n"), type="visual.crosshair", z=p.next_z(), x=cx, y=cy, props={
            "cx": cx, "cy": cy, "size": 18, "gap": 6, "line_width": 1.0,
            "color": style["accent"], "opacity": 0.35,
        }))

    rx = width - 320
    if "System" in panels:
        _sys_block(p, rx, 120, style, options)
    ry = 260
    if "Moon" in panels:
        _panel_moon(p, rx, ry, style, options); ry += 140
    if "Weather" in panels:
        _panel_weather(p, rx, ry, style, options); ry += 140
    if "Battery" in panels:
        _battery_block(p, rx, ry, style, options)
    if "Music" in panels:
        _panel_music(p, 48, height - 170, style, options)
    if "Network" in panels:
        _net_graph(p, 48, height - 130, 360, 85, style, "NET THROUGHPUT", options)


def _build_cyberpunk_layout(p: Project, style: dict, panels: list, width: int, height: int,
                            options: dict | None = None) -> None:
    options = _opts(options)
    if options.get("brackets"):
        _outer_brackets(p, width, height, style, arm=18)
    _header(p, "NIGHT CITY", "cyberdeck telemetry", style, width)

    x, y = 50, 110
    if options.get("chrome"):
        _panel_bg(p, x - 16, y - 24, 440, 220, style)
    if "CPU" in panels:
        _add_bar_vital(p, "source.cpu_percent", "CPU CORE", x, y, style, w=380, options=options); y += 48
    if "GPU" in panels:
        _add_bar_vital(p, "source.gpu_util", "GPU CORE", x, y, style, w=380, options=options); y += 48
    if "RAM" in panels:
        _add_bar_vital(p, "source.ram_percent", "MEMORY", x, y, style, w=380, options=options); y += 48
    if "Disk" in panels:
        _add_bar_vital(p, "source.disk_percent", "STORAGE", x, y, style, w=380, options=options); y += 48
    if "Battery" in panels:
        _battery_block(p, x, y + 8, style, options)

    if options.get("glow") and style.get("flourish") and _has_node("visual.spiral"):
        p.add_node(NodeInstance(id=new_id("n"), type="visual.spiral", z=p.next_z(), x=width // 2 - 80, y=height // 2 - 80, props={
            "cx": width // 2, "cy": height // 2, "radius_end": 70, "radius_start": 10,
            "color": style["accent"], "rotation_speed_dps": 40, "dash_count": 24, "line_width": 1.5,
        }))

    rx = width - 340
    if "Weather" in panels:
        _panel_weather(p, rx, 110, style, options)
    if "Music" in panels:
        _panel_music(p, rx, 280, style, options)
    if "Moon" in panels:
        _panel_moon(p, rx, 430, style, options)
    if "System" in panels:
        _sys_block(p, rx, 580, style, options)
    if "Network" in panels:
        _net_graph(p, 50, height - 130, 500, 90, style, "UPLINK", options)


def _build_terminal_layout(p: Project, style: dict, panels: list, width: int, height: int,
                           options: dict | None = None) -> None:
    options = _opts(options)
    # Terminal stays sparse, no glow/brackets by default feel, but respect toggles
    _header(p, "$ top", "terminal session", style, width)
    font, accent = style["font"], style["accent"]

    y = 100
    if options.get("chrome"):
        _panel_bg(p, 32, 80, min(560, width - 80), 200, style)

    for key, stype, prefix in (
        ("CPU", "source.cpu_percent", "cpu  "),
        ("RAM", "source.ram_percent", "mem  "),
        ("GPU", "source.gpu_util", "gpu  "),
        ("Disk", "source.disk_percent", "disk "),
        ("Battery", "source.battery_percent", "bat  "),
    ):
        if key not in panels:
            continue
        src = p.add_node(NodeInstance(id=new_id("n"), type=stype, x=-200, y=y))
        lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=40, y=y, props={
            "value": "", "prefix": prefix, "suffix": "%", "x": 48, "y": y,
            "font_family": font, "font_size": 14, "color": accent, "decimals": 0,
        }))
        p.add_edge(src.id, lbl.id, "value")
        if options.get("leds"):
            _status_led(p, src.id, 200, int(y - 4), style, 85.0 if key != "Battery" else 15.0)
        y += 28

    if "System" in panels:
        _sys_block(p, 48, y + 24, style, options)
        y += 140
    if "CPU" in panels:
        _add_bar_vital(p, "source.cpu_percent", "cpu_bar", 48, y + 20, style, w=min(500, width - 100), options=options)

    if "Weather" in panels:
        _panel_weather(p, width - 320, 100, style, options)
    if "Calendar" in panels:
        _panel_calendar(p, width - 320, 280, style, options)
    if "Clock" in panels:
        _panel_clock(p, width - 320, 560, style, options)
    if "Network" in panels:
        _net_graph(p, 48, height - 140, min(560, width - 100), 100, style, "iftop", options)


def _build_fantasy_layout(p: Project, style: dict, panels: list, width: int, height: int,
                          options: dict | None = None) -> None:
    options = _opts(options)
    if options.get("brackets"):
        _outer_brackets(p, width, height, style, arm=22)
    _header(p, "GRIMOIRE", "arcane monitor", style, width)

    if "Moon" in panels or True:
        if _has_node("visual.moon_phase"):
            p.add_node(NodeInstance(id=new_id("n"), type="visual.moon_phase", z=p.next_z(), x=width // 2 - 80, y=height // 2 - 120, props={
                "cx": width // 2, "cy": height // 2 - 40, "radius": 48,
                "show_labels": True, "show_brackets": True, "bracket_pad": 16,
                "color": style["accent"], "rim_color": style["track"],
                "text_color": style.get("text_dim", "#d4c8b0"), "font_family": style["font"],
            }))

    x = 60
    if "CPU" in panels:
        _add_arc_vital(p, "source.cpu_percent", "ESSENCE", x + 60, 180, style, radius=36, options=options)
    if "RAM" in panels:
        _add_arc_vital(p, "source.ram_percent", "SPIRIT", x + 60, 340, style, radius=36, options=options)
    if "GPU" in panels:
        _add_arc_vital(p, "source.gpu_util", "FLAME", x + 60, 500, style, radius=36, options=options)
    if "Disk" in panels:
        _add_arc_vital(p, "source.disk_percent", "VAULT", x + 60, 660, style, radius=32, options=options)

    rx = width - 320
    if "Weather" in panels:
        _panel_weather(p, rx, 140, style, options)
    if "Calendar" in panels:
        _panel_calendar(p, rx, 300, style, options)
    if "Music" in panels:
        _panel_music(p, rx, height - 200, style, options)
    if "System" in panels:
        _sys_block(p, rx, height - 340, style, options)
    if "Battery" in panels:
        _battery_block(p, 60, height - 160, style, options)
    if "Network" in panels:
        _net_graph(p, width // 2 - 160, height - 130, 320, 80, style, "LEY LINE", options)


def _batman_vital_row(
    p: Project,
    *,
    usage_type: str,
    temp_type: str | None,
    label: str,
    x: float,
    y: float,
    style: dict,
    bar_w: int = 220,
    options: dict | None = None,
    usage_daemon: bool = False,
) -> tuple:
    """One Batcomputer-style vital: LABEL + segmented bar + optional temp text.
    Returns (usage_src, temp_src_or_None) so callers can wire threat logic."""
    options = _opts(options)
    font = style["font"]
    accent = style["accent"]
    dim = style.get("text_dim", "#4fb8d6")
    warn = style.get("warn", "#ff3b3b")

    usage_props = {}
    if usage_daemon or usage_type.startswith("source.gpu") or usage_type.startswith("source.cpu_temp"):
        usage_props = {"poll_mode": "daemon", "poll_interval": 3}
    usage = p.add_node(NodeInstance(id=new_id("n"), type=usage_type, x=x - 320, y=y, props=usage_props))

    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y, props={
        "value": label, "x": int(x), "y": int(y),
        "font_family": font, "font_size": 13, "bold": True, "color": accent,
    }))
    bar = p.add_node(NodeInstance(id=new_id("n"), type="visual.bar", z=p.next_z(), x=x + 100, y=y + 4, props={
        "x": int(x + 110), "y": int(y - 2), "width": bar_w, "height": 12,
        "style": "segmented", "segment_count": 22,
        "color": accent, "track_color": style["track"],
        "pulse_when_critical": True, "critical_threshold": 90.0,
    }))
    p.add_edge(usage.id, bar.id, "value")

    temp_src = None
    if temp_type and _has_node(temp_type):
        temp_props = {"poll_mode": "daemon", "poll_interval": 3}
        temp_src = p.add_node(NodeInstance(
            id=new_id("n"), type=temp_type, x=x - 320, y=y + 36, props=temp_props,
        ))
        temp_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=x, y=y + 28, props={
            "value": "", "prefix": "TEMP: ", "suffix": " °C", "decimals": 0,
            "x": int(x), "y": int(y + 28),
            "font_family": font, "font_size": 11, "color": dim,
        }))
        p.add_edge(temp_src.id, temp_lbl.id, "value")
        if options.get("leds"):
            _status_led(p, temp_src.id, int(x + 110 + bar_w + 18), int(y + 26), style, 80.0)

    if options.get("leds"):
        _status_led(p, usage.id, int(x + 110 + bar_w + 18), int(y + 2), style, 85.0)
    return usage, temp_src


def _build_batman_layout(p: Project, style: dict, panels: list, width: int, height: int,
                         options: dict | None = None) -> None:
    """Near-1:1 Batcomputer layout using Studio sources / visuals / logic.

    Unlike a legacy import (one opaque Custom Lua), every vital here is a
    real node: edit a bar, rewire a temp, change a threshold, and the HUD
    updates. Decorative-only pieces (case-file flip, exact bat ATOP tint)
    stay as optional Custom Lua so the graph remains the source of truth
    for CPU / GPU / RAM / network / weather.
    """
    options = _opts(options)
    accent = style["accent"]
    dim = style.get("text_dim", "#4fb8d6")
    warn = style.get("warn", "#ff3b3b")
    font = style["font"]
    track = style["track"]

    if options.get("brackets"):
        _outer_brackets(p, width, height, style, pad=6, arm=28)
    _header(p, "ARKHAMOS", "BATCOMPUTER INTERFACE  v1.0", style, width)

    # ---- left column: vitals (matches batcomputer.lua vital_block layout) ----
    vx, vy = 40, 100
    if options.get("chrome"):
        _panel_bg(p, vx - 12, vy - 24, 400, 380, style)

    threat_inputs = []  # sources we fold into a simple threat gate

    if "CPU" in panels:
        cpu_u, cpu_t = _batman_vital_row(
            p, usage_type="source.cpu_percent", temp_type="source.cpu_temp",
            label="CPU", x=vx, y=vy, style=style, options=options,
        )
        threat_inputs.append(cpu_u)
        if cpu_t:
            threat_inputs.append(cpu_t)
        # Clock / cores as secondary facts (native)
        if _has_node("source.cpu_freq"):
            freq = p.add_node(NodeInstance(id=new_id("n"), type="source.cpu_freq", x=vx - 320, y=vy + 48))
            freq_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=vx, y=vy + 48, props={
                "value": "", "prefix": "CLOCK: ", "suffix": " MHz", "decimals": 0,
                "x": int(vx + 160), "y": int(vy + 28),
                "font_family": font, "font_size": 11, "color": dim,
            }))
            p.add_edge(freq.id, freq_lbl.id, "value")
        vy += 78

    if "GPU" in panels and _has_node("source.gpu_util"):
        gpu_u, gpu_t = _batman_vital_row(
            p, usage_type="source.gpu_util", temp_type="source.gpu_temp",
            label="GPU", x=vx, y=vy, style=style, options=options, usage_daemon=True,
        )
        threat_inputs.append(gpu_u)
        if gpu_t:
            threat_inputs.append(gpu_t)
        if _has_node("source.gpu_vram_used") and _has_node("source.gpu_vram_total"):
            vu = p.add_node(NodeInstance(
                id=new_id("n"), type="source.gpu_vram_used", x=vx - 320, y=vy + 48,
                props={"poll_mode": "daemon", "poll_interval": 3},
            ))
            vt = p.add_node(NodeInstance(
                id=new_id("n"), type="source.gpu_vram_total", x=vx - 320, y=vy + 72,
                props={"poll_mode": "daemon", "poll_interval": 3},
            ))
            # Show used only as a compact fact line (full ratio needs map_range math)
            vu_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=vx, y=vy + 48, props={
                "value": "", "prefix": "VRAM used: ", "suffix": " MB", "decimals": 0,
                "x": int(vx + 160), "y": int(vy + 28),
                "font_family": font, "font_size": 11, "color": dim,
            }))
            p.add_edge(vu.id, vu_lbl.id, "value")
        vy += 78

    if "RAM" in panels:
        ram_u, _ = _batman_vital_row(
            p, usage_type="source.ram_percent", temp_type=None,
            label="MEMORY", x=vx, y=vy, style=style, options=options,
        )
        threat_inputs.append(ram_u)
        if _has_node("source.ram_used"):
            used = p.add_node(NodeInstance(id=new_id("n"), type="source.ram_used", x=vx - 320, y=vy + 40))
            used_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=vx, y=vy + 40, props={
                "value": "", "prefix": "USED: ", "x": int(vx + 160), "y": int(vy + 28),
                "font_family": font, "font_size": 11, "color": dim,
            }))
            p.add_edge(used.id, used_lbl.id, "value")
        vy += 70

    if "Disk" in panels:
        disk_u, disk_t = _batman_vital_row(
            p, usage_type="source.disk_percent", temp_type="source.disk_temp",
            label="DISK", x=vx, y=vy, style=style, options=options,
        )
        threat_inputs.append(disk_u)
        if disk_t:
            threat_inputs.append(disk_t)
        vy += 78

    if "Battery" in panels:
        _battery_block(p, vx, vy, style, options)
        vy += 70

    # ---- center: threat level driven by real logic nodes ----
    cx, cy = width // 2, height // 2 - 40

    # Fold first two high-signal sources into a simple elevated/critical gate.
    # logic.threshold → 1 when value ≥ threshold; boolean_or combines them.
    threat_src = None
    if threat_inputs and _has_node("logic.threshold"):
        gates = []
        for src in threat_inputs[:4]:
            g = p.add_node(NodeInstance(
                id=new_id("n"), type="logic.threshold", x=cx - 400, y=cy - 80 + 30 * len(gates),
                props={"comparison": ">=", "threshold": 85.0},
            ))
            p.add_edge(src.id, g.id, "value")
            gates.append(g)
        combined = gates[0]
        if len(gates) > 1 and _has_node("logic.boolean_or"):
            for extra in gates[1:]:
                nxt = p.add_node(NodeInstance(
                    id=new_id("n"), type="logic.boolean_or",
                    x=cx - 400, y=cy + 40 + 20 * len(gates),
                ))
                p.add_edge(combined.id, nxt.id, "input_a")
                p.add_edge(extra.id, nxt.id, "input_b")
                combined = nxt
        threat_src = combined

    if options.get("glow") and _has_node("visual.glow_pulse"):
        glow = p.add_node(NodeInstance(id=new_id("n"), type="visual.glow_pulse", z=p.next_z(), x=cx - 90, y=cy - 90, props={
            "cx": cx, "cy": cy, "radius": 95, "layers": 5, "color": accent, "pulse_hz": 0.45,
            "alpha_min": 0.12, "alpha_max": 0.42, "trigger_threshold": 0.5, "trigger_mode": "above",
        }))
        if threat_src:
            p.add_edge(threat_src.id, glow.id, "trigger")

    if options.get("chrome") and _has_node("visual.ring_track"):
        for i, rad in enumerate((110, 130, 150)):
            p.add_node(NodeInstance(id=new_id("n"), type="visual.ring_track", z=p.next_z(), x=cx - rad, y=cy - rad, props={
                "cx": cx, "cy": cy, "radius": rad, "thickness": 1,
                "start_angle_deg": -90, "sweep_deg": 260,
                "color": track, "opacity": 0.35 + i * 0.05,
            }))

    if options.get("chrome") and _has_node("visual.crosshair"):
        p.add_node(NodeInstance(id=new_id("n"), type="visual.crosshair", z=p.next_z(), x=cx, y=cy, props={
            "cx": cx, "cy": cy, "size": 28, "gap": 8, "line_width": 1.5,
            "color": accent, "opacity": 0.45,
        }))

    # Image slot for bat.png (user drops asset on the node after create)
    if _has_node("visual.image_icon"):
        p.add_node(NodeInstance(id=new_id("n"), type="visual.image_icon", z=p.next_z(), x=cx - 60, y=cy - 60, props={
            "x": cx - 60, "y": cy - 60, "size": 120, "opacity": 0.95, "path": "",
        }))

    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=cx - 80, y=cy + 120, props={
        "value": "THREAT LEVEL", "x": cx, "y": cy + 120, "align": "center",
        "font_family": font, "font_size": 10, "color": dim,
    }))
    threat_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=cx - 80, y=cy + 150, props={
        "value": "NOMINAL", "x": cx, "y": cy + 148, "align": "center",
        "font_family": font, "font_size": 22, "bold": True, "color": accent,
    }))
    # When elevated, flip label via conditional → string is still static here;
    # LED + glow already signal warn. Optional Custom Lua can tint bat.png.
    if threat_src and _has_node("visual.led_dot"):
        led = p.add_node(NodeInstance(id=new_id("n"), type="visual.led_dot", z=p.next_z(), x=cx + 90, y=cy + 140, props={
            "cx": cx + 100, "cy": cy + 142, "radius": 7,
            "threshold": 0.5, "color_on": warn, "color_off": track, "glow": True,
        }))
        p.add_edge(threat_src.id, led.id, "value")

    p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=cx - 120, y=cy + 178, props={
        "value": "Set Image path → bat.png  ·  glow follows threat gate", "x": cx, "y": cy + 178,
        "align": "center", "font_family": font, "font_size": 9, "color": "#2a5a6a",
    }))

    # Optional: small Custom Lua that reads threat on in1 and draws a simple
    # bat-signal silhouette placeholder (user can paste full batcomputer draw).
    if _has_node("visual.custom_lua"):
        bat_lua = p.add_node(NodeInstance(
            id=new_id("n"), type="visual.custom_lua", z=p.next_z(),
            x=cx - 40, y=cy - 200,
            label="Bat hologram (Custom Lua)",
            props={
                "x": 0, "y": 0,
                "code": (
                    "-- in1 = threat gate (0/1) from logic nodes above\n"
                    "local threat = tonumber(in1) or 0\n"
                    "local col = threat >= 0.5 and {1.0, 0.23, 0.23} or {0.25, 0.84, 1.0}\n"
                    "local pulse = (math.sin(wall_clock() * 2) + 1) / 2\n"
                    "local a = 0.55 + pulse * 0.25\n"
                    f"local cx, cy = {cx}, {cy}\n"
                    "cairo_set_source_rgba(cr, col[1], col[2], col[3], a * 0.15)\n"
                    "cairo_arc(cr, cx, cy, 88, 0, 2 * math.pi); cairo_fill(cr)\n"
                    "cairo_set_source_rgba(cr, col[1], col[2], col[3], a)\n"
                    "cairo_set_line_width(cr, 2)\n"
                    "cairo_arc(cr, cx, cy, 70, 0, 2 * math.pi); cairo_stroke(cr)\n"
                    "-- Replace this block with full bat.png ATOP tint from batcomputer.lua\n"
                    "-- after dropping bat.png on the Image node above.\n"
                ),
            },
        ))
        if threat_src:
            p.add_edge(threat_src.id, bat_lua.id, "in1")

    # ---- right column: diagnostics / moon / weather / calendar ----
    rx, ry = width - 380, 100
    if "System" in panels:
        if options.get("chrome"):
            _panel_bg(p, rx - 8, ry - 16, 340, 150, style)
        _sys_block(p, rx + 16, ry, style, options)
        # Extra net line in diagnostics style
        if _has_node("source.net_down"):
            nd = p.add_node(NodeInstance(id=new_id("n"), type="source.net_down", x=rx - 280, y=ry + 100))
            nd_lbl = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=rx + 16, y=ry + 100, props={
                "value": "", "prefix": "NET ↓ ", "suffix": " KB/s", "decimals": 0,
                "x": int(rx + 16), "y": int(ry + 112),
                "font_family": font, "font_size": 11, "color": dim,
            }))
            p.add_edge(nd.id, nd_lbl.id, "value")
        ry += 160

    if "Moon" in panels:
        _panel_moon(p, rx + 16, ry, style, options)
        ry += 140
    if "Weather" in panels:
        _panel_weather(p, rx + 16, ry, style, options)
        ry += 140
    if "Calendar" in panels:
        _panel_calendar(p, rx + 16, ry, style, options)

    # ---- bottom: network + thermal history (batcomputer dual graphs) ----
    hist_y = height - 150
    if "Network" in panels:
        _net_graph(p, 40, hist_y, 380, 90, style, "NETWORK THROUGHPUT  (cyan=down amber=up)", options)

    if options.get("graphs") and ("CPU" in panels or "GPU" in panels) and _has_node("visual.multi_line_graph"):
        # Thermal trend: CPU temp + GPU temp on one multi-series graph
        ml = p.add_node(NodeInstance(
            id=new_id("n"), type="visual.multi_line_graph", z=p.next_z(),
            x=width - 420, y=hist_y,
            props={
                "x": width - 420, "y": hist_y, "width": 380, "height": 90,
                "min_value": 20, "max_value": 100, "history_length": 48,
                "color_a": accent, "color_b": style.get("warn", "#ffcf5c"),
                "color_c": track, "line_width": 1.6, "track_color": track,
            },
        ))
        # Re-find temp sources if we created them; otherwise add dedicated ones
        if "CPU" in panels and _has_node("source.cpu_temp"):
            ct = p.add_node(NodeInstance(
                id=new_id("n"), type="source.cpu_temp", x=-280, y=hist_y,
                props={"poll_mode": "daemon", "poll_interval": 3},
            ))
            p.add_edge(ct.id, ml.id, "value_a")
        if "GPU" in panels and _has_node("source.gpu_temp"):
            gt = p.add_node(NodeInstance(
                id=new_id("n"), type="source.gpu_temp", x=-280, y=hist_y + 40,
                props={"poll_mode": "daemon", "poll_interval": 3},
            ))
            p.add_edge(gt.id, ml.id, "value_b")
        p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=p.next_z(), x=width - 420, y=hist_y - 16, props={
            "value": "THERMAL TREND  (cyan=CPU amber=GPU)", "x": width - 420, "y": hist_y - 8,
            "font_family": font, "font_size": 9, "color": dim,
        }))

    if "Music" in panels:
        _panel_music(p, 40, height - 280, style, options)


LAYOUT_BUILDERS = {
    "minimal": _build_minimal_layout,
    "gaming": _build_gaming_layout,
    "rpg": _build_rpg_layout,
    "scifi": _build_scifi_layout,
    "cyberpunk": _build_cyberpunk_layout,
    "terminal": _build_terminal_layout,
    "fantasy": _build_fantasy_layout,
    "batman": _build_batman_layout,
}


def build_wizard_project(
    name: str,
    category: str,
    resolution: str,
    panels: list,
    options: dict | None = None,
    complexity: str = "Full",
) -> Project:
    style = CATEGORY_STYLES.get(category, CATEGORY_STYLES["Minimal"])
    width, height = RESOLUTIONS.get(resolution, (1920, 1080))
    layout_key = style.get("layout", "minimal")
    builder = LAYOUT_BUILDERS.get(layout_key, _build_minimal_layout)
    # Tier defaults first, then checkbox overrides (preserves original _opts behaviour)
    options = merge_options_for_tier(complexity, options)
    options = _opts(options)

    p = Project(
        name=name or f"{category} HUD",
        description=(
            f"Generated by the Theme Wizard: {category}, {resolution}, {complexity}. "
            f"Full-canvas starter with selected panels "
            f"({', '.join(panels) if panels else 'defaults'}). "
            f"Edit nodes, swap colours, attach images/scripts as needed."
        ),
        canvas=CanvasSettings(
            width=width, height=height, fps=30, stats_hz=2.0,
            alignment="top_left", gap_x=0, gap_y=0,
        ),
    )
    p.ensure_canvas_node()
    panels = _default_panels(list(panels))
    builder(p, style, panels, width, height, options)
    # v1.0.6: Source→Logic→Visual demo + Showcase density (no-op if nodes missing)
    if complexity in ("Full", "Showcase"):
        ensure_logic_demo_edge(p, style)
    if complexity == "Showcase":
        add_showcase_extras(p, style, width, height, options)
    return p


class ThemeWizardDialog(QDialog):
    def __init__(self, parent=None, *, startup_mode: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Theme Wizard" if not startup_mode else "Welcome Create a Theme")
        self.resize(520, 680)
        self.result_project: Project | None = None
        self.startup_mode = startup_mode
        self.skip_on_future_launches = False

        root = QVBoxLayout(self)
        if startup_mode:
            welcome = QLabel(
                "Welcome to Conky Studio. Pick a style and a few panels to generate a starter HUD, "
                "or skip and open a blank canvas. You can always open this again via Project → New HUD…"
            )
            welcome.setWordWrap(True)
            welcome.setProperty("role", "caption")
            root.addWidget(welcome)

        heading = QLabel("Create Theme")
        heading.setProperty("role", "heading")
        root.addWidget(heading)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        layout = QVBoxLayout(body)

        cat_box = QGroupBox("Category")
        cat_layout = QGridLayout()
        cat_box.setLayout(cat_layout)
        self.category_group = QButtonGroup(self)
        for i, cat in enumerate(CATEGORY_ORDER):
            radio = QRadioButton(cat)
            if i == 0:
                radio.setChecked(True)
            self.category_group.addButton(radio)
            cat_layout.addWidget(radio, i // 2, i % 2)
        layout.addWidget(cat_box)

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Resolution"))
        self.res_combo = QComboBox()
        self.res_combo.addItems(list(RESOLUTIONS.keys()))
        res_row.addWidget(self.res_combo, 1)
        layout.addLayout(res_row)

        panel_box = QGroupBox("Panels")
        panel_layout = QGridLayout()
        panel_box.setLayout(panel_layout)
        self.panel_checks = {}
        for i, panel_name in enumerate(PANEL_ORDER):
            cb = QCheckBox(panel_name)
            cb.setChecked(panel_name in DEFAULT_PANELS)
            self.panel_checks[panel_name] = cb
            panel_layout.addWidget(cb, i // 2, i % 2)
        layout.addWidget(panel_box)

        opt_box = QGroupBox("Extras")
        opt_layout = QGridLayout()
        opt_box.setLayout(opt_layout)
        self.option_checks = {}
        for i, (key, label) in enumerate(OPTION_ORDER):
            cb = QCheckBox(label)
            cb.setChecked(DEFAULT_OPTIONS.get(key, True))
            self.option_checks[key] = cb
            opt_layout.addWidget(cb, i // 2, i % 2)
        layout.addWidget(opt_box)

        tier_box = QGroupBox("Complexity")
        tier_layout = QHBoxLayout()
        tier_box.setLayout(tier_layout)
        self.tier_group = QButtonGroup(self)
        for name in ("Simple", "Full", "Showcase"):
            radio = QRadioButton(name)
            if name == "Full":
                radio.setChecked(True)
            self.tier_group.addButton(radio)
            tier_layout.addWidget(radio)
        layout.addWidget(tier_box)
        self.tier_group.buttonClicked.connect(self._on_tier_changed)
        self._on_tier_changed(self.tier_group.checkedButton())

        note = QLabel(
            "Every category builds a full-resolution dashboard. "
            "Panels: system vitals, weather, music, calendar, battery, network graphs. "
            "Extras: rectangle chrome, threshold LEDs, history graphs, corner brackets, glow. "
            "Complexity: Simple (sparse), Full (logic demo chain), Showcase (core strip, top table, orbits). "
            "Missing optional node types are skipped automatically. "
            "Calendar uses Wall Calendar when available; Music needs playerctl. "
            "Attach images (e.g. bat.png) on Image nodes after create."
        )
        note.setProperty("role", "caption")
        note.setWordWrap(True)
        layout.addWidget(note)

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        if startup_mode:
            self.dont_show_cb = QCheckBox("Do not show this wizard on startup again")
            root.addWidget(self.dont_show_cb)
        else:
            self.dont_show_cb = None

        btn_row = QHBoxLayout()
        if startup_mode:
            skip_btn = QPushButton("Skip — blank canvas")
            skip_btn.clicked.connect(self._on_skip)
            btn_row.addWidget(skip_btn)
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Cancel" if not startup_mode else "Close")
        cancel_btn.clicked.connect(self._on_skip if startup_mode else self.reject)
        btn_row.addWidget(cancel_btn)
        create_btn = QPushButton("Create")
        create_btn.setObjectName("primary")
        create_btn.clicked.connect(self._on_create)
        btn_row.addWidget(create_btn)
        root.addLayout(btn_row)

    def _on_tier_changed(self, radio):
        """Reset the Extras and Panel checkboxes to match the newly selected
        tier's defaults. Without this, the checkboxes keep whatever state
        they had (all True at startup) and that gets merged over the tier
        defaults in merge_options_for_tier(), silently defeating
        Simple/Showcase. Showcase also turns on every panel -- otherwise it
        only differs from Full by a few extra nodes that don't read as a
        visually denser HUD."""
        if radio is None:
            return
        tier = radio.text()
        defaults = DEFAULT_OPTIONS_BY_TIER.get(tier, DEFAULT_OPTIONS)
        for key, cb in self.option_checks.items():
            cb.setChecked(defaults.get(key, False))
        panel_set = set(PANEL_ORDER) if tier == "Showcase" else set(DEFAULT_PANELS)
        for name, cb in self.panel_checks.items():
            cb.setChecked(name in panel_set)

    def _remember_skip_pref(self):
        if self.dont_show_cb is not None and self.dont_show_cb.isChecked():
            self.skip_on_future_launches = True

    def _on_skip(self):
        self._remember_skip_pref()
        self.result_project = None
        self.reject()

    def _on_create(self):
        self._remember_skip_pref()
        category = self.category_group.checkedButton().text() if self.category_group.checkedButton() else "Minimal"
        resolution = self.res_combo.currentText()
        panels = [name for name, cb in self.panel_checks.items() if cb.isChecked()]
        options = {key: cb.isChecked() for key, cb in self.option_checks.items()}
        tier_btn = self.tier_group.checkedButton()
        complexity = tier_btn.text() if tier_btn else "Full"
        self.result_project = build_wizard_project(
            f"{category} HUD", category, resolution, panels, options,
            complexity=complexity,
        )
        self.accept()
