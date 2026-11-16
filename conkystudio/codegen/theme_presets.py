"""
Redesigned Theme Wizard presets — v2.

Replaces whatever theme functions theme_wizard.py currently calls with
seven distinct, deliberately-designed HUDs. Each theme is a plain
Python function of (project, tier, options) -> None that populates the
graph; theme_wizard.py's "Build" step just needs to:

    from conkystudio.codegen.theme_presets import THEME_REGISTRY, build_theme
    from conkystudio.model.project import Project

    project = Project(name=chosen_name)
    build_theme(project, theme_id="reactor", tier="Showcase", user_options={})

`build_theme` sets project.canvas from the theme's own recommended size
(width/height/alignment/transparent/window_class) — the wizard can
still let the user override those fields afterwards the same way it
already lets them edit any Canvas node property.

Tiers (see theme_wizard_patch.TIER_OPTION_SCHEMA for the full option
list a "Full"/"Showcase" checkbox panel should expose):

  Simple    -- the theme's identity in as few nodes as possible: a
               title, its one signature readout, and a footer. No
               chrome, no logic chains, nothing animated beyond what
               the signature element already does on its own.
  Full      -- adds a secondary readout, framing chrome (brackets /
               dividers), a status LED wired through a real
               Source -> Logic -> Visual chain, and a trend graph.
               Gradients turn on if the user left "Fill style:
               Gradient" checked.
  Showcase  -- adds the theme's animated flourish (radar sweep, matrix
               rain, vinyl spinner, spinning fan, ...), a smoothed
               (EMA) drive on the hero gauge so motion reads as fluid
               rather than stepped, a per-core CPU strip, a live
               process table, and a footer ticker line.

Every node type referenced here is checked with theme_common.has_node()
before it's created, so a Studio build missing an optional extension
module degrades gracefully (fewer flourishes) instead of raising.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from conkystudio.model.project import Project
from conkystudio.codegen.theme_common import (
    mk, wire, gradient, maybe_gradient, demo_logic_chain,
    frame_brackets, title_row, caption_row, stat_bar_row, footer_clock_date,
    has_node, pin_sensor_poll_mode,
)

TIERS = ("Simple", "Full", "Showcase")


@dataclass
class ThemeDef:
    id: str
    name: str
    tagline: str
    style: dict
    width: int
    height: int
    alignment: str = "top_right"
    transparent: bool = True
    window_class: str = "conky-studio"
    build: Callable[[Project, str, dict], None] = None


THEME_REGISTRY: dict[str, ThemeDef] = {}


def _register(theme: ThemeDef) -> ThemeDef:
    THEME_REGISTRY[theme.id] = theme
    return theme


def list_themes() -> list[ThemeDef]:
    return list(THEME_REGISTRY.values())


def build_theme(project: Project, theme_id: str, tier: str, user_options: Optional[dict] = None) -> Project:
    """Apply THEME_REGISTRY[theme_id] to `project` at the given tier.
    Sets project.canvas to the theme's recommended window settings, then
    calls the theme's build(project, tier, options)."""
    theme = THEME_REGISTRY[theme_id]
    tier = tier if tier in TIERS else "Full"
    opt = merge_tier_options(tier, user_options)

    c = project.canvas
    c.width, c.height = theme.width, theme.height
    c.alignment = theme.alignment
    c.transparent = theme.transparent
    c.window_class = theme.window_class

    theme.build(project, tier, opt)
    # Teaching-tool default: see theme_common.pin_sensor_poll_mode()'s docstring.
    pin_sensor_poll_mode(project)
    return project


# Imported lazily to avoid a circular import (theme_wizard_patch imports
# nothing from here; this module optionally borrows its tier-option
# merge so the two option systems don't drift apart).
def merge_tier_options(tier: str, user_options: Optional[dict]) -> dict:
    from conkystudio.ui.studio.theme_wizard_patch import merge_options_for_tier
    return merge_options_for_tier(tier, user_options)


# =======================================================================
# 1. AURORA — clean glass-panel minimal HUD
# =======================================================================
AURORA_STYLE = dict(
    accent="#6fd7c4", accent2="#7aa6ff", track="#232b36", panel="#141a22",
    text="#eef2f6", text_dim="#93a1b3", warn="#ff8a80",
    font="Sans", font_display="Sans",
)


