"""
Extra logic nodes for smoother gauges, text composition, and category maps.

Import this module from nodes/__init__.py so register() runs at startup.
Generators live in codegen/logic_generators_extra.py (or inlined in lua_gen.py).
"""
from __future__ import annotations

from conkystudio.nodes.registry import (
    NodeSpec, PropertySpec, register,
    FLOAT, STRING, ENUM, BOOL, INT,
    KIND_NUMBER, KIND_TEXT, KIND_PERCENT, KIND_CATEGORY, NUMERIC_KINDS, ALL_KINDS,
)

LOGIC_COLOR = "#5f8fd6"


register(NodeSpec(
    type="logic.smooth", category="logic", label="Smooth (EMA)", color=LOGIC_COLOR,
    icon="math", subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Exponential moving average toward the input. Quiets noisy sensors before gauges. "
                "Uses per-node STATE so the smoothed value persists across frames.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=-1e9, maximum=1e9),
        PropertySpec(key="alpha", label="Alpha (0–1)", kind=FLOAT, default=0.15,
                     minimum=0.01, maximum=1.0, step=0.01, group="Smoothing",
                     help="1 = follow instantly, 0.05–0.2 = heavy smoothing."),
        PropertySpec(key="init_from_input", label="Init from first sample", kind=BOOL, default=True,
                     group="Smoothing",
                     help="If on, first frame seeds STATE from the input instead of 0."),
    ],
))

register(NodeSpec(
    type="logic.rate_of_change", category="logic", label="Rate of Change", color=LOGIC_COLOR,
    icon="math", subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=False,
    description="Difference between current value and the value from N samples ago "
                "(at sensor refresh cadence). Positive = rising.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=-1e9, maximum=1e9),
        PropertySpec(key="samples", label="Look-back samples", kind=INT, default=4,
                     minimum=1, maximum=120, group="Window",
                     help="Compared against the value stored this many refreshes ago."),
    ],
))

register(NodeSpec(
    type="logic.hysteresis", category="logic", label="Hysteresis", color=LOGIC_COLOR,
    icon="branch", subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Outputs 1 after Value crosses High, stays 1 until Value falls below Low. "
                "Stops LEDs and warnings from flickering around a single threshold.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True,
                     accepts=NUMERIC_KINDS, minimum=-1e9, maximum=1e9),
        PropertySpec(key="high", label="High (turn on)", kind=FLOAT, default=85.0, group="Band"),
        PropertySpec(key="low", label="Low (turn off)", kind=FLOAT, default=75.0, group="Band",
                     help="Must be ≤ High for sensible behaviour."),
        PropertySpec(key="on_value", label="On output", kind=FLOAT, default=1.0, group="Output"),
        PropertySpec(key="off_value", label="Off output", kind=FLOAT, default=0.0, group="Output"),
    ],
))

register(NodeSpec(
    type="logic.string_join", category="logic", label="String Join", color=LOGIC_COLOR,
    icon="text", subcategory="Logic", output_kind=KIND_TEXT, simple_mode=True,
    description="Concatenate A and B with an optional separator (e.g. artist + ' — ' + title).",
    properties=[
        PropertySpec(key="input_a", label="A", kind=STRING, default="", bindable=True, accepts=ALL_KINDS),
        PropertySpec(key="input_b", label="B", kind=STRING, default="", bindable=True, accepts=ALL_KINDS),
        PropertySpec(key="separator", label="Separator", kind=STRING, default=" ", group="Format"),
        PropertySpec(key="skip_empty", label="Skip empty parts", kind=BOOL, default=True, group="Format"),
    ],
))

register(NodeSpec(
    type="logic.enum_map", category="logic", label="Enum Map", color=LOGIC_COLOR,
    icon="branch", subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Map a text/category token to a number. Match is case-insensitive. "
                "Useful for weather category → icon index or status → opacity.",
    properties=[
        PropertySpec(key="input", label="Input", kind=STRING, default="", bindable=True,
                     accepts=(KIND_TEXT, KIND_CATEGORY, KIND_NUMBER, KIND_PERCENT)),
        PropertySpec(key="keys", label="Keys (comma-separated)", kind=STRING,
                     default="clear,cloud,rain,snow,storm",
                     group="Map",
                     help="Tokens to match, in order. First match wins."),
        PropertySpec(key="values", label="Values (comma-separated)", kind=STRING,
                     default="0,1,2,3,4",
                     group="Map",
                     help="Numbers parallel to Keys. Non-numeric entries become 0."),
        PropertySpec(key="default_value", label="Default", kind=FLOAT, default=-1.0, group="Map",
                     help="Used when Input matches no key."),
    ],
))
