"""
"Native" data sources: things Conky already knows how to read itself via
its built-in ${...} template variables. These need no background script,
no cache file, no polling loop -- the generated Lua just calls
conky_parse('${...}') straight from the framework's safe_parse/safe_number
helpers (see codegen/lua_framework.py), exactly the pattern already
proven out in batcomputer.lua's refresh_stats().

Contrast with nodes/sources_external.py, whose sources need a real
external command (lm-sensors, nvidia-smi, curl) that Conky has no
built-in variable for.
"""
from __future__ import annotations

from conkystudio.nodes.registry import (
    NodeSpec, PropertySpec, register,
    STRING, ENUM, PATH,
    KIND_PERCENT, KIND_NUMBER, KIND_TEXT,
)

SOURCE_COLOR = "#3fa796"  # teal -- native, "free" sources (no extra process spawned)

register(NodeSpec(
    type="source.cpu_percent", category="source", label="CPU Usage", color=SOURCE_COLOR,
    icon="cpu", output_kind=KIND_PERCENT, subcategory="System",
    description="Overall or per-core CPU load, straight from Conky's own ${cpu} variable.",
    properties=[
        PropertySpec(key="core", label="Core", kind=ENUM, default="overall",
                     choices=["overall", "cpu0", "cpu1", "cpu2", "cpu3", "cpu4", "cpu5", "cpu6", "cpu7"],
                     help="'overall' uses ${cpu} (average). A specific core uses ${cpu cpuN}."),
    ],
))

register(NodeSpec(
    type="source.ram_percent", category="source", label="RAM Usage", color=SOURCE_COLOR,
    icon="memory", output_kind=KIND_PERCENT, subcategory="System",
    description="${memperc} -- percentage of physical RAM in use.",
    properties=[],
))

register(NodeSpec(
    type="source.disk_percent", category="source", label="Disk Usage", color=SOURCE_COLOR,
    icon="disk", output_kind=KIND_PERCENT, subcategory="System",
    description="${fs_used_perc PATH} -- percentage full for a mounted filesystem.",
    properties=[
        PropertySpec(key="mount_path", label="Mount path", kind=PATH, default="/",
                     help="Any mounted path Conky can see, e.g. / or /home."),
    ],
))

register(NodeSpec(
    type="source.net_down", category="source", label="Network Download", color=SOURCE_COLOR,
    icon="download", output_kind=KIND_NUMBER, subcategory="Network",
    description="Download speed in KiB/s. Auto-detects the active interface at runtime the same "
                 "way batcomputer.lua's resolve_net_iface() does, so it keeps working if you "
                 "switch from Wi-Fi to Ethernet without rebuilding the theme.",
    properties=[
        PropertySpec(key="interface", label="Interface", kind=STRING, default="auto",
                     help="'auto' resolves the first 'up' interface at runtime. Or pin one explicitly, e.g. eth0 / wlan0."),
    ],
))

register(NodeSpec(
    type="source.net_up", category="source", label="Network Upload", color=SOURCE_COLOR,
    icon="upload", output_kind=KIND_NUMBER, subcategory="Network",
    description="Upload speed in KiB/s. Same auto-detected interface as Network Download.",
    properties=[
        PropertySpec(key="interface", label="Interface", kind=STRING, default="auto"),
    ],
))

register(NodeSpec(
    type="source.uptime", category="source", label="Uptime", color=SOURCE_COLOR,
    icon="clock", output_kind=KIND_TEXT, subcategory="System Info",
    description="${uptime} / ${uptime_short}.",
    properties=[
        PropertySpec(key="format", label="Format", kind=ENUM, default="short",
                     choices=["short", "long"], choice_labels=["Short (1h 30m)", "Long (1 day, 2 hours, 30 minutes)"]),
    ],
))

register(NodeSpec(
    type="source.hostname", category="source", label="Hostname", color=SOURCE_COLOR,
    icon="tag", output_kind=KIND_TEXT, subcategory="System Info", description="${nodename}.", properties=[],
))

register(NodeSpec(
    type="source.kernel", category="source", label="Kernel Version", color=SOURCE_COLOR,
    icon="tag", output_kind=KIND_TEXT, subcategory="System Info", description="${kernel}.", properties=[],
))

register(NodeSpec(
    type="source.process_count", category="source", label="Process Count", color=SOURCE_COLOR,
    icon="list", output_kind=KIND_NUMBER, subcategory="System Info", description="${processes}.", properties=[],
))

register(NodeSpec(
    type="source.battery_percent", category="source", label="Battery", color=SOURCE_COLOR,
    icon="battery", output_kind=KIND_PERCENT, subcategory="System",
    description="${battery_percent DEVICE}. Nodes of this type quietly report nothing on "
                 "desktops with no battery, rather than showing a fake 0% / 100%.",
    properties=[
        PropertySpec(key="device", label="Battery device", kind=STRING, default="BAT0"),
    ],
))

register(NodeSpec(
    type="source.greeting", category="source", label="Greeting", color=SOURCE_COLOR,
    icon="sun", output_kind=KIND_TEXT, subcategory="Time",
    description="'Good Morning' / 'Good Afternoon' / 'Good Evening' / 'Good Night' based on the "
                "current hour -- computed directly in Lua (os.date), no external script needed, "
                "unlike a bash greeting.sh doing the same thing with a day-of-hour lookup table.",
    properties=[],
))
register(NodeSpec(
    type="source.datetime", category="source", label="Date / Time", color=SOURCE_COLOR,
    icon="calendar", output_kind=KIND_TEXT, subcategory="Time",
    description="${time FORMAT} using strftime syntax. For a fully custom in-world calendar "
                 "(like the Skyrim theme's Tamriel date), use a Custom Script source instead.",
    properties=[
        PropertySpec(key="strftime_format", label="strftime format", kind=STRING, default="%A, %B %d  %H:%M",
                     help="Standard strftime tokens, e.g. %Y-%m-%d %H:%M:%S"),
    ],
))