def _build_aurora(p: Project, tier: str, opt: dict) -> None:
    st = AURORA_STYLE
    W, H = 420, 620

    if opt.get("chrome") and tier != "Simple":
        mk(p, "visual.rectangle", 0, 0, {
            "x": 16, "y": 16, "width": W - 32, "height": H - 32, "corner_radius": 22,
            "fill": True, "stroke": True, "line_width": 1.0,
            "color": st["panel"], "stroke_color": st["accent"], "opacity": 0.55,
        })
        frame_brackets(p, st, 16, 16, W - 32, H - 32, opacity=0.35)

    title_row(p, st, 32, 40, "SYSTEM", size=22)
    caption_row(p, st, 32, 64, "Live overview", size=11)

    cpu = mk(p, "source.cpu_percent", -420, 120)
    ram = mk(p, "source.ram_percent", -420, 160)
    disk = mk(p, "source.disk_percent", -420, 200, {"mount_path": "/"})

    stat_bar_row(p, st, 32, 96, 356, "CPU", cpu, gradient_on=opt.get("gradient_fills", False))
    stat_bar_row(p, st, 32, 134, 356, "MEMORY", ram, gradient_on=opt.get("gradient_fills", False))
    stat_bar_row(p, st, 32, 172, 356, "DISK", disk, gradient_on=opt.get("gradient_fills", False))

    hero_value_src = cpu
    if tier != "Simple":
        cy = 320
        if opt.get("smooth") and has_node("logic.smooth"):
            sm = mk(p, "logic.smooth", -220, 120, {"alpha": 0.18, "init_from_input": True})
            wire(p, cpu, sm, "value")
            hero_value_src = sm

        arc = mk(p, "visual.arc_gauge", 0, 0, {
            "cx": W // 2, "cy": cy, "radius": 78, "thickness": 12,
            "start_angle_deg": -90, "sweep_deg": 300, "cap_style": "round",
            "color": st["accent"], "track_color": st["track"], "track_alpha": 0.5,
            "show_value_text": True, "value_font_size": 30, "value_suffix": "%",
            **maybe_gradient(st, opt.get("gradient_fills", False), angle=90),
        })
        wire(p, hero_value_src, arc, "value")
        caption_row(p, st, W // 2 - 22, cy + 52, "CPU LOAD", size=10)

        if opt.get("signature_effect"):
            mk(p, "visual.glow_pulse", 0, 0, {
                "cx": W // 2, "cy": cy, "radius": 92, "mode": "circle",
                "color": st["accent2"], "layers": 4, "spread": 0.4,
                "pulse_hz": 0.35, "alpha_min": 0.05, "alpha_max": 0.3,
            }, z=(arc.z - 1 if arc else None))
            mk(p, "visual.orbit_field", 0, 0, {
                "cx": W // 2, "cy": cy, "radius": 108, "dot_count": 10,
                "rings": 1, "color": st["accent2"], "opacity": 0.55, "speed_dps": 18,
            })

        if opt.get("leds"):
            _, gate = demo_logic_chain(p, x0=-420, y=260, source_type="source.cpu_temp",
                                        smooth=False, gate_high=78, gate_low=68,
                                        label_prefix="Aurora heat")
            led = mk(p, "visual.led_dot", 0, 0, {
                "cx": 40, "cy": H - 40, "radius": 6, "threshold": 0.5,
                "color_on": st["warn"], "color_off": st["track"], "glow": True,
            })
            wire(p, gate, led, "value")
            caption_row(p, st, 56, H - 46, "THERMAL", size=9)

        if opt.get("graphs"):
            net = mk(p, "source.net_down", -420, 340, {"interface": "auto"})
            spark = mk(p, "visual.sparkline", 0, 0, {
                "x": 32, "y": H - 96, "width": 200, "height": 30,
                "color": st["accent"], "fill": True,
            })
            wire(p, net, spark, "value")
            caption_row(p, st, 32, H - 100, "NETWORK ↓", size=9)

    if tier == "Showcase":
        if opt.get("core_strip"):
            mk(p, "visual.core_strip", 0, 0, {
                "x": 32, "y": H - 150, "core_count": 6, "bar_width": 8,
                "bar_height": 26, "gap": 3, "color": st["accent"],
                "track_color": st["track"], "heat_map": True,
            })
        if opt.get("top_table"):
            mk(p, "visual.top_table", 0, 0, {
                "x": 244, "y": H - 150, "rows": 4, "font_size": 10,
                "color": st["text"], "header_color": st["accent"],
            })
        if opt.get("footer_ticker"):
            up = mk(p, "source.uptime", -420, 400, {"format": "short"})
            footer = mk(p, "visual.text", 0, 0, {
                "value": "", "prefix": "Up ", "x": 32, "y": H - 28,
                "font_family": st["font"], "font_size": 10, "color": st["text_dim"],
            })
            wire(p, up, footer, "value")

    footer_clock_date(p, st, 32, H - 16, size=11)


_register(ThemeDef(
    id="aurora", name="Aurora", tagline="Frosted-glass minimal system readout.",
    style=AURORA_STYLE, width=420, height=620, alignment="top_right",
    build=_build_aurora,
))


# =======================================================================
# 2. REACTOR — sci-fi / JARVIS-style command core
# =======================================================================
REACTOR_STYLE = dict(
    accent="#26fdf1", accent2="#0fb7ad", track="#123033", panel="#05181a",
    text="#d8fbf8", text_dim="#6fb8b3", warn="#ff3b3b",
    font="Orbitron", font_display="Orbitron", font_mono="Share Tech Mono",
)


def _build_reactor(p: Project, tier: str, opt: dict) -> None:
    st = REACTOR_STYLE
    W, H = 460, 460
    cx, cy = W // 2, W // 2 - 10

    title_row(p, st, 30, 28, "SYSTEM CORE", size=16, font_key="font")
    caption_row(p, st, 30, 48, "STATUS: NOMINAL", size=10)

    cpu = mk(p, "source.cpu_percent", -420, 120)
    hero_src = cpu

    if tier == "Showcase" and opt.get("signature_effect"):
        mk(p, "visual.radar_sweep", 0, 0, {
            "cx": cx, "cy": cy, "radius": 150, "ring_count": 3,
            "show_crosshairs": True, "sweep_speed_dps": 55,
            "color": st["accent"], "dim_color": st["accent2"], "blip_count": 3,
        }, z=0)

    if tier != "Simple" and opt.get("smooth") and has_node("logic.smooth"):
        sm = mk(p, "logic.smooth", -220, 120, {"alpha": 0.15, "init_from_input": True})
        wire(p, cpu, sm, "value")
        hero_src = sm

    reactor = mk(p, "visual.reactor_gauge", 0, 0, {
        "cx": cx, "cy": cy, "radius": 96, "label": "CORE OUTPUT %",
        "value_suffix": "%", "color": st["accent"], "dim_color": st["accent2"],
        "accent_color": "#ffcf5c", "warn_color": st["warn"],
        "font_family": st["font"],
        **maybe_gradient(st, opt.get("gradient_fills", False) and tier != "Simple", angle=45),
    })
    wire(p, hero_src, reactor, "value")

    if tier != "Simple":
        if opt.get("brackets"):
            frame_brackets(p, st, 14, 14, W - 28, H - 28, opacity=0.4)

        if opt.get("secondary_gauge"):
            ram = mk(p, "source.ram_percent", -420, 160)
            gpu = mk(p, "source.gpu_util", -420, 200, {"poll_mode": "execi"})
            seg_l = mk(p, "visual.segmented_gauge", 0, 0, {
                "cx": 66, "cy": cy, "radius": 44, "thickness": 8,
                "start_angle_deg": 90, "sweep_deg": 180, "segment_count": 10,
                "color": st["accent"], "track_color": st["track"],
                "show_value_text": False,
            })
            wire(p, ram, seg_l, "value")
            caption_row(p, st, 40, cy + 56, "RAM", size=9)

            seg_r = mk(p, "visual.segmented_gauge", 0, 0, {
                "cx": W - 66, "cy": cy, "radius": 44, "thickness": 8,
                "start_angle_deg": 90, "sweep_deg": 180, "segment_count": 10,
                "color": st["accent2"], "track_color": st["track"],
                "show_value_text": False,
            })
            wire(p, gpu, seg_r, "value")
            caption_row(p, st, W - 92, cy + 56, "GPU", size=9)

        if opt.get("leds"):
            _, gate = demo_logic_chain(p, x0=-420, y=260, source_type="source.cpu_temp",
                                        smooth=False, gate_high=80, gate_low=68,
                                        label_prefix="Reactor thermal")
            led = mk(p, "visual.led_dot", 0, 0, {
                "cx": W - 34, "cy": 34, "radius": 6, "threshold": 0.5,
                "color_on": st["warn"], "color_off": st["track"], "glow": True,
            })
            wire(p, gate, led, "value")

        if opt.get("graphs"):
            net_d = mk(p, "source.net_down", -420, 300, {"interface": "auto"})
            hg = mk(p, "visual.history_graph", 0, 0, {
                "x": 30, "y": H - 78, "width": W - 60, "height": 40,
                "title_label": "NETWORK ↓", "title_color": st["text_dim"],
                "color": st["accent"], "track_color": st["track"], "fill": True,
            })
            wire(p, net_d, hg, "value")

    if tier == "Showcase":
        if opt.get("core_strip"):
            mk(p, "visual.core_strip", 0, 0, {
                "x": 30, "y": H - 116, "core_count": 8, "bar_width": 8,
                "bar_height": 22, "gap": 2, "color": st["accent"],
                "track_color": st["track"], "heat_map": True,
            })
        if opt.get("footer_ticker"):
            host = mk(p, "source.hostname", -420, 340)
            ticker = mk(p, "visual.text", 0, 0, {
                "value": "", "x": 30, "y": 34, "align": "left",
                "font_family": st["font_mono"], "font_size": 9, "color": st["text_dim"],
            })
            wire(p, host, ticker, "value")

    footer_clock_date(p, st, W - 30, H - 16, align="right", font_key="font_mono", size=10)


_register(ThemeDef(
    id="reactor", name="Reactor", tagline="Sci-fi command-core HUD with a central power dial.",
    style=REACTOR_STYLE, width=460, height=460, alignment="top_right",
    build=_build_reactor,
))


# =======================================================================
# 3. TERMINAL — matrix / hacker console
# =======================================================================
TERMINAL_STYLE = dict(
    accent="#39ff14", accent2="#0b6b12", track="#132213", panel="#050705",
    text="#baffb0", text_dim="#4f8f4a", warn="#ff5555",
    font="Share Tech Mono", font_display="Share Tech Mono",
)


def _build_terminal(p: Project, tier: str, opt: dict) -> None:
    st = TERMINAL_STYLE
    W, H = 420, 560

    if tier == "Showcase" and opt.get("signature_effect"):
        mk(p, "visual.matrix_rain", 0, 0, {
            "x": 0, "y": 0, "width": W, "height": H,
            "color": st["accent"], "tail_color": st["accent2"], "opacity": 0.30,
        }, z=0)

    title_row(p, st, 24, 28, "root@system:~$", size=15, font_key="font")

    cpu = mk(p, "source.cpu_percent", -420, 120)
    ram = mk(p, "source.ram_percent", -420, 160)
    disk = mk(p, "source.disk_percent", -420, 200, {"mount_path": "/"})

    stat_bar_row(p, st, 24, 60, 372, "cpu", cpu, bar_style="segmented",
                 gradient_on=opt.get("gradient_fills", False))
    stat_bar_row(p, st, 24, 98, 372, "mem", ram, bar_style="segmented",
                 gradient_on=opt.get("gradient_fills", False))
    stat_bar_row(p, st, 24, 136, 372, "disk", disk, bar_style="segmented",
                 gradient_on=opt.get("gradient_fills", False))

    if tier != "Simple":
        if opt.get("brackets"):
            frame_brackets(p, st, 14, 14, W - 28, H - 28, opacity=0.3)

        hero_src = cpu
        if opt.get("smooth") and has_node("logic.smooth"):
            sm = mk(p, "logic.smooth", -220, 120, {"alpha": 0.2, "init_from_input": True})
            wire(p, cpu, sm, "value")
            hero_src = sm

        if opt.get("graphs"):
            hg = mk(p, "visual.history_graph", 0, 0, {
                "x": 24, "y": 190, "width": W - 48, "height": 70,
                "title_label": "cpu.log", "title_color": st["text_dim"],
                "color": st["accent"], "track_color": st["track"], "fill": True,
            })
            wire(p, hero_src, hg, "value")

        if opt.get("secondary_gauge"):
            up = mk(p, "source.uptime", -420, 240, {"format": "short"})
            up_txt = mk(p, "visual.text", 0, 0, {
                "value": "", "prefix": "uptime: ", "x": 24, "y": 284,
                "font_family": st["font"], "font_size": 12, "color": st["text_dim"],
            })
            wire(p, up, up_txt, "value")

        if opt.get("leds"):
            _, gate = demo_logic_chain(p, x0=-420, y=300, source_type="source.cpu_percent",
                                        smooth=False, gate_high=90, gate_low=75,
                                        label_prefix="Terminal proc")
            led = mk(p, "visual.led_dot", 0, 0, {
                "cx": 34, "cy": 310, "radius": 5, "threshold": 0.5,
                "color_on": st["warn"], "color_off": st["track"], "glow": True,
            })
            wire(p, gate, led, "value")
            caption_row(p, st, 48, 305, "PROC", size=9)

    if tier == "Showcase":
        if opt.get("top_table"):
            mk(p, "visual.top_table", 0, 0, {
                "x": 24, "y": 330, "rows": 5, "row_height": 17, "font_size": 10,
                "font_family": st["font"], "color": st["text"], "header_color": st["accent"],
                "alt_row_color": st["track"],
            })
        if opt.get("core_strip"):
            mk(p, "visual.core_strip", 0, 0, {
                "x": 24, "y": H - 100, "core_count": 8, "bar_width": 8,
                "bar_height": 24, "gap": 2, "color": st["accent"],
                "track_color": st["track"], "heat_map": False,
            })
        if opt.get("footer_ticker"):
            proc = mk(p, "source.process_count", -420, 400)
            tick = mk(p, "visual.text", 0, 0, {
                "value": "", "prefix": "procs: ", "x": 24, "y": H - 40,
                "font_family": st["font"], "font_size": 10, "color": st["text_dim"],
            })
            wire(p, proc, tick, "value")

    footer_clock_date(p, st, 24, H - 16, fmt="%Y-%m-%d %H:%M:%S", size=11)


_register(ThemeDef(
    id="terminal", name="Terminal", tagline="Green-on-black hacker console.",
    style=TERMINAL_STYLE, width=420, height=560, alignment="top_left",
    build=_build_terminal,
))


# =======================================================================
# 4. VINYL LOUNGE — now-playing media HUD
# =======================================================================
VINYL_STYLE = dict(
    accent="#e0b34d", accent2="#a9642f", track="#33281c", panel="#1b140f",
    text="#f3e6d0", text_dim="#b89a78", warn="#e05f5f",
    font="Sans", font_display="Sans",
)


def _build_vinyl(p: Project, tier: str, opt: dict) -> None:
    st = VINYL_STYLE
    W, H = 460, 420

    title_row(p, st, 30, 28, "NOW PLAYING", size=16)

    title_src = mk(p, "source.nowplaying_title", -420, 120, {"player": "spotify"})
    artist_src = mk(p, "source.nowplaying_artist", -420, 160, {"player": "spotify"})
    progress = mk(p, "source.nowplaying_progress", -420, 200, {"player": "spotify"})
    status = mk(p, "source.nowplaying_status", -420, 240, {"player": "spotify"})

    art_x, art_y, art_size = 30, 60, 140
    if tier != "Simple" and opt.get("signature_effect") and tier == "Showcase":
        mk(p, "visual.vinyl_spinner", 0, 0, {
            "cx": art_x + art_size // 2, "cy": art_y + art_size // 2, "radius": art_size * 0.62,
            "label_radius": art_size * 0.22, "disc_color": "#15161a",
            "groove_color": st["track"], "label_color": st["accent"],
            "show_tonearm": True, "tonearm_color": st["text_dim"],
        }, z=0)

    mk(p, "visual.album_art", 0, 0, {
        "x": art_x, "y": art_y, "size": art_size, "corner_radius": art_size // 2,
    })

    joined_x = art_x + art_size + 20
    join = mk(p, "logic.string_join", -220, 120, {"separator": " — ", "skip_empty": True})
    wire(p, title_src, join, "input_a")
    wire(p, artist_src, join, "input_b")
    track_txt = mk(p, "visual.text", 0, 0, {
        "value": "", "x": joined_x, "y": art_y + 20, "align": "left",
        "font_family": st["font"], "font_size": 14, "bold": True, "color": st["text"],
    })
    wire(p, join, track_txt, "value")

    bar = mk(p, "visual.bar", 0, 0, {
        "x": joined_x, "y": art_y + 46, "width": W - joined_x - 30, "height": 6,
        "style": "solid", "corner_radius": 3, "color": st["accent"],
        "track_color": st["track"],
        **maybe_gradient(st, opt.get("gradient_fills", False), angle=0),
    })
    wire(p, progress, bar, "value")

    if tier != "Simple":
        if opt.get("brackets"):
            frame_brackets(p, st, art_x - 6, art_y - 6, art_size + 12, art_size + 12, opacity=0.5)

        if opt.get("leds"):
            gate = mk(p, "logic.enum_map", -220, 240, {
                "keys": "playing,paused,stopped", "values": "1,0,0", "default_value": 0,
            })
            wire(p, status, gate, "input")
            led = mk(p, "visual.led_dot", 0, 0, {
                "cx": joined_x, "cy": art_y + 70, "radius": 5, "threshold": 0.5,
                "color_on": st["accent"], "color_off": st["track"], "glow": True,
            })
            wire(p, gate, led, "value")
            caption_row(p, st, joined_x + 12, art_y + 65, "PLAYING", size=9)

        if opt.get("signature_effect") and tier == "Full":
            # Full tier gets the spinner too, just without the Showcase's extra ring.
            mk(p, "visual.vinyl_spinner", 0, 0, {
                "cx": art_x + art_size // 2, "cy": art_y + art_size // 2, "radius": art_size * 0.6,
                "disc_color": "#15161a", "groove_color": st["track"], "label_color": st["accent"],
            }, z=0)

        if opt.get("graphs"):
            cpu = mk(p, "source.cpu_percent", -420, 280)
            spark = mk(p, "visual.sparkline", 0, 0, {
                "x": 30, "y": H - 90, "width": 180, "height": 26, "color": st["accent"],
            })
            wire(p, cpu, spark, "value")
            caption_row(p, st, 30, H - 96, "SYSTEM LOAD", size=9)

    if tier == "Showcase":
        if opt.get("signature_effect"):
            mk(p, "visual.radial_spectrum", 0, 0, {
                "cx": art_x + art_size // 2, "cy": art_y + art_size // 2,
                "inner_radius": art_size * 0.62, "bar_count": 28,
                "max_length": 22, "color": st["accent"], "idle_energy": 30,
            })
        if opt.get("top_table"):
            mk(p, "visual.top_table", 0, 0, {
                "x": 30, "y": H - 132, "rows": 3, "font_size": 10,
                "color": st["text"], "header_color": st["accent"],
            })
        if opt.get("footer_ticker"):
            album = mk(p, "source.nowplaying_album", -420, 320, {"player": "spotify"})
            tick = mk(p, "visual.text", 0, 0, {
                "value": "", "x": joined_x, "y": art_y + 90, "align": "left",
                "font_family": st["font"], "font_size": 10, "color": st["text_dim"],
            })
            wire(p, album, tick, "value")

    footer_clock_date(p, st, 30, H - 18, size=10)


_register(ThemeDef(
    id="vinyl_lounge", name="Vinyl Lounge", tagline="Warm now-playing HUD with a spinning record.",
    style=VINYL_STYLE, width=460, height=420, alignment="bottom_right",
    build=_build_vinyl,
))


# =======================================================================
# 5. DEPARTURES — split-flap transit board
# =======================================================================
DEPARTURES_STYLE = dict(
    accent="#ffb703", accent2="#fb8500", track="#2a2a26", panel="#10100e",
    text="#ffe8b8", text_dim="#8f8770", warn="#e05f5f",
    font="Share Tech Mono", font_display="Share Tech Mono",
)


def _build_departures(p: Project, tier: str, opt: dict) -> None:
    st = DEPARTURES_STYLE
    W, H = 480, 360

    title_row(p, st, 24, 24, "DEPARTURES", size=18)
    mk(p, "visual.hline", 0, 0, {"x": 24, "y": 46, "length": W - 48, "color": st["accent"], "opacity": 0.6})

    clock_src = mk(p, "source.datetime", -420, 100, {"strftime_format": "%H:%M"})
    clock = mk(p, "visual.flip_digit", 0, 0, {
        "x": 24, "y": 62, "width": 96, "height": 56, "font_size": 30,
        "value": "", "card_color": st["panel"], "text_color": st["text"],
        "flap_color": st["track"], "divider_color": "#0c0f14",
    })
    wire(p, clock_src, clock, "value")
    caption_row(p, st, 24, 122, "LOCAL TIME", size=9)

    if tier == "Simple":
        cpu = mk(p, "source.cpu_percent", -420, 140)
        ram = mk(p, "source.ram_percent", -420, 180)
        for i, (label, src) in enumerate((("CPU", cpu), ("RAM", ram))):
            y = 62 + i * 26
            caption_row(p, st, 150, y, label, size=10)
            txt = mk(p, "visual.text", 0, 0, {
                "value": "", "suffix": "%", "x": 220, "y": y + 10, "align": "left",
                "font_family": st["font"], "font_size": 13, "color": st["text"],
            })
            wire(p, src, txt, "value")
    else:
        cpu = mk(p, "source.cpu_percent", -420, 140)
        ram = mk(p, "source.ram_percent", -420, 180)
        disk = mk(p, "source.disk_percent", -420, 220, {"mount_path": "/"})
        for i, (label, src) in enumerate((("CPU", cpu), ("RAM", ram), ("DISK", disk))):
            fx = 150 + i * 108
            caption_row(p, st, fx, 62, label, size=9)
            card_src = src
            fmt_node = mk(p, "logic.string_format", -260 + i * 10, 200, {"template": "{value}%", "decimals": 0})
            wire(p, src, fmt_node, "input")
            card = mk(p, "visual.flip_digit", 0, 0, {
                "x": fx, "y": 76, "width": 88, "height": 44, "font_size": 20,
                "value": "", "card_color": st["panel"], "text_color": st["accent"],
                "flap_color": st["track"],
            })
            wire(p, fmt_node, card, "value")

        if opt.get("brackets"):
            mk(p, "visual.hline", 0, 0, {"x": 24, "y": 134, "length": W - 48, "color": st["accent"], "opacity": 0.3})

        if opt.get("leds"):
            _, gate = demo_logic_chain(p, x0=-420, y=260, source_type="source.cpu_percent",
                                        smooth=False, gate_high=88, gate_low=72,
                                        label_prefix="Departures delay")
            led = mk(p, "visual.led_dot", 0, 0, {
                "cx": W - 30, "cy": 30, "radius": 6, "threshold": 0.5,
                "color_on": st["warn"], "color_off": st["track"], "glow": True,
            })
            wire(p, gate, led, "value")
            caption_row(p, st, W - 96, 24, "ON TIME", size=9)

        if opt.get("graphs"):
            net = mk(p, "source.net_down", -420, 300, {"interface": "auto"})
            hg = mk(p, "visual.history_graph", 0, 0, {
                "x": 24, "y": 150, "width": W - 48, "height": 44,
                "title_label": "", "color": st["accent"], "track_color": st["track"], "fill": True,
            })
            wire(p, net, hg, "value")

    if tier == "Showcase":
        if opt.get("top_table"):
            caption_row(p, st, 24, 202, "GATE  DESTINATION            STATUS", size=9)
            mk(p, "visual.hline", 0, 0, {"x": 24, "y": 216, "length": W - 48, "color": st["track"], "opacity": 0.8})
            mk(p, "visual.top_table", 0, 0, {
                "x": 24, "y": 224, "rows": 4, "row_height": 18, "show_header": False,
                "font_family": st["font"], "font_size": 10, "color": st["text"],
                "header_color": st["accent"], "alt_row_color": st["track"],
            })
        if opt.get("signature_effect"):
            mk(p, "visual.loading_dots", 0, 0, {
                "x": W - 90, "y": H - 22, "dot_radius": 3, "gap": 10,
                "color": st["accent"],
            })
            caption_row(p, st, W - 150, H - 30, "BOARDING", size=8)
        if opt.get("footer_ticker"):
            host = mk(p, "source.hostname", -420, 320)
            tick = mk(p, "visual.text", 0, 0, {
                "value": "", "x": 24, "y": H - 16, "align": "left",
                "font_family": st["font"], "font_size": 9, "color": st["text_dim"],
            })
            wire(p, host, tick, "value")


_register(ThemeDef(
    id="departures", name="Departures", tagline="Split-flap transit-board system monitor.",
    style=DEPARTURES_STYLE, width=480, height=360, alignment="top_left",
    build=_build_departures,
))


# =======================================================================
# 6. COCKPIT — aviation instrument panel
# =======================================================================
COCKPIT_STYLE = dict(
    accent="#7fd858", accent2="#3f8f2a", track="#24301f", panel="#0c120c",
    text="#d8f5c8", text_dim="#7b9a6a", warn="#ffcf3a", danger="#ff5a3c",
    font="Share Tech Mono", font_display="Share Tech Mono",
)


def _build_cockpit(p: Project, tier: str, opt: dict) -> None:
    st = COCKPIT_STYLE
    W, H = 460, 460
    cx, cy = W // 2, H // 2 - 10

    title_row(p, st, 24, 24, "SYSTEM INSTRUMENTS", size=13)

    cpu = mk(p, "source.cpu_percent", -420, 120)
    hero_src = cpu
    if tier != "Simple" and opt.get("smooth") and has_node("logic.smooth"):
        sm = mk(p, "logic.smooth", -220, 120, {"alpha": 0.15, "init_from_input": True})
        wire(p, cpu, sm, "value")
        hero_src = sm

    needle = mk(p, "visual.needle_gauge", 0, 0, {
        "cx": cx, "cy": cy, "radius": 92, "start_angle": 135, "end_angle": 45,
        "track_color": st["track"], "zone_ok_color": st["accent"],
        "zone_warn_color": st["warn"], "zone_danger_color": st["danger"],
        "needle_color": st["text"], "hub_color": st["panel"], "tick_color": st["text_dim"],
        "font_family": st["font"], "value_suffix": "%",
    })
    wire(p, hero_src, needle, "value")
    caption_row(p, st, cx - 18, cy + 60, "CPU", size=10)

    if tier != "Simple":
        if opt.get("brackets"):
            frame_brackets(p, st, 14, 14, W - 28, H - 28, opacity=0.4)
            mk(p, "visual.hline", 0, 0, {"x": 24, "y": 46, "length": W - 48, "color": st["accent"], "opacity": 0.3})

        if opt.get("secondary_gauge"):
            ram = mk(p, "source.ram_percent", -420, 160)
            disk = mk(p, "source.disk_percent", -420, 200, {"mount_path": "/"})
            left = mk(p, "visual.segmented_gauge", 0, 0, {
                "cx": 74, "cy": cy, "radius": 46, "thickness": 8,
                "start_angle_deg": 90, "sweep_deg": 180, "segment_count": 8,
                "color": st["accent"], "track_color": st["track"], "show_value_text": False,
            })
            right = mk(p, "visual.arc_gauge", 0, 0, {
                "cx": W - 74, "cy": cy, "radius": 46, "thickness": 8,
                "start_angle_deg": -90, "sweep_deg": 300,
                "color": st["accent2"], "track_color": st["track"], "show_value_text": False,
            })
            wire(p, ram, left, "value")
            wire(p, disk, right, "value")
            caption_row(p, st, 56, cy + 56, "RAM", size=9)
            caption_row(p, st, W - 100, cy + 56, "DISK", size=9)

        if opt.get("leds"):
            _, gate = demo_logic_chain(p, x0=-420, y=260, source_type="source.cpu_temp",
                                        smooth=False, gate_high=82, gate_low=68,
                                        label_prefix="Cockpit caution")
            led = mk(p, "visual.led_dot", 0, 0, {
                "cx": W - 34, "cy": 34, "radius": 6, "threshold": 0.5,
                "color_on": st["warn"], "color_off": st["track"], "glow": True,
            })
            wire(p, gate, led, "value")
            caption_row(p, st, W - 130, 28, "MASTER CAUTION", size=8)

        if opt.get("graphs"):
            net = mk(p, "source.net_down", -420, 300, {"interface": "auto"})
            hg = mk(p, "visual.history_graph", 0, 0, {
                "x": 24, "y": H - 88, "width": W - 48, "height": 40,
                "title_label": "NET", "title_color": st["text_dim"],
                "color": st["accent"], "track_color": st["track"], "fill": True,
            })
            wire(p, net, hg, "value")

    if tier == "Showcase":
        if opt.get("signature_effect") and has_node("visual.spinning_fan"):
            # Driven by CPU % rather than raw Fan RPM -- speed_pct expects a
            # 0-100-ish value, and this keeps the blades' idle/max range
            # sane without an extra Map Range node just for chrome.
            fan = mk(p, "visual.spinning_fan", 0, 0, {
                "cx": 60, "cy": H - 60, "blade_count": 5, "blade_length": 30,
                "blade_color": st["text_dim"], "hub_color": st["panel"], "heat_map": True,
            })
            wire(p, cpu, fan, "speed_pct")
            caption_row(p, st, 28, H - 20, "COOLING", size=8)
        if opt.get("core_strip"):
            mk(p, "visual.core_strip", 0, 0, {
                "x": 140, "y": H - 100, "core_count": 8, "bar_width": 8,
                "bar_height": 24, "gap": 2, "color": st["accent"], "track_color": st["track"],
            })
        if opt.get("footer_ticker"):
            up = mk(p, "source.uptime", -420, 380, {"format": "short"})
            tick = mk(p, "visual.text", 0, 0, {
                "value": "", "prefix": "UPTIME ", "x": 140, "y": H - 18,
                "font_family": st["font"], "font_size": 9, "color": st["text_dim"],
            })
            wire(p, up, tick, "value")

    footer_clock_date(p, st, W - 24, H - 16, align="right", size=10)


_register(ThemeDef(
    id="cockpit", name="Cockpit", tagline="Aviation instrument panel for your system vitals.",
    style=COCKPIT_STYLE, width=460, height=460, alignment="top_right",
    build=_build_cockpit,
))


# =======================================================================
# 7. ALMANAC — parchment / light desk-almanac HUD
# =======================================================================
ALMANAC_STYLE = dict(
    accent="#7a5230", accent2="#b08a4e", track="#cbb98a", panel="#ece0c4",
    text="#3a2a18", text_dim="#6b5636", warn="#9c3b2e",
    font="Sans", font_display="Sans",
)


def _build_almanac(p: Project, tier: str, opt: dict) -> None:
    st = ALMANAC_STYLE
    W, H = 420, 620

    # The parchment panel is structural to this theme's identity (dark
    # desktop -> readable paper card), so unlike other themes' optional
    # "chrome" background it's drawn at every tier, not just Full+.
    mk(p, "visual.rectangle", 0, 0, {
        "x": 0, "y": 0, "width": W, "height": H, "corner_radius": 10,
        "fill": True, "stroke": True, "line_width": 1.5,
        "color": st["panel"], "stroke_color": st["accent2"], "opacity": 0.94,
    }, z=0)

    title_row(p, st, 30, 40, "ALMANAC", size=22)
    mk(p, "visual.hline", 0, 0, {"x": 30, "y": 56, "length": W - 60, "color": st["accent2"], "opacity": 0.7})

    greet = mk(p, "source.greeting", -420, 100)
    greet_txt = mk(p, "visual.text", 0, 0, {
        "value": "", "x": 30, "y": 86, "font_family": st["font"], "font_size": 13,
        "color": st["text_dim"], "italic": True, "halo": True,
    })
    wire(p, greet, greet_txt, "value")

    weather_cond = mk(p, "source.weather_condition", -420, 140)
    weather_temp = mk(p, "source.weather_temp_f", -420, 180)
    if tier == "Simple":
        wtxt = mk(p, "visual.text", 0, 0, {
            "value": "", "suffix": "°F", "x": 30, "y": 120,
            "font_family": st["font"], "font_size": 16, "color": st["text"], "halo": True,
        })
        wire(p, weather_temp, wtxt, "value")
        ctxt = mk(p, "visual.text", 0, 0, {
            "value": "", "x": 30, "y": 142, "font_family": st["font"], "font_size": 11,
            "color": st["text_dim"], "halo": True,
        })
        wire(p, weather_cond, ctxt, "value")
    else:
        weather_cat = mk(p, "source.weather_category", -420, 220)
        icon = mk(p, "visual.weather_icon", 0, 0, {
            "cx": 46, "cy": 128, "size": 30, "color": st["accent"],
        })
        wire(p, weather_cat, icon, "category")
        wtxt = mk(p, "visual.text", 0, 0, {
            "value": "", "suffix": "°F", "x": 80, "y": 120,
            "font_family": st["font"], "font_size": 18, "bold": True, "color": st["text"],
        })
        wire(p, weather_temp, wtxt, "value")
        ctxt = mk(p, "visual.text", 0, 0, {
            "value": "", "x": 80, "y": 140, "font_family": st["font"], "font_size": 11,
            "color": st["text_dim"],
        })
        wire(p, weather_cond, ctxt, "value")

    if tier == "Simple":
        date_src = mk(p, "source.datetime", -420, 260, {"strftime_format": "%A, %B %d, %Y"})
        date_txt = mk(p, "visual.text", 0, 0, {
            "value": "", "x": 30, "y": 190, "font_family": st["font"], "font_size": 14,
            "color": st["text"],
        })
        wire(p, date_src, date_txt, "value")
    else:
        mk(p, "visual.wall_calendar", 0, 0, {
            "x": 30, "y": 176, "cell_w": 40, "cell_h": 30,
            "title_color": st["text"], "weekday_color": st["text_dim"],
            "day_color": st["text"], "today_color": st["panel"], "today_fill": st["accent"],
            "outside_color": st["track"], "grid_color": st["track"], "font_family": st["font"],
        })

        mk(p, "visual.moon_phase", 0, 0, {
            "cx": W - 80, "cy": 430, "radius": 34, "color": st["accent2"],
            "dark_color": st["track"], "rim_color": st["accent"], "text_color": st["text_dim"],
            "font_family": st["font"], "show_brackets": opt.get("brackets", False),
        })

        if opt.get("brackets"):
            frame_brackets(p, st, 20, 20, W - 40, H - 40, opacity=0.25)

        if opt.get("leds"):
            _, gate = demo_logic_chain(p, x0=-420, y=300, source_type="source.disk_percent",
                                        source_props={"mount_path": "/"}, smooth=False,
                                        gate_high=90, gate_low=80, label_prefix="Almanac disk")
            led = mk(p, "visual.led_dot", 0, 0, {
                "cx": W - 34, "cy": 34, "radius": 6, "threshold": 0.5,
                "color_on": st["warn"], "color_off": st["track"], "glow": False,
            })
            wire(p, gate, led, "value")

    if tier == "Showcase":
        cpu = mk(p, "source.cpu_percent", -420, 340)
        spark = mk(p, "visual.sparkline", 0, 0, {
            "x": 30, "y": H - 60, "width": 160, "height": 24, "color": st["accent"],
        })
        wire(p, cpu, spark, "value")
        caption_row(p, st, 30, H - 78, "today's load", size=9)
        if opt.get("top_table"):
            mk(p, "visual.top_table", 0, 0, {
                "x": 210, "y": H - 96, "rows": 3, "font_size": 9,
                "color": st["text"], "header_color": st["accent"], "show_alt_rows": False,
            })

    footer_clock_date(p, st, 30, H - 22, size=10, fmt="%H:%M — Week %V")


_register(ThemeDef(
    id="almanac", name="Almanac", tagline="Warm parchment desk-almanac: weather, moon, and calendar.",
    style=ALMANAC_STYLE, width=420, height=620, alignment="top_left",
    build=_build_almanac,
))
