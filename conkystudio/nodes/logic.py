"""
Logic nodes: the "conditionals, math, string formatting" ask. These are
architecturally different from sources (output only) and visuals (input
only) -- a logic node has BOTH bindable inputs and an output, so it can
sit in the middle of a chain: Source -> Logic -> Logic -> Visual. The
codegen side (codegen/lua_gen.py's compute_used_sources +
topological_order) evaluates them in dependency order inside
refresh_sources(), before any visual node reads them.

This is also the category plugins target most often (see
conkystudio/plugins/) -- a community "clamp to range" or "unit convert"
node is a logic node, not a new visual.
"""
from __future__ import annotations

from conkystudio.nodes.registry import (
    NodeSpec, PropertySpec, register,
    FLOAT, STRING, ENUM, BOOL, INT,
    KIND_NUMBER, KIND_TEXT, KIND_PERCENT, KIND_CELSIUS, NUMERIC_KINDS, ALL_KINDS,
)

LOGIC_COLOR = "#5f8fd6"  # blue -- distinct from source teal / visual violet / canvas gold


register(NodeSpec(
    type="logic.math", category="logic", label="Math", color=LOGIC_COLOR, icon="math", subcategory="Logic",
    output_kind=KIND_NUMBER,
    description="Combines two numeric values with an operation -- e.g. average CPU and GPU temp "
                "before feeding a single gauge.",
    properties=[
        PropertySpec(key="input_a", label="A", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-100000, maximum=100000),
        PropertySpec(key="input_b", label="B", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-100000, maximum=100000),
        PropertySpec(key="operation", label="Operation", kind=ENUM, default="add",
                     choices=["add", "subtract", "multiply", "divide", "average", "min", "max"],
                     group="Operation"),
    ],
))

register(NodeSpec(
    type="logic.conditional", category="logic", label="Conditional", color=LOGIC_COLOR, icon="branch", subcategory="Logic",
    output_kind=KIND_NUMBER,
    description="IF Input <compare> Threshold THEN Then-value ELSE Else-value -- the "
                "'IF GPU_TEMP > 80 THEN show warning icon' rule as a node instead of Lua.",
    properties=[
        PropertySpec(key="input", label="Input", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-100000, maximum=100000),
        PropertySpec(key="comparison", label="Comparison", kind=ENUM, default=">",
                     choices=[">", ">=", "<", "<=", "=="], group="Condition"),
        PropertySpec(key="threshold", label="Threshold", kind=FLOAT, default=80.0, group="Condition"),
        PropertySpec(key="then_value", label="Then value", kind=FLOAT, default=1.0, group="Output"),
        PropertySpec(key="else_value", label="Else value", kind=FLOAT, default=0.0, group="Output"),
    ],
))

register(NodeSpec(
    type="logic.string_format", category="logic", label="String Format", color=LOGIC_COLOR, icon="text", subcategory="Logic",
    output_kind=KIND_TEXT,
    description="Wrap a value in a template, e.g. 'CPU: {value}%' -- lets a Text Label show "
                "formatted output without a separate prefix/suffix per label.",
    properties=[
        PropertySpec(key="input", label="Input", kind=STRING, default="", bindable=True, accepts=ALL_KINDS),
        PropertySpec(key="template", label="Template", kind=STRING, default="{value}",
                     help="Must contain the literal text {value} -- replaced with the input, "
                          "formatted to whole numbers if it's numeric."),
        PropertySpec(key="decimals", label="Decimal places", kind=INT, default=0, minimum=0, maximum=4,
                     help="Only applies when Input is a numeric source."),
    ],
))

# ---------------------------------------------------------------------------
# Extra logic — common HUD math without plugins or custom Lua
# ---------------------------------------------------------------------------

register(NodeSpec(
    type="logic.map_range", category="logic", label="Map Range", color=LOGIC_COLOR, icon="math",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Remap a number from one range into another (e.g. 0–100 °C → 0–1, or sensor raw → percent). "
                "Clamps to the output range by default.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=50.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9, group="Input"),
        PropertySpec(key="in_min", label="In min", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9, group="Input range"),
        PropertySpec(key="in_max", label="In max", kind=FLOAT, default=100.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9, group="Input range"),
        PropertySpec(key="out_min", label="Out min", kind=FLOAT, default=0.0, group="Output range"),
        PropertySpec(key="out_max", label="Out max", kind=FLOAT, default=1.0, group="Output range"),
        PropertySpec(key="clamp", label="Clamp to output range", kind=BOOL, default=True, group="Output range"),
    ],
))

