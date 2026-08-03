"""
"External" data sources: things Conky has no built-in variable for, so a
real external command has to run (lm-sensors, nvidia-smi / AMD sysfs,
smartctl, curl). Your own themes show two genuinely different, both
valid, ways to wire that up -- exposed here as the `poll_mode` property
on every node in this file rather than picked once for the whole app:

  "execi"  -- Conky's own ${execi N cmd} periodic-cache mechanism. Simple:
              one line, no background loop, no lock file. What
              skyrim_anim.lua uses for GPU/weather/body-temp. Trade-off:
              when the cache expires, the NEXT draw briefly blocks on
              that command's runtime (curl's --max-time caps this, but
              it's not zero).
  "daemon" -- A dedicated background polling loop (added to start.sh)
              writing an atomically-replaced, flock-guarded cache file
              that the Lua draw hook only ever reads, never blocks on.
              What sensors.sh/weather.sh use in the Batman/Iron-Man
              themes. Trade-off: one more moving part (a loop + lock
              file per family), for a HUD that never stutters.

Neither is "more correct" -- execi is the right default for anything
polled slowly (minutes) or for atmospheric/decorative HUDs; daemon mode
earns its keep once you're drawing at high FPS and want zero stutter,
which is exactly the split your own Skyrim vs. Batman themes already
demonstrate.
"""
from __future__ import annotations

from conkystudio.nodes.registry import (
    NodeSpec, PropertySpec, register,
    STRING, ENUM, PATH, INT, CODE,
    KIND_PERCENT, KIND_CELSIUS, KIND_NUMBER, KIND_TEXT, KIND_CATEGORY,
)

EXT_COLOR = "#d97b3f"  # amber -- signals "spawns a real process"

_POLL_MODE = lambda default_interval, execi_default=2: [  # noqa: E731 -- tiny local factory, not worth a def
    PropertySpec(key="poll_mode", label="Polling mode", kind=ENUM, default="execi",
                 choices=["execi", "daemon"],
                 choice_labels=["Simple (Conky execi)", "Background daemon (zero-stutter)"],
                 group="Polling"),
    PropertySpec(key="poll_interval", label="Refresh every (sec)", kind=INT, default=default_interval,
                 minimum=1, maximum=3600, group="Polling"),
]

# ---------------------------------------------------------------- CPU temp
register(NodeSpec(
    type="source.cpu_temp", category="source", label="CPU Temperature", color=EXT_COLOR,
    icon="thermometer", output_kind=KIND_CELSIUS, subcategory="Sensors",
    description="Reads lm-sensors, auto-matching the coretemp/k10temp/cpu_thermal/zenpower chip "
                "the same way sensors.sh does.",
    script_family="cpu_sensors", script_output_key="cpu_temp",
    properties=[
        PropertySpec(key="chip_pattern", label="Chip pattern (advanced)", kind=STRING,
                     default="^(coretemp-|k10temp-|cpu_thermal-|zenpower-)",
                     help="Regex matched against `sensors -u` chip names. Only touch this if "
                          "auto-detection picks the wrong sensor on your hardware."),
        *_POLL_MODE(3),
    ],
))

# ---------------------------------------------------------------- GPU family
_GPU_POLL = _POLL_MODE(2)
_GPU_COMMON = [
    PropertySpec(key="amd_drm_card", label="AMD card override (advanced)", kind=STRING, default="",
                 help="Leave blank to auto-pick the first card with a gpu_busy_percent file "
                      "(NVIDIA is always auto-detected via nvidia-smi, no override needed). "
                      "On a hybrid/multi-GPU laptop, set this explicitly if usage reads stuck at 0%, "
                      "e.g. card1 -- run `ls /sys/class/drm/` to see what's available."),
]

register(NodeSpec(
    type="source.gpu_util", category="source", label="GPU Utilization", color=EXT_COLOR,
    icon="gpu", output_kind=KIND_PERCENT, subcategory="Sensors",
    description="NVIDIA via nvidia-smi, or AMD via sysfs gpu_busy_percent.",
    script_family="gpu_stats", script_output_key="gpu_util",
    properties=[*_GPU_COMMON, *_GPU_POLL],
))
register(NodeSpec(
    type="source.gpu_temp", category="source", label="GPU Temperature", color=EXT_COLOR,
    icon="thermometer", output_kind=KIND_CELSIUS, subcategory="Sensors",
    description="NVIDIA via nvidia-smi, or AMD via sysfs hwmon temp1_input.",
    script_family="gpu_stats", script_output_key="gpu_temp",
    properties=[*_GPU_COMMON, *_GPU_POLL],
))
register(NodeSpec(
    type="source.gpu_vram_used", category="source", label="GPU VRAM Used (MB)", color=EXT_COLOR,
    icon="memory", output_kind=KIND_NUMBER, subcategory="Sensors",
    description="VRAM currently in use, in MB.",
    script_family="gpu_stats", script_output_key="gpu_vram_used",
    properties=[*_GPU_COMMON, *_GPU_POLL],
))
register(NodeSpec(
    type="source.gpu_vram_total", category="source", label="GPU VRAM Total (MB)", color=EXT_COLOR,
    icon="memory", output_kind=KIND_NUMBER, subcategory="Sensors",
    description="Total VRAM, in MB -- pair with VRAM Used for a percentage bar.",
    script_family="gpu_stats", script_output_key="gpu_vram_total",
    properties=[*_GPU_COMMON, *_GPU_POLL],
))

