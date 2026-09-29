"""
Extra native source expressions for sources_extra.py.

In lua_gen._native_source_expr, before the final raise / fallback:

    from conkystudio.codegen.source_generators_extra import extra_native_source_expr
    extra = extra_native_source_expr(node)
    if extra is not None:
        return extra
"""
from __future__ import annotations

from conkystudio.codegen.lua_gen import lua_string_literal


def extra_native_source_expr(node) -> tuple[str, str] | None:
    t = node.type
    p = node.props

    if t == "source.loadavg":
        which = p.get("which", "all")
        if which == "all":
            return f"safe_parse('${{loadavg}}', '')", "text"
        idx = {"1": 1, "5": 2, "15": 3}.get(str(which), 1)
        return (
            f"(function() local s = safe_parse('${{loadavg}}', '0 0 0'); "
            f"local a,b,c = s:match('([%d%.]+)%s+([%d%.]+)%s+([%d%.]+)'); "
            f"local t = {{a, b, c}}; local v = t[{idx}]; "
            f"return (v ~= nil and tostring(v)) or s end)()",
            "text",
        )

    if t == "source.threads":
        return (
            f"safe_number('${{threads}}', SRC[{lua_string_literal(node.id)}] or 0)",
            "number",
        )

    if t == "source.running_processes":
        return (
            f"safe_number('${{running_processes}}', SRC[{lua_string_literal(node.id)}] or 0)",
            "number",
        )

    return None