# ---------------------------------------------------------------------------
# Additional native sources -- all free reads via Conky's own ${...}
# variables, no background script needed, same as everything above.
# ---------------------------------------------------------------------------

register(NodeSpec(
    type="source.cpu_freq", category="source", label="CPU Frequency (MHz)", color=SOURCE_COLOR,
    icon="cpu", output_kind=KIND_NUMBER, subcategory="System",
    description="${freq} -- current CPU clock speed in MHz for core 0 (or the given core).",
    properties=[
        PropertySpec(key="core", label="Core", kind=ENUM, default="overall",
                     choices=["overall", "cpu0", "cpu1", "cpu2", "cpu3", "cpu4", "cpu5", "cpu6", "cpu7"],
                     help="'overall' uses ${freq} (core 0 on most systems). A specific core uses ${freq N}."),
    ],
))

register(NodeSpec(
    type="source.ram_used", category="source", label="RAM Used", color=SOURCE_COLOR,
    icon="memory", output_kind=KIND_TEXT, subcategory="System",
    description="${mem} -- physical RAM in use, human-formatted by Conky itself (e.g. '3.2GiB'). "
                "Pair with RAM Total, or use RAM Usage (%) instead if you just need a gauge value.",
    properties=[],
))

register(NodeSpec(
    type="source.ram_total", category="source", label="RAM Total", color=SOURCE_COLOR,
    icon="memory", output_kind=KIND_TEXT, subcategory="System",
    description="${memmax} -- total installed physical RAM, human-formatted (e.g. '16.0GiB').",
    properties=[],
))

register(NodeSpec(
    type="source.swap_percent", category="source", label="Swap Usage", color=SOURCE_COLOR,
    icon="memory", output_kind=KIND_PERCENT, subcategory="System",
    description="${swapperc} -- percentage of configured swap space in use.",
    properties=[],
))

register(NodeSpec(
    type="source.net_total_down", category="source", label="Total Downloaded", color=SOURCE_COLOR,
    icon="download", output_kind=KIND_TEXT, subcategory="Network",
    description="${totaldown} -- cumulative data received since Conky started (or since boot on "
                "most distros' counters), human-formatted. Different from Network Download, which "
                "is the current instantaneous speed.",
    properties=[
        PropertySpec(key="interface", label="Interface", kind=STRING, default="auto",
                     help="'auto' resolves the first 'up' interface at runtime, same as Network Download."),
    ],
))

register(NodeSpec(
    type="source.net_total_up", category="source", label="Total Uploaded", color=SOURCE_COLOR,
    icon="upload", output_kind=KIND_TEXT, subcategory="Network",
    description="${totalup} -- cumulative data sent, human-formatted. Same auto-detected interface "
                "as Network Upload.",
    properties=[
        PropertySpec(key="interface", label="Interface", kind=STRING, default="auto"),
    ],
))

register(NodeSpec(
    type="source.wifi_ssid", category="source", label="Wi-Fi Network Name", color=SOURCE_COLOR,
    icon="wifi", output_kind=KIND_TEXT, subcategory="Network",
    description="${wireless_essid IFACE} -- the SSID of the currently associated Wi-Fi network. "
                "Reads as empty on a wired-only machine or an interface that isn't wireless.",
    properties=[
        PropertySpec(key="interface", label="Interface", kind=STRING, default="auto",
                     help="'auto' resolves the first 'up' interface at runtime -- pin one explicitly "
                          "(e.g. wlan0) if auto-detection picks your wired adapter instead."),
    ],
))

register(NodeSpec(
    type="source.wifi_signal", category="source", label="Wi-Fi Signal Quality", color=SOURCE_COLOR,
    icon="wifi", output_kind=KIND_PERCENT, subcategory="Network",
    description="${wireless_link_qual_perc IFACE} -- Wi-Fi link quality as a percentage.",
    properties=[
        PropertySpec(key="interface", label="Interface", kind=STRING, default="auto"),
    ],
))

_TOP_RANK_PROP = PropertySpec(
    key="rank", label="Rank", kind=ENUM, default="1",
    choices=[str(i) for i in range(1, 11)],
    help="1 = the single busiest process by this metric, 2 = second busiest, etc.",
)

register(NodeSpec(
    type="source.top_process_name", category="source", label="Top Process (Name)", color=SOURCE_COLOR,
    icon="list", output_kind=KIND_TEXT, subcategory="System Info",
    description="${top name N} -- the name of the Nth busiest process by CPU usage. Pair with "
                "Top Process (CPU %) at the same Rank for a 'what's eating my CPU' HUD row.",
    properties=[_TOP_RANK_PROP],
))

register(NodeSpec(
    type="source.top_process_cpu", category="source", label="Top Process (CPU %)", color=SOURCE_COLOR,
    icon="cpu", output_kind=KIND_PERCENT, subcategory="System Info",
    description="${top cpu N} -- CPU usage of the Nth busiest process by CPU.",
    properties=[_TOP_RANK_PROP],
))

register(NodeSpec(
    type="source.top_process_mem", category="source", label="Top Process (RAM %)", color=SOURCE_COLOR,
    icon="memory", output_kind=KIND_PERCENT, subcategory="System Info",
    description="${top mem N} -- RAM usage of the Nth busiest process by CPU (same ranking as "
                "Top Process Name/CPU -- Conky ranks the 'top' list by CPU regardless of which "
                "field you print from it).",
    properties=[_TOP_RANK_PROP],
))