# ---------------------------------------------------------------- Disk temp
register(NodeSpec(
    type="source.disk_temp", category="source", label="Disk Temperature", color=EXT_COLOR,
    icon="thermometer", output_kind=KIND_CELSIUS, subcategory="Sensors",
    description="Reads smartctl. Usually needs the theme's start.sh (or a udev rule) run with "
                "permission to query the drive -- see the Hardware panel for a check.",
    script_family="disk_sensors", script_output_key="disk_temp",
    properties=[
        PropertySpec(key="device", label="Disk device", kind=PATH, default="/dev/sda"),
        *_POLL_MODE(30),
    ],
))

# ---------------------------------------------------------------- Fan RPM
register(NodeSpec(
    type="source.fan_rpm", category="source", label="Fan Speed (RPM)", color=EXT_COLOR,
    icon="fan", output_kind=KIND_NUMBER, subcategory="Sensors",
    description="Reads the first non-zero hwmon fan1_input under /sys/class/hwmon -- same "
                "sysfs-scan approach as the GPU family's AMD path. Most laptops and many "
                "motherboards expose this without needing lm-sensors configured specifically "
                "for fans.",
    script_family="fan_sensors", script_output_key="fan_rpm",
    properties=[
        *_POLL_MODE(3),
    ],
))

# ---------------------------------------------------------------- Public IP
_PUBLIC_IP_POLL = [
    PropertySpec(key="poll_mode", label="Polling mode", kind=ENUM, default="daemon",
                 choices=["execi", "daemon"],
                 choice_labels=["Simple (Conky execi)", "Background daemon (zero-stutter)"],
                 group="Polling",
                 help="Defaults to daemon mode for the same reason Weather does: a network call "
                      "is the poll type most likely to hang past its timeout."),
    PropertySpec(key="poll_interval", label="Refresh every (sec)", kind=INT, default=1800,
                 minimum=60, maximum=21600, group="Polling"),
]
register(NodeSpec(
    type="source.public_ip", category="source", label="Public IP Address", color=EXT_COLOR,
    icon="globe", output_kind=KIND_TEXT, subcategory="Network",
    description="Your public-facing IP via a plain-text lookup service (icanhazip.com, falling "
                "back to ifconfig.me). Useful for a remote-access or 'is my VPN up' HUD row.",
    script_family="public_ip", script_output_key="ip",
    properties=_PUBLIC_IP_POLL,
))

# ---------------------------------------------------------------- Weather
_WEATHER_POLL = [
    PropertySpec(key="poll_mode", label="Polling mode", kind=ENUM, default="daemon",
                 choices=["execi", "daemon"],
                 choice_labels=["Simple (Conky execi)", "Background daemon (zero-stutter)"],
                 group="Polling",
                 help="Weather defaults to daemon mode since a network call is the one poll type "
                      "most likely to hang past its timeout."),
    PropertySpec(key="poll_interval", label="Refresh every (sec)", kind=INT, default=1800,
                 minimum=60, maximum=21600, group="Polling"),
]
_WEATHER_COMMON = [
    PropertySpec(key="fallback_location", label="Fallback location", kind=STRING, default="",
                 help="Used only if IP geolocation fails. City name, airport code, or 'City+State' "
                      "for US cities, e.g. Henderson+KY. Leave blank to just retry auto-location."),
    *_WEATHER_POLL,
]
register(NodeSpec(
    type="source.weather_condition", category="source", label="Weather Condition", color=EXT_COLOR,
    icon="cloud", output_kind=KIND_TEXT, subcategory="Weather",
    description="Human-readable condition text from wttr.in, e.g. 'Partly cloudy'.",
    script_family="weather", script_output_key="condition",
    properties=_WEATHER_COMMON,
))
register(NodeSpec(
    type="source.weather_category", category="source", label="Weather Category", color=EXT_COLOR,
    icon="cloud", output_kind=KIND_CATEGORY, subcategory="Weather",
    description="A short token (clear/cloud/overcast/fog/wind/rain/storm/snow/cold/hot/dust/unknown) "
                "meant to drive an Image/Icon node's threshold swap, not to be displayed as text -- "
                "wire this into an Icon node's Icon Trigger, the same role skyrim_weather.sh's "
                "category token plays for draw_weather_icon().",
    script_family="weather", script_output_key="category",
    properties=_WEATHER_COMMON,
))
register(NodeSpec(
    type="source.weather_temp_f", category="source", label="Weather Temp (F)", color=EXT_COLOR,
    icon="thermometer", output_kind=KIND_NUMBER, subcategory="Weather",
    description="Current temperature in Fahrenheit, from the same wttr.in fetch.",
    script_family="weather", script_output_key="temp_f",
    properties=_WEATHER_COMMON,
))

