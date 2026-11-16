"""Optional native sources from Conky variables (no scripts)."""
from __future__ import annotations

from conkystudio.nodes.registry import (
    NodeSpec, PropertySpec, register, ENUM, KIND_TEXT, KIND_NUMBER, KIND_PERCENT,
)

SOURCE_COLOR = "#3fa796"

register(NodeSpec(
    type="source.loadavg", category="source", label="Load Average",
    color=SOURCE_COLOR, icon="list", output_kind=KIND_TEXT, subcategory="System Info",
    description="${loadavg} — 1 / 5 / 15 minute load averages as text.",
    properties=[
        PropertySpec(
            key="which", label="Which", kind=ENUM, default="all",
            choices=["all", "1", "5", "15"],
            choice_labels=["All (1 5 15)", "1-minute", "5-minute", "15-minute"],
            help="Conky prints all three together; 'all' uses ${loadavg}. "
                 "Single buckets use the first/second/third field via exec parse in codegen if needed — "
                 "prefer 'all' for a text label.",
        ),
    ],
))

register(NodeSpec(
    type="source.threads", category="source", label="Thread Count",
    color=SOURCE_COLOR, icon="list", output_kind=KIND_NUMBER, subcategory="System Info",
    description="${threads} — number of threads.",
    properties=[],
))

register(NodeSpec(
    type="source.running_processes", category="source", label="Running Processes",
    color=SOURCE_COLOR, icon="list", output_kind=KIND_NUMBER, subcategory="System Info",
    description="${running_processes} — processes in running state.",
    properties=[],
))