register(NodeSpec(
    type="logic.clamp", category="logic", label="Clamp", color=LOGIC_COLOR, icon="math",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Force a value into [Min, Max]. Useful before gauges that assume 0–100.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=50.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="min_value", label="Min", kind=FLOAT, default=0.0, group="Range"),
        PropertySpec(key="max_value", label="Max", kind=FLOAT, default=100.0, group="Range"),
    ],
))

register(NodeSpec(
    type="logic.lerp", category="logic", label="Lerp", color=LOGIC_COLOR, icon="math",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Linear interpolate: Out = A + (B − A) × T. T is usually 0–1 from a Map Range or gauge percent.",
    properties=[
        PropertySpec(key="a", label="A", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="b", label="B", kind=FLOAT, default=1.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="t", label="T", kind=FLOAT, default=0.5, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-10, maximum=10, help="Blend factor; 0 → A, 1 → B."),
    ],
))

register(NodeSpec(
    type="logic.threshold", category="logic", label="Threshold Gate", color=LOGIC_COLOR, icon="branch",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Outputs 1 when Value meets the comparison, else 0. Wire into opacity, trigger, or Conditional.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="comparison", label="Comparison", kind=ENUM, default=">=",
                     choices=[">", ">=", "<", "<=", "=="], group="Condition"),
        PropertySpec(key="threshold", label="Threshold", kind=FLOAT, default=80.0, group="Condition"),
    ],
))

register(NodeSpec(
    type="logic.deadzone", category="logic", label="Deadzone", color=LOGIC_COLOR, icon="math",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=False,
    description="Snap values near zero (or a centre) to that centre; quiets noisy sensors.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="centre", label="Centre", kind=FLOAT, default=0.0, group="Deadzone"),
        PropertySpec(key="radius", label="Radius", kind=FLOAT, default=1.0, minimum=0, maximum=1e6, group="Deadzone",
                     help="If |value − centre| ≤ radius, output centre; else pass value through."),
    ],
))

register(NodeSpec(
    type="logic.invert_percent", category="logic", label="Invert Percent", color=LOGIC_COLOR, icon="math",
    subcategory="Logic", output_kind=KIND_PERCENT, simple_mode=True,
    description="100 − value (clamped 0–100). Free space from used disk, remaining battery style math.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=40.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
    ],
))

register(NodeSpec(
    type="logic.scale", category="logic", label="Scale / Offset", color=LOGIC_COLOR, icon="math",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="out = value × multiply + add. Unit tweaks without a full Map Range.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=1.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="multiply", label="Multiply", kind=FLOAT, default=1.0, group="Transform"),
        PropertySpec(key="add", label="Add", kind=FLOAT, default=0.0, group="Transform"),
    ],
))

register(NodeSpec(
    type="logic.round", category="logic", label="Round", color=LOGIC_COLOR, icon="math",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Round to N decimal places (0 = integer).",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="decimals", label="Decimals", kind=INT, default=0, minimum=0, maximum=6, group="Format"),
    ],
))

register(NodeSpec(
    type="logic.abs", category="logic", label="Absolute", color=LOGIC_COLOR, icon="math",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Absolute value |x|.",
    properties=[
        PropertySpec(key="value", label="Value", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
    ],
))

register(NodeSpec(
    type="logic.boolean_and", category="logic", label="AND Gate", color=LOGIC_COLOR, icon="branch",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Outputs 1 if both inputs are non-zero (truthy), else 0. Chain threshold gates.",
    properties=[
        PropertySpec(key="input_a", label="A", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="input_b", label="B", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
    ],
))

register(NodeSpec(
    type="logic.boolean_or", category="logic", label="OR Gate", color=LOGIC_COLOR, icon="branch",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="Outputs 1 if either input is non-zero, else 0.",
    properties=[
        PropertySpec(key="input_a", label="A", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="input_b", label="B", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
    ],
))

register(NodeSpec(
    type="logic.pick", category="logic", label="Pick A/B", color=LOGIC_COLOR, icon="branch",
    subcategory="Logic", output_kind=KIND_NUMBER, simple_mode=True,
    description="If Selector ≥ 0.5 output B, else A. Use with a Threshold Gate for mode switches.",
    properties=[
        PropertySpec(key="selector", label="Selector", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="input_a", label="A", kind=FLOAT, default=0.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
        PropertySpec(key="input_b", label="B", kind=FLOAT, default=1.0, bindable=True, accepts=NUMERIC_KINDS,
                     minimum=-1e9, maximum=1e9),
    ],
))