# ---------------------------------------------------------------- Now Playing
_NOWPLAYING_POLL = [
    PropertySpec(key="player", label="Player name", kind=STRING, default="spotify",
                 help="Whatever `playerctl -l` lists -- spotify, vlc, chromium, etc.", group="Player"),
    *_POLL_MODE(2, execi_default=1),
]
register(NodeSpec(
    type="source.nowplaying_title", category="source", label="Track Title", color=EXT_COLOR,
    icon="music", output_kind=KIND_TEXT, subcategory="Media",
    description="Current track title via playerctl. Reads as empty when nothing is playing "
                "rather than showing stale data -- matches playerctl.sh's own behavior.",
    script_family="nowplaying", script_output_key="title",
    properties=_NOWPLAYING_POLL,
))
register(NodeSpec(
    type="source.nowplaying_artist", category="source", label="Track Artist", color=EXT_COLOR,
    icon="music", output_kind=KIND_TEXT, subcategory="Media",
    description="Current track artist via playerctl.",
    script_family="nowplaying", script_output_key="artist",
    properties=_NOWPLAYING_POLL,
))
register(NodeSpec(
    type="source.nowplaying_album", category="source", label="Track Album", color=EXT_COLOR,
    icon="music", output_kind=KIND_TEXT, subcategory="Media",
    description="Current track album via playerctl.",
    script_family="nowplaying", script_output_key="album",
    properties=_NOWPLAYING_POLL,
))
register(NodeSpec(
    type="source.nowplaying_status", category="source", label="Playback Status", color=EXT_COLOR,
    icon="music", output_kind=KIND_CATEGORY, subcategory="Media",
    description="'playing', 'paused', or 'stopped' -- wire into an Image/Icon threshold swap "
                "or a Conditional node to show/hide playback controls.",
    script_family="nowplaying", script_output_key="status",
    properties=_NOWPLAYING_POLL,
))
register(NodeSpec(
    type="source.nowplaying_progress", category="source", label="Playback Progress %", color=EXT_COLOR,
    icon="music", output_kind=KIND_PERCENT, subcategory="Media",
    description="Playback position as a percentage of track length -- feed straight into a Bar, "
                "the same role spot2.sh's 'perc' mode plays for ${execbar}.",
    script_family="nowplaying", script_output_key="progress_pct",
    properties=_NOWPLAYING_POLL,
))

# ---------------------------------------------------------------- Custom
register(NodeSpec(
    type="source.custom_script", category="source", label="Custom Script", color=EXT_COLOR,
    icon="terminal", output_kind=KIND_TEXT, subcategory="Custom",
    description="Any executable script, or an inline body edited in the Properties panel. "
                "Conky Studio wraps it with the same flock + atomic-write cache harness "
                "(daemon mode) or a plain ${execi} call (execi mode). Print a single line "
                "to stdout (or key=value lines for structured use). Prefer Inline script "
                "when fixing a broken legacy import — no external file required.",
    simple_mode=False,
    script_family=None,  # each instance is unique; family = its own node id (handled by builder)
    script_output_key="value",
    properties=[
        PropertySpec(key="script_path", label="Script path", kind=PATH, default="",
                     help="Optional. Copied into the theme's scripts/ folder at build time. "
                          "Ignored when Inline script is non-empty."),
        PropertySpec(key="script_body", label="Inline script", kind=CODE, default="",
                     help="If non-empty, this body is written to scripts/ at Build and used "
                          "instead of Script path. Edit here like Custom Lua — ideal for "
                          "fixing legacy sensors.sh / one-liners without leaving Studio."),
        PropertySpec(key="output_kind", label="Treat output as", kind=ENUM, default="text",
                     choices=["text", "number", "percent", "celsius", "category"],
                     help="Affects which visual properties this source is offered for binding."),
        *_POLL_MODE(5),
    ],
))
