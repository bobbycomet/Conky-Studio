"""
Conky Studio Lua code generator.

Turns a Project node graph into render.lua: framework helpers, refresh_sources(),
per-node draw_* functions, and main_draw().

IMPORTANT: This module must NEVER call register(NodeSpec(...)).
NodeSpecs live only in conkystudio.nodes.visuals* / sources* / logic*.
A packaging mistake that shipped visuals.py under this path caused the
duplicate visual.arc_gauge startup crash.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from conkystudio.codegen.lua_framework import FRAMEWORK_LUA
from conkystudio.codegen.color import lua_rgb_literal, lua_set_source, lua_destroy_gradient_if_needed
from conkystudio.codegen.gradient_integration import (
    fill_source_lua,
    wrap_blend_lua,
    apply_scale_to_draw_function,
)
from conkystudio.nodes import registry


def _lua_fill_source(
    props: dict,
    *,
    box=None,
    radial=None,
    alpha=1,
    color_key: str = "color",
    cr: str = "cr",
):
    """Compatibility wrapper: every core visual fill goes through the unified
    gradient pipeline (``fill_source_lua`` → ``lua_set_source``).

    Kept under this name so older generators / call sites that still say
    ``_lua_fill_source(...)`` need no rewrites. New code should call
    ``fill_source_lua`` directly.
    """
    return fill_source_lua(
        props,
        color_key=color_key,
        alpha=alpha,
        box=box,
        radial=radial,
        cr=cr,
    )


# ---------------------------------------------------------------------------
# Decorator tables — extension modules (visual_generators_*, logic_generators_*)
# call these after import via extensions_bootstrap.
# ---------------------------------------------------------------------------

_VISUAL_GENERATORS: dict[str, Callable] = {}
_LOGIC_GENERATORS: dict[str, Callable] = {}


def visual_generator(type_id: str):
    """Register a function (node, ctx) -> lua_source that emits one draw_* fn."""

    def deco(fn):
        _VISUAL_GENERATORS[type_id] = fn
        return fn

    return deco


def logic_generator(type_id: str):
    """Register a function (node, ctx) -> lua_expression for logic node output."""

    def deco(fn):
        _LOGIC_GENERATORS[type_id] = fn
        return fn

    return deco


def lua_safe_id(node_id: str) -> str:
    """Sanitize a node id for use inside a Lua identifier."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(node_id))
    if not s or s[0].isdigit():
        s = "n_" + s
    return s


def lua_string_literal(value: Any) -> str:
    """Python value → Lua single-quoted string literal."""
    s = "" if value is None else str(value)
    s = s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
    return f"'{s}'"


def lua_literal(value: Any) -> str:
    """Python number/bool/str → Lua literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(float(value) if isinstance(value, float) else int(value))
    if value is None:
        return "nil"
    return lua_string_literal(value)


def has_clickable_nodes(project) -> bool:
    """True if any visual might need lua_mouse_hook (reserved for future click targets)."""
    for n in getattr(project, "nodes", []) or []:
        if getattr(n, "type", "").startswith("visual.") and n.props.get("clickable"):
            return True
    return False


def assert_full_coverage() -> None:
    """Ensure every registered visual type has a generator (stub if needed).

    Missing generators get a no-op draw function so a partial install still
    builds rather than aborting Build & Run.
    """
    for spec in registry.by_category("visual"):
        if spec.type not in _VISUAL_GENERATORS:
            _VISUAL_GENERATORS[spec.type] = _make_stub_visual(spec.type)


def _make_stub_visual(type_id: str):
    def _stub(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        return (
            f"local function {fn}(cr, W, H)\n"
            f"    -- stub: no generator for {type_id}\n"
            f"end"
        )

    return _stub


# ---------------------------------------------------------------------------
# Resolve context — bindable props → Lua expressions
# ---------------------------------------------------------------------------

class ResolveContext:
    def __init__(self, project, script_filenames: dict | None = None):
        self.project = project
        self.script_filenames = script_filenames or {}
        self._edge_index: dict[tuple[str, str], Any] = {}
        for e in getattr(project, "edges", []) or []:
            # Edge may be object or dict-like
            src = getattr(e, "src_node", None) or getattr(e, "src", None)
            dst = getattr(e, "dst_node", None) or getattr(e, "dst", None)
            prop = getattr(e, "prop_key", None) or getattr(e, "prop", None) or getattr(e, "dst_prop", None)
            if src and dst and prop:
                self._edge_index[(str(dst), str(prop))] = str(src)

    def edge_src(self, node, prop_key: str) -> Optional[str]:
        nid = str(node.id)
        if (nid, prop_key) in self._edge_index:
            return self._edge_index[(nid, prop_key)]
        # Project helper if present
        edge_fn = getattr(self.project, "edge_for_prop", None)
        if callable(edge_fn):
            e = edge_fn(node.id, prop_key)
            if e is not None:
                return str(getattr(e, "src_node", e))
        return None

    def resolve(self, node, prop_key: str, default: Any = None) -> str:
        """Return a Lua expression for this property (wired source or literal)."""
        src_id = self.edge_src(node, prop_key)
        if src_id is not None:
            return f"(SRC[{lua_string_literal(src_id)}] or 0)"
        val = node.props.get(prop_key, default)
        if val is None:
            val = default
        if isinstance(val, bool):
            return "true" if val else "false"
        if isinstance(val, (int, float)):
            return repr(float(val) if isinstance(val, float) else int(val))
        return lua_string_literal(val)


# ---------------------------------------------------------------------------
# Native + scripted source expressions
# ---------------------------------------------------------------------------

def _native_source_expr(node) -> tuple[str, str]:
    """Return (lua_expr, kind) for a source node. kind is 'number' or 'text'."""
    t = node.type
    p = node.props

    # Optional extras
    try:
        from conkystudio.codegen.source_generators_extra import extra_native_source_expr

        extra = extra_native_source_expr(node)
        if extra is not None:
            return extra
    except Exception:
        pass

    if t == "source.cpu_percent":
        core = p.get("core", "overall")
        if core and core != "overall":
            return f"safe_number('${{cpu {core}}}', 0)", "number"
        return "safe_number('${cpu}', 0)", "number"

    if t == "source.ram_percent":
        return "safe_number('${memperc}', 0)", "number"

    if t == "source.disk_percent":
        path = p.get("mount_path", "/") or "/"
        return f"safe_number('${{fs_used_perc {path}}}', 0)", "number"

    if t == "source.net_down":
        return (
            "(function() local iface = resolve_net_iface(); "
            "return safe_number('${downspeedf ' .. iface .. '}', 0) end)()",
            "number",
        )

    if t == "source.net_up":
        return (
            "(function() local iface = resolve_net_iface(); "
            "return safe_number('${upspeedf ' .. iface .. '}', 0) end)()",
            "number",
        )

    if t == "source.uptime":
        fmt = p.get("format", "short")
        var = "uptime_short" if fmt == "short" else "uptime"
        return f"safe_parse('${{{var}}}', '')", "text"

    if t == "source.hostname":
        return "safe_parse('${nodename}', '')", "text"

    if t == "source.kernel":
        return "safe_parse('${kernel}', '')", "text"

    if t == "source.process_count":
        return "safe_number('${processes}', 0)", "number"

    if t == "source.battery_percent":
        dev = p.get("device", "BAT0") or "BAT0"
        return (
            f"(function() if not battery_exists({lua_string_literal(dev)}) then return 0 end; "
            f"return safe_number('${{battery_percent {dev}}}', 0) end)()",
            "number",
        )

    if t == "source.greeting":
        return "greeting_for_hour(tonumber(os.date('%H')))", "text"

    if t == "source.datetime":
        fmt = p.get("strftime_format", "%A, %B %d  %H:%M") or "%A, %B %d  %H:%M"
        # Prefer Conky ${time} when possible; fall back to os.date
        return f"safe_parse('${{time {fmt}}}', os.date({lua_string_literal(fmt)}))", "text"

    if t == "source.cpu_freq":
        core = p.get("core", "overall")
        if core and core != "overall":
            n = core.replace("cpu", "")
            return f"safe_number('${{freq {n}}}', 0)", "number"
        return "safe_number('${freq}', 0)", "number"

    if t == "source.ram_used":
        return "safe_parse('${mem}', '')", "text"

    if t == "source.ram_total":
        return "safe_parse('${memmax}', '')", "text"

    if t == "source.swap_percent":
        return "safe_number('${swapperc}', 0)", "number"

    if t in ("source.top_process_name",):
        rank = p.get("rank", "1")
        return f"safe_parse('${{top name {rank}}}', '')", "text"

    if t == "source.top_process_cpu":
        rank = p.get("rank", "1")
        return f"safe_number('${{top cpu {rank}}}', 0)", "number"

    if t == "source.top_process_mem":
        rank = p.get("rank", "1")
        return f"safe_number('${{top mem {rank}}}', 0)", "number"

    # Scripted / external families — read from CACHE_KV after refresh
    try:
        spec = registry.get(t)
    except Exception:
        return "0", "number"

    if getattr(spec, "scripted", False) or getattr(spec, "script_family", None):
        family = spec.script_family or node.id
        key = spec.script_output_key or "value"
        cache_name = f"{family}.cache"
        return (
            f"(CACHE_KV[{lua_string_literal(cache_name)}] "
            f"and CACHE_KV[{lua_string_literal(cache_name)}][{lua_string_literal(key)}]) or 0",
            "number" if (spec.output_kind or "") != "text" else "text",
        )

    # Fallback: previous SRC value
    return f"(SRC[{lua_string_literal(node.id)}] or 0)", "number"


def _scripted_refresh_line(node, script_filenames: dict) -> Optional[str]:
    """Emit Lua that re-reads a daemon cache or runs execi for this source."""
    try:
        spec = registry.get(node.type)
    except Exception:
        return None
    if not (getattr(spec, "scripted", False) or getattr(spec, "script_family", None)):
        return None
    family = spec.script_family or node.id
    mode = node.props.get("poll_mode", "execi")
    interval = int(node.props.get("poll_interval", 5) or 5)
    filename = script_filenames.get(family) or script_filenames.get(node.id) or f"{family}.sh"
    key = spec.script_output_key or "value"
    cache_name = f"{family}.cache"

    if mode == "daemon":
        return (
            f"    do local path = THEME_DIR .. '/.runtime-cache/{cache_name}'; "
            f"CACHE_KV[{lua_string_literal(cache_name)}] = read_kv_cache(path); "
            f"local t = CACHE_KV[{lua_string_literal(cache_name)}]; "
            f"SRC[{lua_string_literal(node.id)}] = (t and t[{lua_string_literal(key)}]) or SRC[{lua_string_literal(node.id)}] or 0 end"
        )
    # execi-style: Conky variable via conky_parse.
    # Do NOT put double-quotes around the script path. Conky feeds the
    # remainder of ${execi …} to sh -c; extra quotes produce
    # "sh: 1: Syntax error: Unterminated quoted string". Use an explicit
    # bash interpreter so bashisms in the script are honoured (Conky's
    # shell is always sh, often dash).
    return (
        f"    SRC[{lua_string_literal(node.id)}] = safe_parse("
        f"'${{execi {interval} bash ' .. THEME_DIR .. '/scripts/{filename} --key {key}}}', "
        f"SRC[{lua_string_literal(node.id)}] or '')"
    )


# ---------------------------------------------------------------------------
# Built-in logic generators
# ---------------------------------------------------------------------------

@logic_generator("logic.math")
def _logic_math(node, ctx):
    a = ctx.resolve(node, "input_a")
    b = ctx.resolve(node, "input_b")
    op = str(node.props.get("operation", "add"))
    if op == "add":
        return f"((tonumber({a}) or 0) + (tonumber({b}) or 0))"
    if op == "subtract":
        return f"((tonumber({a}) or 0) - (tonumber({b}) or 0))"
    if op == "multiply":
        return f"((tonumber({a}) or 0) * (tonumber({b}) or 0))"
    if op == "divide":
        return f"(function() local b = tonumber({b}) or 0; if b == 0 then return 0 end; return (tonumber({a}) or 0) / b end)()"
    if op == "average":
        return f"(((tonumber({a}) or 0) + (tonumber({b}) or 0)) / 2)"
    if op == "min":
        return f"math.min(tonumber({a}) or 0, tonumber({b}) or 0)"
    if op == "max":
        return f"math.max(tonumber({a}) or 0, tonumber({b}) or 0)"
    return f"(tonumber({a}) or 0)"


@logic_generator("logic.conditional")
def _logic_conditional(node, ctx):
    inp = ctx.resolve(node, "input")
    cmp = str(node.props.get("comparison", ">"))
    thr = float(node.props.get("threshold", 80.0) or 80.0)
    then_v = float(node.props.get("then_value", 1.0) or 1.0)
    else_v = float(node.props.get("else_value", 0.0) or 0.0)
    return (
        f"((tonumber({inp}) or 0) {cmp} {thr} and {then_v} or {else_v})"
    )


@logic_generator("logic.string_format")
def _logic_string_format(node, ctx):
    inp = ctx.resolve(node, "input")
    tmpl = str(node.props.get("template", "{value}") or "{value}")
    dec = int(node.props.get("decimals", 0) or 0)
    # Replace {value} in template
    lit = lua_string_literal(tmpl)
    return (
        f"(function() local v = {inp}; local s; "
        f"if type(v) == 'number' or tonumber(v) then s = string.format('%." + str(dec) + f"f', tonumber(v) or 0) "
        f"else s = tostring(v or '') end; "
        f"return (string.gsub({lit}, '{{value}}', s)) end)()"
    )


@logic_generator("logic.map_range")
def _logic_map_range(node, ctx):
    v = ctx.resolve(node, "value")
    in_min = ctx.resolve(node, "in_min")
    in_max = ctx.resolve(node, "in_max")
    out_min = float(node.props.get("out_min", 0.0) or 0.0)
    out_max = float(node.props.get("out_max", 1.0) or 1.0)
    do_clamp = bool(node.props.get("clamp", True))
    body = (
        f"(function() local v = tonumber({v}) or 0; "
        f"local lo, hi = tonumber({in_min}) or 0, tonumber({in_max}) or 100; "
        f"if hi == lo then return {out_min} end; "
        f"local t = (v - lo) / (hi - lo); "
    )
    if do_clamp:
        body += "t = clamp(t, 0, 1); "
    body += f"return {out_min} + ({out_max} - {out_min}) * t end)()"
    return body


@logic_generator("logic.clamp")
def _logic_clamp(node, ctx):
    v = ctx.resolve(node, "value")
    lo = float(node.props.get("min_value", 0.0) or 0.0)
    hi = float(node.props.get("max_value", 100.0) or 100.0)
    return f"clamp(tonumber({v}) or 0, {lo}, {hi})"


@logic_generator("logic.lerp")
def _logic_lerp(node, ctx):
    a = ctx.resolve(node, "a")
    b = ctx.resolve(node, "b")
    t = ctx.resolve(node, "t")
    return f"lerp(tonumber({a}) or 0, tonumber({b}) or 0, tonumber({t}) or 0)"


@logic_generator("logic.threshold")
def _logic_threshold(node, ctx):
    v = ctx.resolve(node, "value")
    cmp = str(node.props.get("comparison", ">="))
    thr = float(node.props.get("threshold", 80.0) or 80.0)
    return f"(((tonumber({v}) or 0) {cmp} {thr}) and 1 or 0)"


@logic_generator("logic.invert_percent")
def _logic_invert_percent(node, ctx):
    v = ctx.resolve(node, "value")
    return f"clamp(100 - (tonumber({v}) or 0), 0, 100)"


@logic_generator("logic.scale")
def _logic_scale(node, ctx):
    v = ctx.resolve(node, "value")
    m = float(node.props.get("multiply", 1.0) or 1.0)
    a = float(node.props.get("add", 0.0) or 0.0)
    return f"((tonumber({v}) or 0) * {m} + {a})"


@logic_generator("logic.round")
def _logic_round(node, ctx):
    v = ctx.resolve(node, "value")
    d = int(node.props.get("decimals", 0) or 0)
    if d <= 0:
        return f"math.floor((tonumber({v}) or 0) + 0.5)"
    return f"(function() local m = 10^{d}; return math.floor(((tonumber({v}) or 0) * m) + 0.5) / m end)()"


@logic_generator("logic.abs")
def _logic_abs(node, ctx):
    v = ctx.resolve(node, "value")
    return f"math.abs(tonumber({v}) or 0)"


@logic_generator("logic.boolean_and")
def _logic_and(node, ctx):
    a = ctx.resolve(node, "input_a")
    b = ctx.resolve(node, "input_b")
    return f"((((tonumber({a}) or 0) ~= 0) and ((tonumber({b}) or 0) ~= 0)) and 1 or 0)"


@logic_generator("logic.boolean_or")
def _logic_or(node, ctx):
    a = ctx.resolve(node, "input_a")
    b = ctx.resolve(node, "input_b")
    return f"((((tonumber({a}) or 0) ~= 0) or ((tonumber({b}) or 0) ~= 0)) and 1 or 0)"


@logic_generator("logic.pick")
def _logic_pick(node, ctx):
    sel = ctx.resolve(node, "selector")
    a = ctx.resolve(node, "input_a")
    b = ctx.resolve(node, "input_b")
    return f"(((tonumber({sel}) or 0) >= 0.5) and (tonumber({b}) or 0) or (tonumber({a}) or 0))"


@logic_generator("logic.deadzone")
def _logic_deadzone(node, ctx):
    v = ctx.resolve(node, "value")
    centre = float(node.props.get("centre", 0.0) or 0.0)
    radius = float(node.props.get("radius", 1.0) or 1.0)
    return (
        f"(function() local v = tonumber({v}) or 0; "
        f"if math.abs(v - {centre}) <= {radius} then return {centre} end; return v end)()"
    )


# ---------------------------------------------------------------------------
# Built-in visual generators (core set; extensions add more)
# ---------------------------------------------------------------------------

def _split_rgb(hex_str: str):
    return tuple(lua_rgb_literal(hex_str).split(", "))


@visual_generator("visual.text")
def _gen_text(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    value = ctx.resolve(node, "value")
    prefix = lua_string_literal(p.get("prefix", "") or "")
    suffix = lua_string_literal(p.get("suffix", "") or "")
    decimals = int(p.get("decimals", 0) or 0)
    align = str(p.get("align", "left") or "left")
    family = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
    size = int(p.get("font_size", 16) or 16)
    bold = bool(p.get("bold", False))
    italic = bool(p.get("italic", False))
    r, g, b = _split_rgb(p.get("color", "#FFFFFF"))
    halo = "true" if p.get("halo") else "false"
    return f"""local function {fn}(cr, W, H)
    local raw = {value}
    local text
    if type(raw) == 'number' or tonumber(raw) then
        text = string.format('%.{decimals}f', tonumber(raw) or 0)
    else
        text = tostring(raw or '')
    end
    text = {prefix} .. text .. {suffix}
    studio_draw_text(cr, text, {x}, {y}, {{
        family = '{family}', size = {size},
        bold = {'true' if bold else 'false'}, italic = {'true' if italic else 'false'},
        r = {r}, g = {g}, b = {b}, a = 1, align = '{align}', halo = {halo}
    }})
end"""


def _wrap_fn_body(fn: str, body_lines: list[str], props: dict) -> str:
    """Build `local function fn(...) ... end` with optional blend only on the body."""
    body = "\n".join(body_lines)
    body = wrap_blend_lua(body, props)
    indented = "\n".join(("    " + ln if ln.strip() else ln) for ln in body.splitlines())
    return f"local function {fn}(cr, W, H)\n{indented}\nend"


@visual_generator("visual.rectangle")
def _gen_rectangle(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    w, h = int(p.get("width", 160)), int(p.get("height", 80))
    rad = int(p.get("corner_radius", 0) or 0)
    opacity = float(p.get("opacity", 1.0) or 1.0)
    do_fill = bool(p.get("fill", True))
    do_stroke = bool(p.get("stroke", True))
    lw = float(p.get("line_width", 1.5) or 1.5)
    sr, sg, sb = _split_rgb(p.get("stroke_color", "#26fdf1"))
    setup, destroy = fill_source_lua(p, box=(x, y, w, h), alpha=opacity)
    body = [
        f"local x, y, w, h = {x}, {y}, {w}, {h}",
        f"rounded_rect(cr, x, y, w, h, {rad})",
    ]
    if do_fill:
        body.append(setup)
        body.append("cairo_fill_preserve(cr)" if do_stroke else "cairo_fill(cr)")
        if destroy:
            body.append(destroy)
    if do_stroke:
        body += [
            f"cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})",
            f"cairo_set_line_width(cr, {lw})",
            "cairo_stroke(cr)",
        ]
    elif not do_fill:
        body.append("cairo_new_path(cr)")
    return _wrap_fn_body(fn, body, p)


@visual_generator("visual.bar")
def _gen_bar(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    width = int(p.get("width", 220))
    height = int(p.get("height", 18))
    orient = str(p.get("orientation", "horizontal") or "horizontal").lower()
    vertical = orient == "vertical"
    style = str(p.get("style", "solid") or "solid").lower()
    segs = max(2, int(p.get("segment_count", 22) or 22))
    rad = int(p.get("corner_radius", 4) or 0)
    min_v = float(p.get("min_value", 0) or 0)
    max_v = float(p.get("max_value", 100) or 100)
    value = ctx.resolve(node, "value")
    tr, tg, tb = _split_rgb(p.get("track_color", "#33313a"))
    setup, destroy = fill_source_lua(p, box=(x, y, width, height), alpha=1)
    setup_indented = setup.replace("\n", "\n        ")
    body = [
        f"local x, y, w, h = {x}, {y}, {width}, {height}",
        f"local min_v, max_v = {min_v}, {max_v}",
        f"local val = tonumber({value}) or min_v",
        f"local pct = clamp((val - min_v) / math.max(max_v - min_v, 1e-9), 0, 1)",
        f"cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, 1)",
    ]

    if style == "trapezoid":
        if vertical:
            # Vertical: full track, then clip fill growing upward from the bottom.
            body += [
                "bar_trapezoid_path(cr, x, y, w, h)",
                "cairo_fill(cr)",
                setup,
                "local fh = h * pct",
                "if fh > 0.5 then",
                "    cairo_save(cr)",
                "    cairo_rectangle(cr, x, y + h - fh, w, fh)",
                "    cairo_clip(cr)",
                "    bar_trapezoid_path(cr, x, y, w, h)",
                "    cairo_fill(cr)",
                "    cairo_restore(cr)",
                "end",
            ]
        else:
            body += [
                "bar_trapezoid_path(cr, x, y, w, h)",
                "cairo_fill(cr)",
                setup,
                "local fw = w * pct",
                "if fw > 0.5 then bar_trapezoid_path(cr, x, y, fw, h); cairo_fill(cr) end",
            ]
    elif style == "segmented":
        if vertical:
            # Stack segments bottom -> top; light from the bottom.
            body += [
                f"local segs, gap = {segs}, 2",
                "local sh = (h - gap * (segs - 1)) / segs",
                "local lit = math.floor(pct * segs + 1e-6)",
                "for i = 1, segs do",
                "    local sy = y + h - i * sh - (i - 1) * gap",
                f"    cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, 1)",
                "    cairo_rectangle(cr, x, sy, w, sh); cairo_fill(cr)",
                "    if i <= lit then",
                "        " + setup_indented,
                "        cairo_rectangle(cr, x, sy, w, sh); cairo_fill(cr)",
                "    end",
                "end",
            ]
        else:
            body += [
                f"local segs, gap = {segs}, 2",
                "local sw = (w - gap * (segs - 1)) / segs",
                "local lit = math.floor(pct * segs + 1e-6)",
                "for i = 1, segs do",
                "    local sx = x + (i - 1) * (sw + gap)",
                f"    cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, 1)",
                "    cairo_rectangle(cr, sx, y, sw, h); cairo_fill(cr)",
                "    if i <= lit then",
                "        " + setup_indented,
                "        cairo_rectangle(cr, sx, y, sw, h); cairo_fill(cr)",
                "    end",
                "end",
            ]
    else:
        # solid
        if vertical:
            body += [
                f"rounded_rect(cr, x, y, w, h, {rad}); cairo_fill(cr)",
                setup,
                "local fh = h * pct",
                f"if fh > 0.5 then rounded_rect(cr, x, y + h - fh, w, fh, {rad}); cairo_fill(cr) end",
            ]
        else:
            body += [
                f"rounded_rect(cr, x, y, w, h, {rad}); cairo_fill(cr)",
                setup,
                "local fw = w * pct",
                f"if fw > 0.5 then rounded_rect(cr, x, y, fw, h, {rad}); cairo_fill(cr) end",
            ]
    if destroy:
        body.append(destroy)
    return _wrap_fn_body(fn, body, p)

@visual_generator("visual.arc_gauge")
def _gen_arc_gauge(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    radius = int(p.get("radius", 70))
    thick = int(p.get("thickness", 10))
    start = float(p.get("start_angle_deg", -90) or -90)
    sweep = float(p.get("sweep_deg", 360) or 360)
    min_v = float(p.get("min_value", 0) or 0)
    max_v = float(p.get("max_value", 100) or 100)
    value = ctx.resolve(node, "value")
    tr, tg, tb = _split_rgb(p.get("track_color", "#33313a"))
    ta = float(p.get("track_alpha", 0.6) or 0.6)
    cap = "CAIRO_LINE_CAP_ROUND" if p.get("cap_style", "round") == "round" else "CAIRO_LINE_CAP_BUTT"
    show = bool(p.get("show_value_text", True))
    fsize = int(p.get("value_font_size", 20) or 20)
    suffix = lua_string_literal(p.get("value_suffix", "%") or "")
    setup, destroy = fill_source_lua(
        p, radial=(cx, cy, radius), box=(cx - radius, cy - radius, radius * 2, radius * 2), alpha=1
    )
    body = [
        f"local cx, cy, R = {cx}, {cy}, {radius}",
        f"local min_v, max_v = {min_v}, {max_v}",
        f"local val = tonumber({value}) or min_v",
        f"local pct = clamp((val - min_v) / math.max(max_v - min_v, 1e-9), 0, 1)",
        f"local start_a, sweep = {start}, {sweep}",
        f"cairo_set_line_width(cr, {thick})",
        f"cairo_set_line_cap(cr, {cap})",
        f"cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, {ta})",
        "cairo_new_sub_path(cr)",
        "cairo_arc(cr, cx, cy, R, math.rad(start_a), math.rad(start_a + sweep))",
        "cairo_stroke(cr)",
        setup,
        "cairo_new_sub_path(cr)",
        "cairo_arc(cr, cx, cy, R, math.rad(start_a), math.rad(start_a + sweep * pct))",
        "cairo_stroke(cr)",
    ]
    if destroy:
        body.append(destroy)
    if show:
        body.append(
            f"studio_draw_text(cr, string.format('%.0f', val) .. {suffix}, cx, cy, "
            f"{{size = {fsize}, align = 'center', r = 1, g = 1, b = 1, a = 1}})"
        )
    return _wrap_fn_body(fn, body, p)


@visual_generator("visual.ring_track")
def _gen_ring_track(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    radius = int(p.get("radius", 70))
    thick = int(p.get("thickness", 8))
    start = float(p.get("start_angle_deg", -90) or -90)
    sweep = float(p.get("sweep_deg", 360) or 360)
    opacity = float(p.get("opacity", 0.7) or 0.7)
    cap = "CAIRO_LINE_CAP_ROUND" if p.get("cap_style", "round") == "round" else "CAIRO_LINE_CAP_BUTT"
    setup, destroy = fill_source_lua(
        p, radial=(cx, cy, radius), box=(cx - radius, cy - radius, radius * 2, radius * 2), alpha=opacity
    )
    lines = [
        f"local function {fn}(cr, W, H)",
        f"    cairo_set_line_width(cr, {thick})",
        f"    cairo_set_line_cap(cr, {cap})",
        "    " + setup.replace("\n", "\n    "),
        f"    cairo_new_sub_path(cr)",
        f"    cairo_arc(cr, {cx}, {cy}, {radius}, math.rad({start}), math.rad({start + sweep}))",
        "    cairo_stroke(cr)",
    ]
    if destroy:
        lines.append(f"    {destroy}")
    lines.append("end")
    return "\n".join(lines)


@visual_generator("visual.hline")
def _gen_hline(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 40))
    length = int(p.get("length", 200))
    lw = float(p.get("line_width", 1.5) or 1.5)
    opacity = float(p.get("opacity", 0.85) or 0.85)
    r, g, b = _split_rgb(p.get("color", "#26fdf1"))
    return f"""local function {fn}(cr, W, H)
    cairo_set_line_width(cr, {lw})
    cairo_set_source_rgba(cr, {r}, {g}, {b}, {opacity})
    cairo_move_to(cr, {x}, {y})
    cairo_line_to(cr, {x + length}, {y})
    cairo_stroke(cr)
end"""


@visual_generator("visual.vline")
def _gen_vline(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 40)), int(p.get("y", 20))
    length = int(p.get("length", 120))
    lw = float(p.get("line_width", 1.5) or 1.5)
    opacity = float(p.get("opacity", 0.85) or 0.85)
    r, g, b = _split_rgb(p.get("color", "#26fdf1"))
    return f"""local function {fn}(cr, W, H)
    cairo_set_line_width(cr, {lw})
    cairo_set_source_rgba(cr, {r}, {g}, {b}, {opacity})
    cairo_move_to(cr, {x}, {y})
    cairo_line_to(cr, {x}, {y + length})
    cairo_stroke(cr)
end"""


@visual_generator("visual.crosshair")
def _gen_crosshair(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    size = int(p.get("size", 24))
    gap = int(p.get("gap", 4))
    lw = float(p.get("line_width", 1.5) or 1.5)
    opacity = float(p.get("opacity", 0.9) or 0.9)
    r, g, b = _split_rgb(p.get("color", "#26fdf1"))
    return f"""local function {fn}(cr, W, H)
    local cx, cy, s, g = {cx}, {cy}, {size}, {gap}
    cairo_set_line_width(cr, {lw})
    cairo_set_source_rgba(cr, {r}, {g}, {b}, {opacity})
    cairo_move_to(cr, cx - s, cy); cairo_line_to(cr, cx - g, cy); cairo_stroke(cr)
    cairo_move_to(cr, cx + g, cy); cairo_line_to(cr, cx + s, cy); cairo_stroke(cr)
    cairo_move_to(cr, cx, cy - s); cairo_line_to(cr, cx, cy - g); cairo_stroke(cr)
    cairo_move_to(cr, cx, cy + g); cairo_line_to(cr, cx, cy + s); cairo_stroke(cr)
end"""


@visual_generator("visual.led_dot")
def _gen_led_dot(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 40)), int(p.get("cy", 40))
    radius = int(p.get("radius", 6))
    thr = float(p.get("threshold", 0.5) or 0.5)
    value = ctx.resolve(node, "value")
    opacity = float(p.get("opacity", 1.0) or 1.0)
    on_r, on_g, on_b = _split_rgb(p.get("color_on", "#4fd1c5"))
    off_r, off_g, off_b = _split_rgb(p.get("color_off", "#33313a"))
    glow = bool(p.get("glow", True))
    glow_lines = ""
    if glow:
        glow_lines = f"""
    if on then
        cairo_set_source_rgba(cr, {on_r}, {on_g}, {on_b}, {opacity} * 0.25)
        cairo_arc(cr, {cx}, {cy}, {radius} * 2.2, 0, 2 * math.pi)
        cairo_fill(cr)
    end"""
    return f"""local function {fn}(cr, W, H)
    local on = (tonumber({value}) or 0) >= {thr}
    {glow_lines}
    if on then cairo_set_source_rgba(cr, {on_r}, {on_g}, {on_b}, {opacity})
    else cairo_set_source_rgba(cr, {off_r}, {off_g}, {off_b}, {opacity}) end
    cairo_arc(cr, {cx}, {cy}, {radius}, 0, 2 * math.pi)
    cairo_fill(cr)
end"""


@visual_generator("visual.image_icon")
def _gen_image_icon(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    size = int(p.get("size", 48))
    opacity = float(p.get("opacity", 1.0) or 1.0)
    path = str(p.get("path", "") or "")
    base = path.split("/")[-1] if path else ""
    rot = ctx.resolve(node, "rotation_deg")
    trigger = ctx.resolve(node, "swap_trigger")
    above = str(p.get("swap_above_path", "") or "").split("/")[-1]
    below = str(p.get("swap_below_path", "") or "").split("/")[-1]
    ath = float(p.get("swap_above_threshold", 70) or 70)
    bth = float(p.get("swap_below_threshold", 35) or 35)
    return f"""local function {fn}(cr, W, H)
    local path = THEME_DIR .. '/images/' .. {lua_string_literal(base)}
    local trig = tonumber({trigger}) or 0
    local above = {lua_string_literal(above)}
    local below = {lua_string_literal(below)}
    if above ~= '' and trig >= {ath} then path = THEME_DIR .. '/images/' .. above end
    if below ~= '' and trig <= {bth} then path = THEME_DIR .. '/images/' .. below end
    local img = load_image_cached(path)
    draw_image_fit(cr, img, {x}, {y}, {size}, tonumber({rot}) or 0, {opacity})
end"""


@visual_generator("visual.glow_pulse")
def _gen_glow_pulse(node, ctx):
    """Soft multi-pass halo: circle, image silhouette, star, or triangle."""
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    radius = float(p.get("radius", 60) or 60)
    layers = max(1, min(12, int(p.get("layers", 4) or 4)))
    spread = float(p.get("spread", 0.35) or 0.35)
    pulse_hz = float(p.get("pulse_hz", 0.5) or 0.5)
    a_min = float(p.get("alpha_min", 0.15) or 0.15)
    a_max = float(p.get("alpha_max", 0.55) or 0.55)
    r, g, b = _split_rgb(p.get("color", "#4fd1c5"))
    trigger = ctx.resolve(node, "trigger")
    thr = float(p.get("trigger_threshold", 80) or 80)
    tmode = str(p.get("trigger_mode", "above") or "above")
    shape = str(p.get("mode", "circle") or "circle").lower()
    path = str(p.get("path", "") or "")
    base = path.split("/")[-1] if path else ""
    star_pts = max(3, min(12, int(p.get("star_points", 5) or 5)))
    star_ir = float(p.get("star_inner_ratio", 0.4) or 0.4)
    lines = [f"local function {fn}(cr, W, H)"]
    if "SRC[" in str(trigger):
        cmp = f">= {thr}" if tmode == "above" else f"<= {thr}"
        lines.append(f"    local trig = tonumber({trigger}) or 0")
        lines.append(f"    if not (trig {cmp}) then return end")
    lines += [
        "    local t = wall_clock()",
        f"    local phase = 0.5 + 0.5 * math.sin(t * {pulse_hz} * 2 * math.pi)",
        f"    local a = {a_min} + ({a_max} - {a_min}) * phase",
    ]
    if shape == "image" and base:
        lines += [
            f"    local img = load_image_cached(THEME_DIR .. '/images/' .. {lua_string_literal(base)})",
            "    if img == nil then return end",
            f"    for i = {layers}, 1, -1 do",
            f"        local scale = 1 + {spread} * (i / {layers})",
            f"        local size = {radius} * 2 * scale",
            f"        local ox = {cx} - size / 2",
            f"        local oy = {cy} - size / 2",
            "        local la = a * (0.45 / i)",
            "        cairo_save(cr)",
            "        draw_image_fit(cr, img, ox, oy, size, 0, la)",
            "        if type(cairo_set_operator) == 'function' and CAIRO_OPERATOR_ATOP ~= nil then",
            "            cairo_set_operator(cr, CAIRO_OPERATOR_ATOP)",
            f"            cairo_set_source_rgba(cr, {r}, {g}, {b}, la * 0.5)",
            "            cairo_rectangle(cr, ox, oy, size, size)",
            "            cairo_fill(cr)",
            "            cairo_set_operator(cr, CAIRO_OPERATOR_OVER)",
            "        end",
            "        cairo_restore(cr)",
            "    end",
        ]
    elif shape == "star":
        lines += [
            f"    for i = {layers}, 1, -1 do",
            f"        local scale = 1 + {spread} * (i / {layers})",
            f"        local outer = {radius} * scale",
            f"        local inner = outer * {star_ir}",
            "        local la = a * (0.4 / i)",
            f"        cairo_set_source_rgba(cr, {r}, {g}, {b}, la)",
            "        cairo_set_line_width(cr, 2.0 + i * 0.6)",
            "        cairo_new_sub_path(cr)",
            f"        for k = 0, {star_pts} * 2 - 1 do",
            f"            local ang = -math.pi / 2 + k * math.pi / {star_pts}",
            "            local rad = (k % 2 == 0) and outer or inner",
            f"            local px = {cx} + math.cos(ang) * rad",
            f"            local py = {cy} + math.sin(ang) * rad",
            "            if k == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end",
            "        end",
            "        cairo_close_path(cr)",
            "        cairo_stroke(cr)",
            "    end",
        ]
    elif shape == "triangle":
        lines += [
            f"    for i = {layers}, 1, -1 do",
            f"        local scale = 1 + {spread} * (i / {layers})",
            f"        local rad = {radius} * scale",
            "        local la = a * (0.4 / i)",
            f"        cairo_set_source_rgba(cr, {r}, {g}, {b}, la)",
            "        cairo_set_line_width(cr, 2.0 + i * 0.6)",
            "        cairo_new_sub_path(cr)",
            "        for k = 0, 2 do",
            "            local ang = -math.pi / 2 + k * 2 * math.pi / 3",
            f"            local px = {cx} + math.cos(ang) * rad",
            f"            local py = {cy} + math.sin(ang) * rad",
            "            if k == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end",
            "        end",
            "        cairo_close_path(cr)",
            "        cairo_stroke(cr)",
            "    end",
        ]
    else:
        lines += [
            f"    for i = {layers}, 1, -1 do",
            f"        local rad = {radius} * (1 + {spread} * (i / {layers}))",
            "        local la = a * (0.35 / i)",
            f"        cairo_set_source_rgba(cr, {r}, {g}, {b}, la)",
            "        cairo_set_line_width(cr, 3 + i)",
            "        cairo_new_sub_path(cr)",
            f"        cairo_arc(cr, {cx}, {cy}, rad, 0, 2 * math.pi)",
            "        cairo_close_path(cr)",
            "        cairo_stroke(cr)",
            "    end",
        ]
    lines.append("    cairo_new_path(cr)")
    lines.append("end")
    return "\n".join(lines)



@visual_generator("visual.spiral")
def _gen_spiral(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    turns = float(p.get("turns", 2.5) or 2.5)
    r0 = float(p.get("radius_start", 8) or 8)
    r1 = float(p.get("radius_end", 90) or 90)
    lw = float(p.get("line_width", 2.0) or 2.0)
    speed = float(p.get("rotation_speed_dps", 30) or 30)
    dash = max(0, int(p.get("dash_count", 0) or 0))
    r, g, b = _split_rgb(p.get("color", "#4fd1c5"))
    if dash > 0:
        return f"""local function {fn}(cr, W, H)
    local cx, cy = {cx}, {cy}
    local rot = wall_clock() * {speed}
    cairo_set_line_width(cr, {lw})
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    cairo_set_source_rgba(cr, {r}, {g}, {b}, 1)
    for i = 0, {dash} - 1 do
        local t = i / {dash}
        local a = math.rad(rot + t * {turns} * 360)
        local rad = {r0} + ({r1} - {r0}) * t
        local px = cx + math.cos(a) * rad
        local py = cy + math.sin(a) * rad
        cairo_new_path(cr)
        cairo_arc(cr, px, py, math.max(0.8, {lw} * 0.55), 0, 2 * math.pi)
        cairo_fill(cr)
    end
end"""
    return f"""local function {fn}(cr, W, H)
    local cx, cy = {cx}, {cy}
    local rot = wall_clock() * {speed}
    local steps = math.max(60, math.floor({turns} * 90))
    cairo_set_line_width(cr, {lw})
    cairo_set_source_rgba(cr, {r}, {g}, {b}, 1)
    cairo_new_sub_path(cr)
    for i = 0, steps do
        local t = i / steps
        local a = math.rad(rot + t * {turns} * 360)
        local rad = {r0} + ({r1} - {r0}) * t
        local px, py = cx + math.cos(a) * rad, cy + math.sin(a) * rad
        if i == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
    end
    cairo_stroke(cr)
end"""



@visual_generator("visual.history_graph")
def _gen_history_graph(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    w, h = int(p.get("width", 200)), int(p.get("height", 60))
    hist = int(p.get("history_length", 48) or 48)
    min_v = float(p.get("min_value", 0) or 0)
    max_v = float(p.get("max_value", 100) or 100)
    value = ctx.resolve(node, "value")
    fill = bool(p.get("fill", True))
    r, g, b = _split_rgb(p.get("color", "#4fd1c5"))
    tr, tg, tb = _split_rgb(p.get("track_color", "#33313a"))
    title = ctx.resolve(node, "title_label")
    tsize = int(p.get("title_font_size", 11) or 11)
    tcr, tcg, tcb = _split_rgb(p.get("title_color", "#9aa2ad"))
    key = lua_string_literal(node.id)
    return f"""local function {fn}(cr, W, H)
    local key = {key}
    local buf = HIST[key]
    if type(buf) ~= 'table' then buf = {{}}; HIST[key] = buf end
    local val = tonumber({value}) or 0
    table.insert(buf, val)
    while #buf > {hist} do table.remove(buf, 1) end
    local x, y, w, h = {x}, {y}, {w}, {h}
    local min_v, max_v = {min_v}, {max_v}
    cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, 0.8)
    cairo_rectangle(cr, x, y, w, h); cairo_stroke(cr)
    local n = #buf
    if n >= 2 then
        cairo_set_line_width(cr, 1.5)
        cairo_set_source_rgba(cr, {r}, {g}, {b}, 1)
        for i = 1, n do
            local px = x + (i - 1) * (w / math.max(n - 1, 1))
            local pct = clamp((buf[i] - min_v) / math.max(max_v - min_v, 1e-9), 0, 1)
            local py = y + h - pct * h
            if i == 1 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
        end
        cairo_stroke_preserve(cr)
        {"cairo_line_to(cr, x + w, y + h); cairo_line_to(cr, x, y + h); cairo_close_path(cr); cairo_set_source_rgba(cr, " + r + ", " + g + ", " + b + ", 0.25); cairo_fill(cr)" if fill else "cairo_new_path(cr)"}
    end
    local title = tostring({title} or '')
    if title ~= '' then
        studio_draw_text(cr, title, x, y - 4, {{size = {tsize}, r = {tcr}, g = {tcg}, b = {tcb}, a = 1}})
    end
end"""


@visual_generator("visual.sparkline")
def _gen_sparkline(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    w, h = int(p.get("width", 120)), int(p.get("height", 28))
    hist = int(p.get("history_length", 32) or 32)
    auto = bool(p.get("auto_scale", True))
    min_v = float(p.get("min_value", 0) or 0)
    max_v = float(p.get("max_value", 100) or 100)
    value = ctx.resolve(node, "value")
    lw = float(p.get("line_width", 1.5) or 1.5)
    fill = bool(p.get("fill", False))
    r, g, b = _split_rgb(p.get("color", "#4fd1c5"))
    key = lua_string_literal(node.id)
    return f"""local function {fn}(cr, W, H)
    local key = {key}
    local buf = HIST[key]
    if type(buf) ~= 'table' then buf = {{}}; HIST[key] = buf end
    table.insert(buf, tonumber({value}) or 0)
    while #buf > {hist} do table.remove(buf, 1) end
    local x, y, w, h = {x}, {y}, {w}, {h}
    local lo, hi = {min_v}, {max_v}
    if {str(auto).lower()} and #buf > 0 then
        lo, hi = buf[1], buf[1]
        for i = 2, #buf do
            if buf[i] < lo then lo = buf[i] end
            if buf[i] > hi then hi = buf[i] end
        end
        if hi <= lo then hi = lo + 1 end
    end
    local n = #buf
    if n >= 2 then
        cairo_set_line_width(cr, {lw})
        cairo_set_source_rgba(cr, {r}, {g}, {b}, 1)
        for i = 1, n do
            local px = x + (i - 1) * (w / math.max(n - 1, 1))
            local pct = clamp((buf[i] - lo) / math.max(hi - lo, 1e-9), 0, 1)
            local py = y + h - pct * h
            if i == 1 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
        end
        cairo_stroke(cr)
    end
end"""


@visual_generator("visual.segmented_gauge")
def _gen_segmented_gauge(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    radius = int(p.get("radius", 70))
    thick = int(p.get("thickness", 12))
    start = float(p.get("start_angle_deg", -90) or -90)
    sweep = float(p.get("sweep_deg", 270) or 270)
    segs = max(2, int(p.get("segment_count", 12) or 12))
    gap = float(p.get("gap_deg", 4) or 4)
    min_v = float(p.get("min_value", 0) or 0)
    max_v = float(p.get("max_value", 100) or 100)
    value = ctx.resolve(node, "value")
    r, g, b = _split_rgb(p.get("color", "#4fd1c5"))
    tr, tg, tb = _split_rgb(p.get("track_color", "#33313a"))
    show = bool(p.get("show_value_text", True))
    fsize = int(p.get("value_font_size", 20) or 20)
    suffix = lua_string_literal(p.get("value_suffix", "%") or "")
    return f"""local function {fn}(cr, W, H)
    local cx, cy, R = {cx}, {cy}, {radius}
    local segs, gap, sweep, start_a = {segs}, {gap}, {sweep}, {start}
    local seg_span = (sweep - gap * segs) / segs
    local val = tonumber({value}) or {min_v}
    local pct = clamp((val - {min_v}) / math.max({max_v} - {min_v}, 1e-9), 0, 1)
    local lit = math.floor(pct * segs + 1e-6)
    cairo_set_line_width(cr, {thick})
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
    for i = 0, segs - 1 do
        local a0 = start_a + i * (seg_span + gap)
        local a1 = a0 + seg_span
        if i < lit then cairo_set_source_rgba(cr, {r}, {g}, {b}, 1)
        else cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, 1) end
        cairo_new_sub_path(cr)
        cairo_arc(cr, cx, cy, R, math.rad(a0), math.rad(a1))
        cairo_stroke(cr)
    end
    {"studio_draw_text(cr, string.format('%.0f', val) .. " + suffix + f", cx, cy, {{size = {fsize}, align = 'center', r = 1, g = 1, b = 1, a = 1}})" if show else ""}
end"""


@visual_generator("visual.custom_lua")
def _gen_custom_lua(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    code = str(p.get("code", "") or "")
    ox, oy = int(p.get("x", 0) or 0), int(p.get("y", 0) or 0)
    no_translate = bool(p.get("no_translate", False))
    run_mode = str(p.get("run_mode", "draw") or "draw")
    if run_mode == "module":
        # Module nodes run once at load; emit as a one-shot block in build_render_lua
        return f"-- module node {node.id} handled in MODULE_BLOCKS\nlocal function {fn}(cr, W, H) end"

    inputs = []
    for i in range(1, 13):
        expr = ctx.resolve(node, f"input_{i}")
        inputs.append(f"    local in{i} = {expr}")

    props_lit = "{" + ", ".join(
        f"[{lua_string_literal(k)}] = {lua_literal(v)}" for k, v in (p or {}).items() if k != "code"
    ) + "}"

    body_indent = "\n".join("    " + ln if ln.strip() else ln for ln in code.splitlines())
    translate = "" if no_translate else f"    cairo_translate(cr, {ox}, {oy})\n"
    restore = "" if no_translate else "    cairo_restore(cr)\n"
    save = "" if no_translate else "    cairo_save(cr)\n"

    return f"""local function {fn}(cr, W, H)
{save}{translate}{chr(10).join(inputs)}
    local NODE_ID = {lua_string_literal(node.id)}
    local NS = studio_node_state(NODE_ID)
    local PROPS = {props_lit}
{body_indent}
{restore}end"""


@visual_generator("visual.weather_icon")
def _gen_weather_icon(node, ctx):
    """Category-driven vector weather mark."""
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 30)), int(p.get("cy", 30))
    size = int(p.get("size", 28) or 28)
    cat = ctx.resolve(node, "category")
    r, g, b = _split_rgb(p.get("color", "#B8A888"))
    return f"""local function {fn}(cr, W, H)
    local cat = string.lower(tostring({cat} or 'clear'))
    local s = {size}
    local cx, cy = {cx}, {cy}
    local lw = math.max(1.4, s * 0.07)
    cairo_set_line_width(cr, lw)
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)

    local function sun(warm)
        if warm then cairo_set_source_rgba(cr, 0.95, 0.72, 0.25, 1)
        else cairo_set_source_rgba(cr, {r}, {g}, {b}, 1) end
        cairo_new_sub_path(cr)
        cairo_arc(cr, cx, cy, s * 0.26, 0, 2 * math.pi)
        cairo_fill(cr)
        for i = 0, 7 do
            local a = i * math.pi / 4
            cairo_move_to(cr, cx + math.cos(a) * s * 0.36, cy + math.sin(a) * s * 0.36)
            cairo_line_to(cr, cx + math.cos(a) * s * 0.48, cy + math.sin(a) * s * 0.48)
            cairo_stroke(cr)
        end
    end

    local function cloud()
        cairo_set_source_rgba(cr, {r}, {g}, {b}, 1)
        cairo_new_sub_path(cr)
        cairo_arc(cr, cx - s * 0.16, cy + s * 0.02, s * 0.20, 0, 2 * math.pi)
        cairo_arc(cr, cx + s * 0.10, cy - s * 0.04, s * 0.24, 0, 2 * math.pi)
        cairo_arc(cr, cx + s * 0.22, cy + s * 0.06, s * 0.16, 0, 2 * math.pi)
        cairo_fill(cr)
    end

    if cat == 'clear' or cat == 'hot' then
        sun(cat == 'hot')
    elseif cat == 'cloud' or cat == 'overcast' then
        cloud()
    elseif cat == 'rain' or cat == 'storm' then
        cloud()
        cairo_set_source_rgba(cr, {r}, {g}, {b}, 0.9)
        cairo_set_line_width(cr, lw * 0.85)
        local drops = (cat == 'storm') and 5 or 3
        for i = 0, drops - 1 do
            local dx = cx - s * 0.22 + i * (s * 0.12)
            local dy = cy + s * 0.22
            cairo_move_to(cr, dx, dy)
            cairo_line_to(cr, dx - s * 0.04, dy + s * 0.18)
            cairo_stroke(cr)
        end
        if cat == 'storm' then
            cairo_set_source_rgba(cr, 0.95, 0.85, 0.25, 1)
            cairo_set_line_width(cr, lw * 1.1)
            cairo_move_to(cr, cx + s * 0.05, cy - s * 0.05)
            cairo_line_to(cr, cx - s * 0.02, cy + s * 0.12)
            cairo_line_to(cr, cx + s * 0.08, cy + s * 0.10)
            cairo_line_to(cr, cx - s * 0.05, cy + s * 0.32)
            cairo_stroke(cr)
        end
    elseif cat == 'snow' or cat == 'cold' then
        if cat == 'snow' then cloud() end
        cairo_set_source_rgba(cr, 0.75, 0.88, 1.0, 1)
        cairo_set_line_width(cr, lw * 0.7)
        for i = 0, 4 do
            local a = i * (2 * math.pi / 5)
            local ox = cx + math.cos(a) * s * 0.12
            local oy = cy + s * 0.28 + math.sin(a) * s * 0.08
            cairo_move_to(cr, ox - s * 0.05, oy)
            cairo_line_to(cr, ox + s * 0.05, oy)
            cairo_move_to(cr, ox, oy - s * 0.05)
            cairo_line_to(cr, ox, oy + s * 0.05)
            cairo_stroke(cr)
        end
        if cat == 'cold' then
            cairo_set_source_rgba(cr, 0.6, 0.8, 1.0, 1)
            cairo_new_sub_path(cr)
            cairo_arc(cr, cx, cy, s * 0.18, 0, 2 * math.pi)
            cairo_stroke(cr)
        end
    elseif cat == 'fog' then
        cairo_set_source_rgba(cr, {r}, {g}, {b}, 0.85)
        for i = 0, 3 do
            local yy = cy - s * 0.18 + i * s * 0.12
            cairo_move_to(cr, cx - s * 0.35, yy)
            cairo_line_to(cr, cx + s * 0.35, yy)
            cairo_stroke(cr)
        end
    elseif cat == 'wind' then
        cairo_set_source_rgba(cr, {r}, {g}, {b}, 1)
        for i = 0, 2 do
            local yy = cy - s * 0.12 + i * s * 0.12
            cairo_move_to(cr, cx - s * 0.35, yy)
            cairo_curve_to(cr, cx - s * 0.05, yy - s * 0.08, cx + s * 0.1, yy + s * 0.08, cx + s * 0.38, yy)
            cairo_stroke(cr)
        end
    elseif cat == 'dust' then
        cairo_set_source_rgba(cr, {r}, {g}, {b}, 0.75)
        for i = 0, 8 do
            local a = i * 0.7
            local px = cx + math.cos(a) * s * (0.1 + (i % 3) * 0.08)
            local py = cy + math.sin(a * 1.3) * s * (0.1 + (i % 2) * 0.1)
            cairo_new_sub_path(cr)
            cairo_arc(cr, px, py, s * 0.04, 0, 2 * math.pi)
            cairo_fill(cr)
        end
    else
        cloud()
    end
    cairo_new_path(cr)
end"""



# ---------------------------------------------------------------------------
# Generators for types that were registered in visuals.py but lacked emitters
# (palette showed them; preview drew nothing / stub only).
# ---------------------------------------------------------------------------

@visual_generator("visual.circle")
def _gen_circle(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    radius = float(p.get("radius", 40) or 40)
    w = float(p.get("width", 0) or 0)
    h = float(p.get("height", 0) or 0)
    start = float(p.get("start_angle_deg", 0) or 0)
    sweep = float(p.get("sweep_deg", 360) or 360)
    pie = bool(p.get("pie", False))
    do_fill = bool(p.get("fill", True))
    do_stroke = bool(p.get("stroke", True))
    lw = float(p.get("line_width", 1.5) or 1.5)
    opacity = float(p.get("opacity", 1.0) or 1.0)
    sr, sg, sb = _split_rgb(p.get("stroke_color", "#26fdf1"))
    rx = (w / 2.0) if w > 0 else radius
    ry = (h / 2.0) if h > 0 else radius
    setup, destroy = fill_source_lua(
        p, box=(cx - rx, cy - ry, rx * 2, ry * 2), radial=(cx, cy, max(rx, ry)), alpha=opacity
    )
    body = [
        f"local cx, cy, rx, ry = {cx}, {cy}, {rx}, {ry}",
        f"local a0, a1 = math.rad({start}), math.rad({start + sweep})",
        "cairo_new_sub_path(cr)",
        "if math.abs(rx - ry) < 0.01 then",
        "    cairo_arc(cr, cx, cy, rx, a0, a1)",
        "else",
        "    cairo_save(cr); cairo_translate(cr, cx, cy); cairo_scale(cr, 1, ry / math.max(rx, 1e-6))",
        "    cairo_arc(cr, 0, 0, rx, a0, a1); cairo_restore(cr)",
        "end",
    ]
    if pie and abs(sweep) < 359.9:
        body += ["cairo_line_to(cr, cx, cy)", "cairo_close_path(cr)"]
    if do_fill:
        body.append(setup)
        body.append("cairo_fill_preserve(cr)" if do_stroke else "cairo_fill(cr)")
        if destroy:
            body.append(destroy)
    if do_stroke:
        body += [
            f"cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})",
            f"cairo_set_line_width(cr, {lw})",
            "cairo_stroke(cr)",
        ]
    elif not do_fill:
        body.append("cairo_new_path(cr)")
    return _wrap_fn_body(fn, body, p)


@visual_generator("visual.star")
def _gen_star(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    radius = float(p.get("radius", 40) or 40)
    points = max(3, int(p.get("points", 5) or 5))
    inner = float(p.get("inner_ratio", 0.4) or 0.4)
    rot = float(p.get("rotation_deg", 0) or 0)
    do_fill = bool(p.get("fill", True))
    do_stroke = bool(p.get("stroke", True))
    lw = float(p.get("line_width", 1.5) or 1.5)
    opacity = float(p.get("opacity", 1.0) or 1.0)
    sr, sg, sb = _split_rgb(p.get("stroke_color", "#26fdf1"))
    setup, destroy = fill_source_lua(
        p, box=(cx - radius, cy - radius, radius * 2, radius * 2), radial=(cx, cy, radius), alpha=opacity
    )
    body = [
        f"local cx, cy, R, n, ir = {cx}, {cy}, {radius}, {points}, {inner}",
        f"local rot = math.rad({rot} - 90)",
        "cairo_new_path(cr)",
        "for i = 0, n * 2 - 1 do",
        "    local a = rot + i * math.pi / n",
        "    local rad = (i % 2 == 0) and R or (R * ir)",
        "    local px, py = cx + math.cos(a) * rad, cy + math.sin(a) * rad",
        "    if i == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end",
        "end",
        "cairo_close_path(cr)",
    ]
    if do_fill:
        body.append(setup)
        body.append("cairo_fill_preserve(cr)" if do_stroke else "cairo_fill(cr)")
        if destroy:
            body.append(destroy)
    if do_stroke:
        body += [
            f"cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})",
            f"cairo_set_line_width(cr, {lw})",
            "cairo_stroke(cr)",
        ]
    return _wrap_fn_body(fn, body, p)


@visual_generator("visual.triangle")
def _gen_triangle(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    size = float(p.get("size", 50) or 50)
    rot = float(p.get("rotation_deg", 0) or 0)
    free = bool(p.get("free_corners", False))
    do_fill = bool(p.get("fill", True))
    do_stroke = bool(p.get("stroke", True))
    lw = float(p.get("line_width", 1.5) or 1.5)
    opacity = float(p.get("opacity", 1.0) or 1.0)
    sr, sg, sb = _split_rgb(p.get("stroke_color", "#26fdf1"))
    if free:
        pts = [
            (float(p.get("x1", 0)), float(p.get("y1", -size))),
            (float(p.get("x2", size)), float(p.get("y2", size))),
            (float(p.get("x3", -size)), float(p.get("y3", size))),
        ]
    else:
        pts = None
    setup, destroy = fill_source_lua(
        p, box=(cx - size, cy - size, size * 2, size * 2), alpha=opacity
    )
    if pts:
        body = [
            f"local cx, cy = {cx}, {cy}",
            f"cairo_move_to(cr, cx + {pts[0][0]}, cy + {pts[0][1]})",
            f"cairo_line_to(cr, cx + {pts[1][0]}, cy + {pts[1][1]})",
            f"cairo_line_to(cr, cx + {pts[2][0]}, cy + {pts[2][1]})",
            "cairo_close_path(cr)",
        ]
    else:
        body = [
            f"local cx, cy, s, rot = {cx}, {cy}, {size}, math.rad({rot} - 90)",
            "cairo_new_path(cr)",
            "for i = 0, 2 do",
            "    local a = rot + i * 2 * math.pi / 3",
            "    local px, py = cx + math.cos(a) * s, cy + math.sin(a) * s",
            "    if i == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end",
            "end",
            "cairo_close_path(cr)",
        ]
    if do_fill:
        body.append(setup)
        body.append("cairo_fill_preserve(cr)" if do_stroke else "cairo_fill(cr)")
        if destroy:
            body.append(destroy)
    if do_stroke:
        body += [
            f"cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})",
            f"cairo_set_line_width(cr, {lw})",
            "cairo_stroke(cr)",
        ]
    return _wrap_fn_body(fn, body, p)


@visual_generator("visual.corner_brackets")
def _gen_corner_brackets(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    w, h = int(p.get("width", 200)), int(p.get("height", 120))
    arm = float(p.get("arm_length", 24) or 24)
    thick = float(p.get("thickness", 2) or 2)
    opacity = float(p.get("opacity", 1.0) or 1.0)
    r, g, b = _split_rgb(p.get("color", "#26fdf1"))
    corners = []
    if p.get("top_left", True):
        corners.append(("tl", x, y))
    if p.get("top_right", True):
        corners.append(("tr", x + w, y))
    if p.get("bottom_left", True):
        corners.append(("bl", x, y + h))
    if p.get("bottom_right", True):
        corners.append(("br", x + w, y + h))
    body = [
        f"cairo_set_line_width(cr, {thick})",
        f"cairo_set_source_rgba(cr, {r}, {g}, {b}, {opacity})",
        f"local arm = {arm}",
    ]
    for name, px, py in corners:
        if name == "tl":
            body += [f"cairo_move_to(cr, {px}, {py} + arm); cairo_line_to(cr, {px}, {py}); cairo_line_to(cr, {px} + arm, {py}); cairo_stroke(cr)"]
        elif name == "tr":
            body += [f"cairo_move_to(cr, {px} - arm, {py}); cairo_line_to(cr, {px}, {py}); cairo_line_to(cr, {px}, {py} + arm); cairo_stroke(cr)"]
        elif name == "bl":
            body += [f"cairo_move_to(cr, {px}, {py} - arm); cairo_line_to(cr, {px}, {py}); cairo_line_to(cr, {px} + arm, {py}); cairo_stroke(cr)"]
        else:
            body += [f"cairo_move_to(cr, {px} - arm, {py}); cairo_line_to(cr, {px}, {py}); cairo_line_to(cr, {px}, {py} - arm); cairo_stroke(cr)"]
    return _wrap_fn_body(fn, body, p)


@visual_generator("visual.icon_glyph")
def _gen_icon_glyph(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    ch = str(p.get("character", "★") or "★")
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    size = int(p.get("size", 24) or 24)
    family = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
    r, g, b = _split_rgb(p.get("color", "#e8eaed"))
    mode = str(p.get("input_mode", "literal") or "literal").lower()
    ch_expr = ctx.resolve(node, "character")
    if mode in ("bound", "value", "source") or "SRC[" in str(ch_expr):
        text_lua = f"tostring({ch_expr} or {lua_string_literal(ch)})"
    else:
        text_lua = lua_string_literal(ch)
    return f"""local function {fn}(cr, W, H)
    studio_draw_text(cr, {text_lua}, {x}, {y}, {{
        family = '{family}', size = {size},
        r = {r}, g = {g}, b = {b}, a = 1, align = 'center'
    }})
end"""



@visual_generator("visual.text_list")
def _gen_text_list(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    value = ctx.resolve(node, "value")
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    max_lines = int(p.get("max_lines", 8) or 8)
    line_h = int(p.get("line_height", 16) or 16)
    family = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
    size = int(p.get("font_size", 12) or 12)
    r, g, b = _split_rgb(p.get("color", "#e8eaed"))
    return f"""local function {fn}(cr, W, H)
    local raw = tostring({value} or '')
    local y0, lh, maxl = {y}, {line_h}, {max_lines}
    local n = 0
    for line in string.gmatch(raw .. '\\n', '(.-)\\n') do
        n = n + 1
        if n > maxl then break end
        studio_draw_text(cr, line, {x}, y0 + (n - 1) * lh, {{
            family = '{family}', size = {size}, r = {r}, g = {g}, b = {b}, a = 1
        }})
    end
end"""


@visual_generator("visual.multi_line_graph")
def _gen_multi_line_graph(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    w, h = int(p.get("width", 220)), int(p.get("height", 70))
    hist = int(p.get("history_length", 48) or 48)
    min_v = float(p.get("min_value", 0) or 0)
    max_v = float(p.get("max_value", 100) or 100)
    lw = float(p.get("line_width", 2.0) or 2.0)
    tr, tg, tb = _split_rgb(p.get("track_color", "#33313a"))
    series = []
    for key, ck in (("value_a", "color_a"), ("value_b", "color_b"), ("value_c", "color_c")):
        series.append((ctx.resolve(node, key), _split_rgb(p.get(ck, "#4fd1c5"))))
    title = ctx.resolve(node, "title_label")
    tsize = int(p.get("title_font_size", 11) or 11)
    tcr, tcg, tcb = _split_rgb(p.get("title_color", "#9aa2ad"))
    key = lua_string_literal(node.id)
    lines = [
        f"local function {fn}(cr, W, H)",
        f"    local key = {key}",
        f"    local x, y, w, h = {x}, {y}, {w}, {h}",
        f"    local min_v, max_v = {min_v}, {max_v}",
        f"    cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, 0.8)",
        "    cairo_rectangle(cr, x, y, w, h); cairo_stroke(cr)",
    ]
    for i, (expr, (r, g, b)) in enumerate(series):
        sk = f"key .. '_{i}'"
        lines += [
            f"    do local buf = HIST[{sk}]; if type(buf) ~= 'table' then buf = {{}}; HIST[{sk}] = buf end",
            f"    table.insert(buf, tonumber({expr}) or 0)",
            f"    while #buf > {hist} do table.remove(buf, 1) end",
            f"    local n = #buf",
            "    if n >= 2 then",
            f"        cairo_set_line_width(cr, {lw})",
            f"        cairo_set_source_rgba(cr, {r}, {g}, {b}, 1)",
            "        for i = 1, n do",
            "            local px = x + (i - 1) * (w / math.max(n - 1, 1))",
            "            local pct = clamp((buf[i] - min_v) / math.max(max_v - min_v, 1e-9), 0, 1)",
            "            local py = y + h - pct * h",
            "            if i == 1 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end",
            "        end",
            "        cairo_stroke(cr)",
            "    end end",
        ]
    lines += [
        f"    local title = tostring({title} or '')",
        "    if title ~= '' then",
        f"        studio_draw_text(cr, title, x, y - 4, {{size = {tsize}, r = {tcr}, g = {tcg}, b = {tcb}, a = 1}})",
        "    end",
        "end",
    ]
    return "\n".join(lines)


@visual_generator("visual.radar_sweep")
def _gen_radar_sweep(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 120)), int(p.get("cy", 120))
    radius = float(p.get("radius", 80) or 80)
    rings = max(1, int(p.get("ring_count", 3) or 3))
    trail = max(1, int(p.get("trail_length", 8) or 8))
    speed = float(p.get("sweep_speed_dps", 90) or 90)
    show_cross = bool(p.get("show_crosshairs", True))
    r, g, b = _split_rgb(p.get("color", "#4fd1c5"))
    dr, dg, db = _split_rgb(p.get("dim_color", "#1a3a4a"))
    br, bg, bb = _split_rgb(p.get("blip_color", "#e8eaed"))
    blips = max(0, int(p.get("blip_count", 3) or 3))
    seed = int(p.get("blip_seed", 7) or 7)

    cross = ""
    if show_cross:
        cross = f"""
    -- crosshairs (explicit new_path so nothing connects to prior arcs)
    cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.5)
    cairo_set_line_width(cr, 1)
    cairo_new_path(cr)
    cairo_move_to(cr, cx - R, cy)
    cairo_line_to(cr, cx + R, cy)
    cairo_stroke(cr)
    cairo_new_path(cr)
    cairo_move_to(cr, cx, cy - R)
    cairo_line_to(cr, cx, cy + R)
    cairo_stroke(cr)"""

    return f"""local function {fn}(cr, W, H)
    local cx, cy, R = {cx}, {cy}, {radius}
    local t = wall_clock()
    local ang = math.rad((t * {speed}) % 360)
    -- range rings
    cairo_set_line_width(cr, 1)
    for i = 1, {rings} do
        local rr = R * i / {rings}
        cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.7)
        cairo_new_sub_path(cr)
        cairo_arc(cr, cx, cy, rr, 0, 2 * math.pi)
        cairo_close_path(cr)
        cairo_stroke(cr)
    end
{cross}
    -- sweep trail: discrete rays, each on a fresh path
    for i = 0, {trail} - 1 do
        local a = ang - math.rad(i * 3)
        local alpha = 0.55 * (1 - i / {trail})
        cairo_set_source_rgba(cr, {r}, {g}, {b}, alpha)
        cairo_set_line_width(cr, 2)
        cairo_new_path(cr)
        cairo_move_to(cr, cx, cy)
        cairo_line_to(cr, cx + math.cos(a) * R, cy + math.sin(a) * R)
        cairo_stroke(cr)
    end
    -- decorative blips
    for i = 1, {blips} do
        local s = {seed} * 17 + i * 31
        local ba = math.rad((s * 47 + t * 12 * i) % 360)
        local brd = R * (0.25 + (s % 50) / 100)
        cairo_set_source_rgba(cr, {br}, {bg}, {bb}, 0.85)
        cairo_new_sub_path(cr)
        cairo_arc(cr, cx + math.cos(ba) * brd, cy + math.sin(ba) * brd, 2.5, 0, 2 * math.pi)
        cairo_close_path(cr)
        cairo_fill(cr)
    end
    cairo_new_path(cr)
end"""



@visual_generator("visual.moon_phase")
def _gen_moon_phase(node, ctx):
    """Lit-face moon disc + phase name, full/new countdowns, and eclipse window on the RIGHT."""
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 50)), int(p.get("cy", 160))
    radius = float(p.get("radius", 36) or 36)
    show_labels = bool(p.get("show_labels", True))
    label_gap = int(p.get("label_gap", 26) or 26)
    family = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
    fsize = int(p.get("font_size", 15) or 15)
    dsize = int(p.get("detail_font_size", 12) or 12)
    southern = bool(p.get("southern_hemisphere", False))
    show_brackets = bool(p.get("show_brackets", True))
    bpad = int(p.get("bracket_pad", 12) or 12)
    blen = int(p.get("bracket_length", 18) or 18)
    bthick = float(p.get("bracket_thickness", 2.0) or 2.0)
    dr, dg, db = _split_rgb(p.get("dark_color", "#0a2226"))
    rr, rg, rb = _split_rgb(p.get("rim_color", "#0fb7ad"))
    tr, tg, tb = _split_rgb(p.get("text_color", "#5fd8ce"))
    flip = -1 if southern else 1
    setup, destroy = fill_source_lua(
        p,
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
        alpha=1,
    )
    destroy_line = destroy if destroy else ""

    # Approximate text block width for brackets (right of disc)
    text_w = 168 if show_labels else 0
    label_h = (fsize + dsize * 2 + 20) if show_labels else 0

    bracket_block = ""
    if show_brackets:
        bracket_block = f"""
    do
        local pad, arm, th = {bpad}, {blen}, {bthick}
        local x1 = cx - R - pad
        local y1 = cy - R - pad
        local x2 = cx + R + pad + {text_w} + {label_gap}
        local y2 = cy + R + pad
        if {str(show_labels).lower()} then
            -- brackets hug disc height; text sits to the right inside/near frame
            local half_h = math.max(R + pad, {label_h} / 2 + 6)
            y1 = cy - half_h
            y2 = cy + half_h
        end
        cairo_set_line_width(cr, th)
        cairo_set_source_rgba(cr, {rr}, {rg}, {rb}, 0.9)
        cairo_new_path(cr)
        cairo_move_to(cr, x1, y1 + arm); cairo_line_to(cr, x1, y1); cairo_line_to(cr, x1 + arm, y1); cairo_stroke(cr)
        cairo_new_path(cr)
        cairo_move_to(cr, x2 - arm, y1); cairo_line_to(cr, x2, y1); cairo_line_to(cr, x2, y1 + arm); cairo_stroke(cr)
        cairo_new_path(cr)
        cairo_move_to(cr, x1, y2 - arm); cairo_line_to(cr, x1, y2); cairo_line_to(cr, x1 + arm, y2); cairo_stroke(cr)
        cairo_new_path(cr)
        cairo_move_to(cr, x2 - arm, y2); cairo_line_to(cr, x2, y2); cairo_line_to(cr, x2, y2 - arm); cairo_stroke(cr)
    end"""

    label_block = ""
    if show_labels:
        label_block = f"""
    do
        local names = {{'New Moon','Waxing Crescent','First Quarter','Waxing Gibbous',
                       'Full Moon','Waning Gibbous','Last Quarter','Waning Crescent'}}
        local idx = math.floor((phase + 0.0625) * 8) % 8 + 1
        local name = names[idx]
        local days_to_full = ((0.5 - phase) % 1) * SYNODIC
        local days_to_new = ((1.0 - phase) % 1) * SYNODIC
        -- text column to the RIGHT of the disc, vertically centred
        local lx = cx + R + {label_gap}
        local ly = cy - ({fsize} + {dsize} * 2 + 12) / 2

        studio_draw_text(cr, name, lx, ly, {{
            family = '{family}', size = {fsize}, align = 'left',
            r = {tr}, g = {tg}, b = {tb}, a = 1
        }})

        local detail
        if days_to_full < 0.6 then
            detail = string.format('Full moon · New in %.0fd', days_to_new)
        elseif days_to_new < 0.6 then
            detail = string.format('New moon · Full in %.0fd', days_to_full)
        else
            detail = string.format('Full in %.0fd · New in %.0fd', days_to_full, days_to_new)
        end
        studio_draw_text(cr, detail, lx, ly + {fsize + 4}, {{
            family = '{family}', size = {dsize}, align = 'left',
            r = {tr}, g = {tg}, b = {tb}, a = 0.85
        }})

        -- Eclipse / blood-moon window (approx): seasons ~every 173.3d, ~35d wide;
        -- lunar eclipses only near full moon inside a season.
        local season_phase = (days % 173.3)
        local in_season = (season_phase < 18) or (season_phase > 155.3)
        local eclipse_line
        if in_season and days_to_full < 18 then
            if days_to_full < 0.6 then
                eclipse_line = 'Eclipse window · now'
            else
                eclipse_line = string.format('Eclipse window in %.0fd', days_to_full)
            end
        else
            local wait = days_to_full
            local probe = days + days_to_full
            for _ = 1, 8 do
                local sp = (probe % 173.3)
                if sp < 18 or sp > 155.3 then break end
                wait = wait + SYNODIC
                probe = probe + SYNODIC
            end
            eclipse_line = string.format('Next eclipse window ~%.0fd', wait)
        end
        studio_draw_text(cr, eclipse_line, lx, ly + {fsize + dsize + 10}, {{
            family = '{family}', size = {dsize}, align = 'left',
            r = {tr}, g = {tg}, b = {tb}, a = 0.75
        }})
    end"""

    return f"""local function {fn}(cr, W, H)
    local cx, cy, R = {cx}, {cy}, {radius}
    local SYNODIC = 29.530588853
    -- 2000-01-06 18:14 UTC approximate new moon
    local KNOWN_NEW = 947182440
    local now = os.time()
    local days = now / 86400
    local phase = ((now - KNOWN_NEW) / 86400 / SYNODIC) % 1
    if phase < 0 then phase = phase + 1 end
    local flip = {flip}
{bracket_block}
    -- dark disc
    cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 1)
    cairo_new_sub_path(cr)
    cairo_arc(cr, cx, cy, R, 0, 2 * math.pi)
    cairo_close_path(cr)
    cairo_fill(cr)
    -- lit face
    cairo_save(cr)
    cairo_new_sub_path(cr)
    cairo_arc(cr, cx, cy, R, 0, 2 * math.pi)
    cairo_clip(cr)
    local cos_el = math.cos(phase * 2 * math.pi)
    local waxing = phase <= 0.5
    {setup}
    if waxing then
        if flip >= 0 then cairo_rectangle(cr, cx, cy - R, R, R * 2)
        else cairo_rectangle(cr, cx - R, cy - R, R, R * 2) end
    else
        if flip >= 0 then cairo_rectangle(cr, cx - R, cy - R, R, R * 2)
        else cairo_rectangle(cr, cx, cy - R, R, R * 2) end
    end
    cairo_fill(cr)
    {destroy_line}
    cairo_save(cr)
    cairo_translate(cr, cx, cy)
    cairo_scale(cr, math.max(math.abs(cos_el), 0.001), 1)
    if cos_el >= 0 then
        cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 1)
        cairo_new_sub_path(cr)
        cairo_arc(cr, 0, 0, R, 0, 2 * math.pi)
        cairo_close_path(cr)
        cairo_fill(cr)
    else
        {setup}
        cairo_new_sub_path(cr)
        cairo_arc(cr, 0, 0, R, 0, 2 * math.pi)
        cairo_close_path(cr)
        cairo_fill(cr)
        {destroy_line}
    end
    cairo_restore(cr)
    cairo_restore(cr)
    -- rim
    cairo_set_source_rgba(cr, {rr}, {rg}, {rb}, 0.85)
    cairo_set_line_width(cr, 1.5)
    cairo_new_sub_path(cr)
    cairo_arc(cr, cx, cy, R, 0, 2 * math.pi)
    cairo_close_path(cr)
    cairo_stroke(cr)
{label_block}
end"""



def _gen_reactor_gauge_v1(node, ctx):
    """Variant 1 of visual.reactor_gauge: the original central-dial generator
    (dashed counter-rotating rings, tick marks, orbiting accent dots, centred
    readout), kept alongside _gen_reactor_gauge_v2 so both looks stay
    selectable from the property panel via the node's `variant` property.
    """
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    value_expr = ctx.resolve(node, "value")
    cx = int(p.get("cx", 120))
    cy = int(p.get("cy", 120))
    radius = int(p.get("radius", 96))
    min_value = float(p.get("min_value", 0.0))
    max_value = float(p.get("max_value", 100.0))
    label = lua_string_literal(p.get("label", "REACTOR OUTPUT %"))
    show_value = bool(p.get("show_value_text", True))
    value_font_size = int(p.get("value_font_size", 46))
    label_font_size = int(p.get("label_font_size", 11))
    font = lua_string_literal(p.get("font_family", "Orbitron"))
    outer_speed = float(p.get("outer_speed_dps", 12.0))
    inner_speed = float(p.get("inner_speed_dps", -27.0))
    value_suffix = lua_string_literal(p.get("value_suffix", "%"))
    pr, pg, pb = _split_rgb(p.get("color", "#26fdf1"))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha="alpha",
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
    )
    dr, dg, db = _split_rgb(p.get("dim_color", "#0fb7ad"))
    ar, ag, ab = _split_rgb(p.get("accent_color", "#ffcf5c"))
    wr, wg, wb = _split_rgb(p.get("warn_color", "#ff3b3b"))
    crit_at = float(p.get("critical_threshold", 90.0))
    pulse_on = bool(p.get("pulse_when_critical", True))

    text_block = ""
    if show_value:
        text_block = f'''
    do
        local num = string.format('%.0f', raw) .. {value_suffix}
        local cr_, cg_, cb_ = {pr}, {pg}, {pb}
        if critical then cr_, cg_, cb_ = {wr}, {wg}, {wb} end
        cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
        cairo_set_font_size(cr, {value_font_size})
        cairo_set_source_rgba(cr, cr_, cg_, cb_, 1)
        local ext = cairo_text_extents_t:create()
        cairo_text_extents(cr, num, ext)
        cairo_move_to(cr, {cx} - ext.width / 2 - ext.x_bearing, {cy} - 4)
        cairo_show_text(cr, num)
        cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
        cairo_set_font_size(cr, {label_font_size})
        cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.85)
        local lab = {label}
        cairo_text_extents(cr, lab, ext)
        cairo_move_to(cr, {cx} - ext.width / 2 - ext.x_bearing, {cy} + 26)
        cairo_show_text(cr, lab)
    end
'''

    return f'''
local function {fn}(cr, W, H)
    local cx, cy, r = {cx}, {cy}, {radius}
    local vmin, vmax = {min_value}, {max_value}
    local raw = {value_expr}
    if type(raw) ~= 'number' then raw = tonumber(raw) or 0 end
    local load = 0
    if vmax > vmin then
        load = math.max(0, math.min(100, (raw - vmin) / (vmax - vmin) * 100))
    end
    local critical = load >= {crit_at}
    local pulse_on = {lua_literal(pulse_on)}
    local t = wall_clock()
    local angle_slow = (t * {outer_speed}) % 360
    local angle_fast = (t * {inner_speed}) % 360
    local pulse = (math.sin(t * 2) + 1) / 2

    -- outer dashed ring
    do
        local n_dashes, dash_deg, thickness = 40, 4, 2
        local step = 360 / n_dashes
        for i = 0, n_dashes - 1 do
            local s = i * step + angle_slow
            cairo_new_path(cr)
            cairo_arc(cr, cx, cy, r + 26, math.rad(s - 90), math.rad(s + dash_deg - 90))
            cairo_set_line_width(cr, thickness)
            cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
            cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.5)
            cairo_stroke(cr)
        end
    end

    -- inner dashed ring (counter-rotating)
    do
        local n_dashes, dash_deg, thickness = 60, 2, 1.5
        local step = 360 / n_dashes
        for i = 0, n_dashes - 1 do
            local s = i * step + angle_fast
            cairo_new_path(cr)
            cairo_arc(cr, cx, cy, r + 14, math.rad(s - 90), math.rad(s + dash_deg - 90))
            cairo_set_line_width(cr, thickness)
            cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
            cairo_set_source_rgba(cr, {pr}, {pg}, {pb}, 0.35)
            cairo_stroke(cr)
        end
    end

    -- solid track
    cairo_new_path(cr)
    cairo_arc(cr, cx, cy, r, 0, 2 * math.pi)
    cairo_set_line_width(cr, 2)
    cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.6)
    cairo_stroke(cr)

    -- tick marks
    do
        local n_ticks, long_every = 60, 5
        for i = 0, n_ticks - 1 do
            local deg = i * (360 / n_ticks)
            local rad = math.rad(deg - 90)
            local is_long = (i % long_every == 0)
            local len = is_long and 14 or 6
            local x1 = cx + math.cos(rad) * r
            local y1 = cy + math.sin(rad) * r
            local x2 = cx + math.cos(rad) * (r - len)
            local y2 = cy + math.sin(rad) * (r - len)
            cairo_new_path(cr)
            cairo_move_to(cr, x1, y1)
            cairo_line_to(cr, x2, y2)
            cairo_set_line_width(cr, is_long and 2 or 1)
            cairo_set_source_rgba(cr, {pr}, {pg}, {pb}, is_long and 0.85 or 0.35)
            cairo_stroke(cr)
        end
    end

    -- value arc
    do
        local alpha = (critical and pulse_on) and (0.6 + pulse * 0.4) or 0.95
        cairo_new_path(cr)
        cairo_arc(cr, cx, cy, r - 20, math.rad(-90), math.rad((load / 100) * 360 - 90))
        cairo_set_line_width(cr, 6)
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
        if critical then
            cairo_set_source_rgba(cr, {wr}, {wg}, {wb}, alpha)
            cairo_stroke(cr)
        else
{fill_setup}
            cairo_stroke(cr)
{fill_destroy}
        end
    end

    -- three orbiting accent dots
    for i = 0, 2 do
        local a = math.rad(angle_slow + i * 120)
        local ox = cx + math.cos(a) * (r + 26)
        local oy = cy + math.sin(a) * (r + 26)
        cairo_set_source_rgba(cr, {ar}, {ag}, {ab}, 0.9)
        cairo_new_path(cr)
        cairo_arc(cr, ox, oy, 3, 0, 2 * math.pi)
        cairo_fill(cr)
    end
{text_block}
end'''


def _gen_reactor_gauge_v2(node, ctx):
    """Variant 2 of visual.reactor_gauge (see _gen_reactor_gauge_v1 just above
    for Variant 1). Dispatched to by the @visual_generator("visual.reactor_gauge")
    entry point below, based on the node's `variant` property.

    JARVIS-style central dial: track, value arc, dual counter-rotating
    dashed rings (drawn as discrete segments — no cairo_set_dash, which is
    unreliable across Conky Lua bindings), tick marks, orbiting accent
    dots, and centred readout. Critical threshold swaps colour and optionally
    pulses opacity.

    visuals.py registers *_GRADIENT_FILL/*_BLEND on this spec (same Style
    group as Arc Gauge / CPU Core Strip), but this generator was never
    updated to read them -- the value arc was hard-coded to solid `color`,
    so the gradient and blend controls sat in the property panel doing
    nothing. Fixed to route the value arc through fill_source_lua (gradient
    only applies in the non-critical state -- once critical, the arc always
    swaps to a solid, unambiguous warn_color, same as before) and to wrap
    the whole draw in wrap_blend_lua like every other gradient-capable node.
    """
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 120)), int(p.get("cy", 120))
    radius = float(p.get("radius", 96) or 96)
    value = ctx.resolve(node, "value")
    min_v = float(p.get("min_value", 0) or 0)
    max_v = float(p.get("max_value", 100) or 100)
    outer_spd = float(p.get("outer_speed_dps", 12) or 12)
    inner_spd = float(p.get("inner_speed_dps", -27) or -27)
    r, g, b = _split_rgb(p.get("color", "#26fdf1"))
    dr, dg, db = _split_rgb(p.get("dim_color", "#0fb7ad"))
    ar, ag, ab = _split_rgb(p.get("accent_color", "#ffcf5c"))
    wr, wg, wb = _split_rgb(p.get("warn_color", "#ff3b3b"))
    crit = float(p.get("critical_threshold", 90) or 90)
    pulse = bool(p.get("pulse_when_critical", True))
    show = bool(p.get("show_value_text", True))
    suffix = lua_string_literal(p.get("value_suffix", "%") or "")
    fsize = int(p.get("value_font_size", 46) or 46)
    label = lua_string_literal(p.get("label", "REACTOR OUTPUT %") or "")
    lfsize = int(p.get("label_font_size", 11) or 11)
    family = str(p.get("font_family", "Orbitron") or "Orbitron").replace("'", "")
    # track thickness ~ radius scale so small gauges stay readable
    track_w = max(6.0, min(14.0, radius * 0.09))
    outer_r = radius + track_w * 0.85
    inner_r = max(radius * 0.72, radius - track_w * 1.6)

    # Vertical layout for the two-line centre readout (value number up
    # high, label down near the bottom of the dial). studio_draw_text's
    # `y` argument is the TOP of the glyph box (lua_framework.py: `ty = y
    # - ext.y_bearing`, and y_bearing is negative -- i.e. the ink starts
    # AT y and extends downward), not a baseline. The previous fix treated
    # it as a baseline and added a small pad above/below the centre line,
    # which meant the value number's real ink extended a full text-height
    # BELOW the y we gave it -- straight down into the label. Positioning
    # both blocks by their vertical centres (top-anchor + half their own
    # height) fixes that, and tying the offsets to `radius` (rather than
    # only font size, which the old code did) is what actually spreads the
    # number up toward the top of the dial and the label down toward the
    # bottom, scaling with gauge size the way a HUD dial should.
    value_h = fsize * 0.85   # ~cap-height block; digits/'%' have no descenders
    label_h = lfsize * 0.85  # label default is all-caps, same assumption
    value_center = radius * 0.30   # above cy
    label_center = radius * 0.42   # below cy
    _min_gap = 6.0
    _gap = (label_center + value_center) - (label_h + value_h) / 2
    if _gap < _min_gap:
        label_center += (_min_gap - _gap)
    value_dy = value_center + value_h / 2    # subtracted from cy -> top of value text
    label_dy = label_center - label_h / 2    # added to cy -> top of label text

    # Gradient source for the value arc, same call shape as visual.arc_gauge.
    # `destroy` (if non-empty) must run in the SAME Lua block as `setup` --
    # a gradient pattern local declared in one if/else arm is out of scope
    # in a later statement -- so both live inside the `else` branch below
    # (mirrors the existing hemisphere-fill pattern earlier in this file
    # rather than a bolt-on "if not hot then destroy end").
    setup, destroy = fill_source_lua(
        p, radial=(cx, cy, radius),
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        alpha=1,
    )

    pulse_lua = ""
    if pulse:
        pulse_lua = (
            "    if hot then\n"
            "        local pulse = 0.72 + 0.28 * (0.5 + 0.5 * math.sin(t * 4.2))\n"
            "        alpha = alpha * pulse\n"
            "    end\n"
        )

    value_text = ""
    if show:
        value_text = (
            f"    studio_draw_text(cr, string.format('%.0f', val) .. {suffix}, "
            f"cx, cy - {value_dy:.1f}, "
            f"{{family = '{family}', size = {fsize}, align = 'center', "
            f"r = cr_, g = cg_, b = cb_, a = alpha, bold = true, halo = true}})\n"
        )

    destroy_line = f"        {destroy}\n" if destroy else ""

    body = f"""    local cx, cy, R = {cx}, {cy}, {radius}
    local track_w = {track_w}
    local outer_r, inner_r = {outer_r}, {inner_r}
    local val = tonumber({value}) or {min_v}
    local span = math.max({max_v} - {min_v}, 1e-9)
    local pct = clamp((val - {min_v}) / span, 0, 1)
    local t = wall_clock()
    local hot = val >= {crit}
    local cr_, cg_, cb_ = {r}, {g}, {b}
    if hot then cr_, cg_, cb_ = {wr}, {wg}, {wb} end
    local alpha = 1.0
{pulse_lua}
    -- dim full track. cairo_new_sub_path is required here: every node's
    -- draw_node_* shares one cairo context for the whole widget, so
    -- without it cairo_arc would implicitly line_to from whatever point
    -- the PREVIOUS node's drawing left the pen at, before stroking this
    -- circle -- a stray line across the canvas. Every other arc-based
    -- gauge in this file (arc_gauge, ring_track, needle_gauge) already
    -- does this; reactor_gauge was the outlier missing it.
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
    cairo_set_line_width(cr, track_w)
    cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.35 * alpha)
    cairo_new_sub_path(cr)
    cairo_arc(cr, cx, cy, R, 0, 2 * math.pi)
    cairo_stroke(cr)

    -- thick value arc (starts at 12 o'clock, clockwise). Critical state
    -- always wins with a solid warn colour; otherwise gradient-aware.
    if pct > 0.001 then
        cairo_set_line_width(cr, track_w)
        if hot then
            cairo_set_source_rgba(cr, {wr}, {wg}, {wb}, alpha)
            cairo_new_sub_path(cr)
            cairo_arc(cr, cx, cy, R, -math.pi / 2, -math.pi / 2 + pct * 2 * math.pi)
            cairo_stroke(cr)
        else
            {setup}
            cairo_new_sub_path(cr)
            cairo_arc(cr, cx, cy, R, -math.pi / 2, -math.pi / 2 + pct * 2 * math.pi)
            cairo_stroke(cr)
{destroy_line}        end
    end

    -- major tick marks on the track
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
    cairo_set_line_width(cr, 1.6)
    cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.75 * alpha)
    for i = 0, 11 do
        local a = -math.pi / 2 + i * (2 * math.pi / 12)
        local cos_a, sin_a = math.cos(a), math.sin(a)
        local r0 = R - track_w * 0.55
        local r1 = R + track_w * 0.55
        cairo_move_to(cr, cx + cos_a * r0, cy + sin_a * r0)
        cairo_line_to(cr, cx + cos_a * r1, cy + sin_a * r1)
        cairo_stroke(cr)
    end
    -- minor ticks
    cairo_set_line_width(cr, 1.0)
    cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.4 * alpha)
    for i = 0, 59 do
        if i % 5 ~= 0 then
            local a = -math.pi / 2 + i * (2 * math.pi / 60)
            local cos_a, sin_a = math.cos(a), math.sin(a)
            local r0 = R - track_w * 0.25
            local r1 = R + track_w * 0.25
            cairo_move_to(cr, cx + cos_a * r0, cy + sin_a * r0)
            cairo_line_to(cr, cx + cos_a * r1, cy + sin_a * r1)
            cairo_stroke(cr)
        end
    end

    -- outer rotating dashed ring (discrete segments — reliable without cairo_set_dash)
    do
        local oang = math.rad(t * {outer_spd})
        local segs, gap_frac = 18, 0.38
        local sweep = (2 * math.pi) / segs
        local solid = sweep * (1 - gap_frac)
        cairo_set_line_width(cr, 2.2)
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
        cairo_set_source_rgba(cr, cr_, cg_, cb_, 0.55 * alpha)
        for i = 0, segs - 1 do
            local a0 = oang + i * sweep
            cairo_arc(cr, cx, cy, outer_r, a0, a0 + solid)
            cairo_stroke(cr)
        end
    end

    -- inner counter-rotating dashed ring
    do
        local iang = math.rad(t * {inner_spd})
        local segs, gap_frac = 12, 0.42
        local sweep = (2 * math.pi) / segs
        local solid = sweep * (1 - gap_frac)
        cairo_set_line_width(cr, 1.8)
        cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.7 * alpha)
        for i = 0, segs - 1 do
            local a0 = iang + i * sweep
            cairo_arc(cr, cx, cy, inner_r, a0, a0 + solid)
            cairo_stroke(cr)
        end
    end

    -- orbiting accent dots (tied to outer ring phase)
    do
        local oang = math.rad(t * {outer_spd})
        local n_dots = 4
        local dot_r = math.max(2.2, track_w * 0.28)
        for i = 0, n_dots - 1 do
            local a = oang + i * (2 * math.pi / n_dots)
            local px = cx + math.cos(a) * outer_r
            local py = cy + math.sin(a) * outer_r
            cairo_set_source_rgba(cr, {ar}, {ag}, {ab}, 0.9 * alpha)
            cairo_arc(cr, px, py, dot_r, 0, 2 * math.pi)
            cairo_fill(cr)
            -- soft halo
            cairo_set_source_rgba(cr, {ar}, {ag}, {ab}, 0.25 * alpha)
            cairo_arc(cr, px, py, dot_r * 2.2, 0, 2 * math.pi)
            cairo_fill(cr)
        end
    end

{value_text}    if {label} ~= '' then
        studio_draw_text(cr, {label}, cx, cy + {label_dy:.1f}, {{
            family = '{family}', size = {lfsize}, align = 'center',
            r = {dr}, g = {dg}, b = {db}, a = 0.85 * alpha
        }})
    end"""

    body = wrap_blend_lua(body, p)
    return f"local function {fn}(cr, W, H)\n{body}\nend"


@visual_generator("visual.reactor_gauge")
def _gen_reactor_gauge(node, ctx):
    """Entry point for visual.reactor_gauge. Dispatches to Variant 1 or
    Variant 2 based on the node's `variant` property (property panel:
    Reactor Gauge > Style > Render variant), so both looks stay available
    without registering two separate node types. Defaults to 'v2' (the
    gradient/blend-aware implementation) for nodes saved before the
    `variant` property existed.
    """
    variant = str(node.props.get("variant", "v2") or "v2").lower()
    if variant == "v1":
        return _gen_reactor_gauge_v1(node, ctx)
    return _gen_reactor_gauge_v2(node, ctx)


@visual_generator("visual.analog_clock")
def _gen_analog_clock(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    radius = float(p.get("radius", 70) or 70)
    show_sec = bool(p.get("show_seconds", True))
    show_num = bool(p.get("show_numerals", True))
    show_min_ticks = bool(p.get("show_minute_ticks", True))
    show_digital = bool(p.get("show_digital", False))
    fr, fg, fb = _split_rgb(p.get("face_color", "#1a222c"))
    rr, rg, rb = _split_rgb(p.get("rim_color", "#4fd1c5"))
    tr, tg, tb = _split_rgb(p.get("tick_color", "#9aa2ad"))
    nr, ng, nb = _split_rgb(p.get("numeral_color", "#e8eaed"))
    hr, hg, hb = _split_rgb(p.get("hour_hand_color", "#e8eaed"))
    mr, mg, mb = _split_rgb(p.get("minute_hand_color", "#e8eaed"))
    sr, sg, sb = _split_rgb(p.get("second_hand_color", "#ff6b6b"))
    hub_r, hub_g, hub_b = _split_rgb(p.get("hub_color", "#1a222c"))
    rim_t = float(p.get("rim_thickness", 3) or 3)
    family = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
    nsize = int(p.get("numeral_size", 12) or 12)
    return f"""local function {fn}(cr, W, H)
    local cx, cy, R = {cx}, {cy}, {radius}
    local t = os.date('*t')
    local sec = t.sec + (tonumber(os.date('%S')) and 0 or 0)
    local min = t.min + t.sec / 60
    local hour = (t.hour % 12) + min / 60
    -- face
    cairo_set_source_rgba(cr, {fr}, {fg}, {fb}, 1)
    cairo_arc(cr, cx, cy, R, 0, 2 * math.pi)
    cairo_fill(cr)
    cairo_set_line_width(cr, {rim_t})
    cairo_set_source_rgba(cr, {rr}, {rg}, {rb}, 1)
    cairo_arc(cr, cx, cy, R, 0, 2 * math.pi)
    cairo_stroke(cr)
    -- ticks
    for i = 0, 59 do
        local a = math.rad(i * 6 - 90)
        local major = (i % 5 == 0)
        local len = major and (R * 0.12) or (R * 0.05)
        if major or {str(show_min_ticks).lower()} then
            cairo_set_line_width(cr, major and 2 or 1)
            cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, 1)
            cairo_move_to(cr, cx + math.cos(a) * (R - len), cy + math.sin(a) * (R - len))
            cairo_line_to(cr, cx + math.cos(a) * (R - 2), cy + math.sin(a) * (R - 2))
            cairo_stroke(cr)
        end
    end
    {"for i = 1, 12 do local a = math.rad(i * 30 - 90); local px = cx + math.cos(a) * R * 0.72; local py = cy + math.sin(a) * R * 0.72; studio_draw_text(cr, tostring(i), px, py, {family = '" + family + "', size = " + str(nsize) + ", align = 'center', r = " + nr + ", g = " + ng + ", b = " + nb + ", a = 1}) end" if show_num else ""}
    -- hands
    local function hand(ang_deg, len, width, r, g, b)
        local a = math.rad(ang_deg - 90)
        cairo_set_line_width(cr, width)
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
        cairo_set_source_rgba(cr, r, g, b, 1)
        cairo_move_to(cr, cx, cy)
        cairo_line_to(cr, cx + math.cos(a) * len, cy + math.sin(a) * len)
        cairo_stroke(cr)
    end
    hand(hour * 30, R * 0.5, 3.5, {hr}, {hg}, {hb})
    hand(min * 6, R * 0.72, 2.5, {mr}, {mg}, {mb})
    {"hand(t.sec * 6, R * 0.82, 1.2, " + sr + ", " + sg + ", " + sb + ")" if show_sec else ""}
    cairo_set_source_rgba(cr, {hub_r}, {hub_g}, {hub_b}, 1)
    cairo_arc(cr, cx, cy, 4, 0, 2 * math.pi)
    cairo_fill(cr)
    {"studio_draw_text(cr, os.date('%H:%M:%S'), cx, cy + R + 14, {family = '" + family + "', size = 12, align = 'center', r = " + nr + ", g = " + ng + ", b = " + nb + ", a = 1})" if show_digital else ""}
end"""


@visual_generator("visual.wall_calendar")
def _gen_wall_calendar(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    cw = int(p.get("cell_w", 36) or 36)
    ch = int(p.get("cell_h", 28) or 28)
    show_title = bool(p.get("show_title", True))
    show_wd = bool(p.get("show_weekdays", True))
    show_outside = bool(p.get("show_outside_days", False))
    show_grid = bool(p.get("show_grid", True))
    week_start = str(p.get("week_start", "monday") or "monday")
    today_style = str(p.get("today_style", "fill") or "fill")
    family = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
    title_size = int(p.get("title_size", 16) or 16)
    day_size = int(p.get("day_size", 13) or 13)
    weekday_size = int(p.get("weekday_size", 11) or 11)
    tr, tg, tb = _split_rgb(p.get("title_color", "#FFFFFF"))
    wr, wg, wb = _split_rgb(p.get("weekday_color", "#9aa2ad"))
    dr, dg, db = _split_rgb(p.get("day_color", "#e8eaed"))
    tdr, tdg, tdb = _split_rgb(p.get("today_color", "#4fd1c5"))
    tfr, tfg, tfb = _split_rgb(p.get("today_fill", "#4fd1c5"))
    or_, og, ob = _split_rgb(p.get("outside_color", "#5c636d"))
    gr, gg, gb = _split_rgb(p.get("grid_color", "#33313a"))
    opacity = float(p.get("opacity", 1.0) or 1.0)

    fill_mode = str(p.get("fill_mode", "solid") or "solid").lower()
    color_end = str(p.get("color_end", p.get("color_end_hex", "#1a3a4a")) or "#1a3a4a")
    angle = float(p.get("gradient_angle", 0) or 0)
    spread = float(p.get("gradient_spread", 1.0) or 1.0)
    er, eg, eb = _split_rgb(color_end)

    body_title = ""
    if show_title:
        body_title = f"""
    studio_draw_text(cr, os.date('%B %Y'), x0, y0, {{family = '{family}', size = {title_size}, r = {tr}, g = {tg}, b = {tb}, a = {opacity}}})
    row0 = row0 + ch
"""
    body_wd = ""
    if show_wd:
        wd_str = "Mon Tue Wed Thu Fri Sat Sun" if week_start == "monday" else "Sun Mon Tue Wed Thu Fri Sat"
        body_wd = f"""
    do
        local wi = 0
        for name in ('{wd_str}'):gmatch('%S+') do
            studio_draw_text(cr, name:sub(1,2), x0 + wi * cw + cw/2, row0 + ch/2, {{
                family = '{family}', size = {weekday_size}, align = 'center',
                r = {wr}, g = {wg}, b = {wb}, a = {opacity}
            }})
            wi = wi + 1
        end
        row0 = row0 + ch
    end
"""
    start_num = "1" if week_start == "monday" else "0"
    grid_block = ""
    if show_grid:
        grid_block = f"""
    do
        local rows = math.ceil((pad + dim) / 7)
        cairo_set_line_width(cr, 1)
        cairo_set_source_rgba(cr, {gr}, {gg}, {gb}, {opacity} * 0.9)
        for c = 0, 7 do
            local gx = x0 + c * cw
            cairo_move_to(cr, gx, row0)
            cairo_line_to(cr, gx, row0 + rows * ch)
            cairo_stroke(cr)
        end
        for r = 0, rows do
            local gy = row0 + r * ch
            cairo_move_to(cr, x0, gy)
            cairo_line_to(cr, x0 + 7 * cw, gy)
            cairo_stroke(cr)
        end
    end
"""
    outside_flag = "true" if show_outside else "false"

    if fill_mode == "radial":
        today_fill_lua = f"""
                local _grad = cairo_pattern_create_radial(px + cw/2, py + ch/2, 0, px + cw/2, py + ch/2, math.max(cw, ch)/2 * {spread})
                cairo_pattern_add_color_stop_rgba(_grad, 0, {tfr}, {tfg}, {tfb}, {opacity * 0.55})
                cairo_pattern_add_color_stop_rgba(_grad, 1, {er}, {eg}, {eb}, {opacity * 0.25})
                cairo_set_source(cr, _grad)
                cairo_rectangle(cr, px + 2, py + 2, cw - 4, ch - 4)
                cairo_fill(cr)
                cairo_pattern_destroy(_grad)
"""
    elif fill_mode == "linear":
        today_fill_lua = f"""
                local _gx = px + cw/2
                local _gy = py + ch/2
                local _glen = math.max(cw, ch) / 2
                local _ga = math.rad({angle})
                local _grad = cairo_pattern_create_linear(
                    _gx - math.cos(_ga) * _glen, _gy - math.sin(_ga) * _glen,
                    _gx + math.cos(_ga) * _glen, _gy + math.sin(_ga) * _glen)
                cairo_pattern_add_color_stop_rgba(_grad, 0, {tfr}, {tfg}, {tfb}, {opacity * 0.55})
                cairo_pattern_add_color_stop_rgba(_grad, 1, {er}, {eg}, {eb}, {opacity * 0.25})
                cairo_set_source(cr, _grad)
                cairo_rectangle(cr, px + 2, py + 2, cw - 4, ch - 4)
                cairo_fill(cr)
                cairo_pattern_destroy(_grad)
"""
    else:
        today_fill_lua = f"""
                cairo_set_source_rgba(cr, {tfr}, {tfg}, {tfb}, {opacity} * 0.35)
                cairo_rectangle(cr, px + 2, py + 2, cw - 4, ch - 4)
                cairo_fill(cr)
"""

    return f"""local function {fn}(cr, W, H)
    local x0, y0, cw, ch = {x}, {y}, {cw}, {ch}
    local t = os.date('*t')
    local y, m, today = t.year, t.month, t.day
    local first = os.date('*t', os.time{{year=y, month=m, day=1}}).wday - 1
    local start = {start_num}
    local pad = (first - start) % 7
    local dim = os.date('*t', os.time{{year=y, month=m+1, day=0}}).day
    local prev_dim = os.date('*t', os.time{{year=y, month=m, day=0}}).day
    local row0 = y0
{body_title}{body_wd}
{grid_block}
    local cells = math.ceil((pad + dim) / 7) * 7
    for i = 0, cells - 1 do
        local col = i % 7
        local row = math.floor(i / 7)
        local px = x0 + col * cw
        local py = row0 + row * ch
        local d, is_outside, is_today = 0, false, false
        if i < pad then
            is_outside = true
            d = prev_dim - pad + i + 1
        elseif i < pad + dim then
            d = i - pad + 1
            is_today = (d == today)
        else
            is_outside = true
            d = i - (pad + dim) + 1
        end
        if is_outside and not {outside_flag} then
            -- skip
        else
            local cr_, cg_, cb_ = {dr}, {dg}, {db}
            if is_outside then cr_, cg_, cb_ = {or_}, {og}, {ob} end
            if is_today then
                local style = '{today_style}'
                if style == 'fill' then
{today_fill_lua}
                elseif style == 'ring' then
                    cairo_set_source_rgba(cr, {tfr}, {tfg}, {tfb}, {opacity})
                    cairo_set_line_width(cr, 2)
                    cairo_rectangle(cr, px + 2, py + 2, cw - 4, ch - 4)
                    cairo_stroke(cr)
                end
                cr_, cg_, cb_ = {tdr}, {tdg}, {tdb}
            end
            local size = {day_size}
            if is_today and '{today_style}' == 'bold' then size = size + 2 end
            studio_draw_text(cr, tostring(d), px + cw/2, py + ch/2, {{
                family = '{family}', size = size, align = 'center',
                r = cr_, g = cg_, b = cb_, a = {opacity}
            }})
        end
    end
end"""



@visual_generator("visual.album_art")
def _gen_album_art(node, ctx):
    """Cover art from daemon cache, then images/ fallback."""
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    size = int(p.get("size", 96) or 96)
    rad = float(p.get("corner_radius", 6) or 6)
    fallback = str(p.get("fallback_path", "") or "").split("/")[-1]
    nid = lua_string_literal(str(node.id))
    return f"""local function {fn}(cr, W, H)
    local path = THEME_DIR .. '/.runtime-cache/album_art_' .. {nid} .. '.png'
    local img = load_image_periodic(path, 'album_art_' .. {nid})
    if img == nil then
        img = load_image_cached(THEME_DIR .. '/images/album_art.jpg')
    end
    if img == nil and {lua_string_literal(fallback)} ~= '' then
        img = load_image_cached(THEME_DIR .. '/images/' .. {lua_string_literal(fallback)})
    end
    if img == nil then
        cairo_set_source_rgba(cr, 0.12, 0.14, 0.18, 1)
        rounded_rect(cr, {x}, {y}, {size}, {size}, {rad})
        cairo_fill(cr)
        return
    end
    cairo_save(cr)
    rounded_rect(cr, {x}, {y}, {size}, {size}, {rad})
    cairo_clip(cr)
    draw_image_fit(cr, img, {x}, {y}, {size}, 0, 1)
    cairo_restore(cr)
end"""



# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _topo_logic_nodes(project):
    """Logic nodes in dependency order (sources first via edges)."""
    logic_nodes = [n for n in project.nodes if str(n.type).startswith("logic.")]
    ids = {n.id for n in logic_nodes}
    deps = {n.id: set() for n in logic_nodes}
    for e in getattr(project, "edges", []) or []:
        src = getattr(e, "src_node", None)
        dst = getattr(e, "dst_node", None)
        if src in ids and dst in ids:
            deps[dst].add(src)
    ordered = []
    seen = set()

    def visit(nid):
        if nid in seen:
            return
        seen.add(nid)
        for d in deps.get(nid, ()):
            visit(d)
        ordered.append(nid)

    for n in logic_nodes:
        visit(n.id)
    by_id = {n.id: n for n in logic_nodes}
    return [by_id[i] for i in ordered if i in by_id]


def build_render_lua(
    project,
    script_filenames: dict | None = None,
    header_comment: str = "",
    visible_node_ids: list[str] | None = None,
) -> str:
    """Emit full render.lua text for *project*.

    *visible_node_ids*: when non-empty, only those visual node ids are called
    from main_draw (per-window scene filter). Sources + logic still refresh
    fully so shared data stays coherent across windows.
    """
    assert_full_coverage()
    script_filenames = script_filenames or {}
    ctx = ResolveContext(project, script_filenames)
    visible_filter = {str(i) for i in (visible_node_ids or []) if i}

    parts: list[str] = []
    parts.append(header_comment or f"-- {getattr(project, 'name', 'theme')} -- generated by Conky Studio")
    parts.append("")
    parts.append(FRAMEWORK_LUA.rstrip())
    parts.append("")
    parts.append("-- ---------------------------------------------------------------------")
    parts.append("--  Theme directory (self-locating)")
    parts.append("-- ---------------------------------------------------------------------")
    parts.append("local THEME_DIR = (function()")
    parts.append("    local src = debug.getinfo(1, 'S').source:gsub('^@', '')")
    parts.append("    return (src:match('(.*/)') or './'):gsub('/$', '')")
    parts.append("end)()")
    parts.append("")

    # Module-mode custom lua nodes (run once at load)
    module_nodes = [
        n for n in project.nodes
        if n.type == "visual.custom_lua" and str(n.props.get("run_mode", "draw")) == "module"
    ]
    module_nodes.sort(key=lambda n: float(n.props.get("load_order", 0) or 0))
    if module_nodes:
        parts.append("-- Module Custom Lua nodes (run once)")
        for n in module_nodes:
            code = str(n.props.get("code", "") or "")
            parts.append(f"do -- module {n.id}")
            parts.append(f"    local NODE_ID = {lua_string_literal(n.id)}")
            parts.append(f"    local NS = studio_node_state(NODE_ID)")
            parts.append(code)
            parts.append("end")
        parts.append("")

    # refresh_sources
    parts.append("local function refresh_sources()")
    parts.append("    -- Native + scripted sources")
    source_nodes = [n for n in project.nodes if str(n.type).startswith("source.")]
    for n in source_nodes:
        line = _scripted_refresh_line(n, script_filenames)
        if line:
            parts.append(line)
        else:
            expr, _kind = _native_source_expr(n)
            parts.append(f"    SRC[{lua_string_literal(n.id)}] = {expr}")

    # Logic nodes (after sources)
    for n in _topo_logic_nodes(project):
        gen = _LOGIC_GENERATORS.get(n.type)
        if gen is None:
            parts.append(f"    SRC[{lua_string_literal(n.id)}] = 0")
            continue
        try:
            expr = gen(n, ctx)
        except Exception as exc:
            parts.append(f"    SRC[{lua_string_literal(n.id)}] = 0 -- logic error: {exc}")
            continue
        parts.append(f"    SRC[{lua_string_literal(n.id)}] = {expr}")
    parts.append("end")
    parts.append("")

    # Visual draw functions
    visual_nodes = [
        n for n in project.nodes
        if str(n.type).startswith("visual.")
        and getattr(n, "visible", True)
        and not (n.type == "visual.custom_lua" and str(n.props.get("run_mode", "draw")) == "module")
    ]
    # Stable draw order by z then id
    visual_nodes.sort(key=lambda n: (getattr(n, "z", 0) or 0, str(n.id)))

    # Always emit every visual's draw_* function so a shared render.lua can
    # serve multiple window filters; main_draw decides which to call.
    draw_entries: list[tuple[str, str]] = []  # (node_id, function_name)
    for n in visual_nodes:
        gen = _VISUAL_GENERATORS.get(n.type) or _make_stub_visual(n.type)
        try:
            lua = gen(n, ctx)
        except Exception as exc:
            fn = f"draw_node_{lua_safe_id(n.id)}"
            lua = f"local function {fn}(cr, W, H)\n    -- generator error: {exc}\nend"
        # Uniform Scale %: geometry + text + strokes resize together
        try:
            lua = apply_scale_to_draw_function(lua, n)
        except Exception:
            pass
        parts.append(lua)
        parts.append("")
        draw_entries.append((str(n.id), f"draw_node_{lua_safe_id(n.id)}"))

    if visible_filter:
        active = [(nid, fn) for nid, fn in draw_entries if nid in visible_filter]
        # If the filter listed ids that are missing, fall back to full set so
        # the window is not blank after a node delete.
        if not active:
            active = list(draw_entries)
        filter_note = f"  -- filtered scene: {len(active)}/{len(draw_entries)} visuals"
    else:
        active = list(draw_entries)
        filter_note = "  -- full shared scene"

    # main_draw
    parts.append("function main_draw()")
    parts.append(filter_note)
    parts.append("    local cs, ww, wh, own = get_draw_surface()")
    parts.append("    if cs == nil then return end")
    parts.append("    local cr = cairo_create(cs)")
    parts.append("    refresh_sources()")
    for _nid, name in active:
        parts.append(f"    studio_safe_call('{name}', {name}, cr, ww, wh)")
    parts.append("    cairo_destroy(cr)")
    parts.append("    if own then cairo_surface_destroy(cs) end")
    parts.append("end")
    parts.append("")
    parts.append("-- Conky entry points")
    parts.append("function conky_main_draw()")
    parts.append("    main_draw()")
    parts.append("end")
    parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Extension generators (extra / more / niche) — safety net so headless builds
# and out-of-order imports still get top_table, needle_gauge, matrix_rain, etc.
# ---------------------------------------------------------------------------
def _register_bundled_extension_generators() -> None:
    try:
        from conkystudio.codegen.logic_generators_extra import register as _reg_logic
        _reg_logic(logic_generator)
    except Exception as exc:
        print(f"[conky-studio] logic_generators_extra: {exc}")
    try:
        from conkystudio.codegen.visual_generators_extra import register as _reg_vextra
        _reg_vextra(visual_generator)
    except Exception as exc:
        print(f"[conky-studio] visual_generators_extra: {exc}")
    try:
        from conkystudio.codegen.visual_generators_more import register as _reg_vmore
        _reg_vmore(visual_generator)
    except Exception as exc:
        print(f"[conky-studio] visual_generators_more: {exc}")
    try:
        from conkystudio.codegen.visual_generators_niche import register as _reg_vniche
        _reg_vniche(visual_generator)
    except Exception as exc:
        print(f"[conky-studio] visual_generators_niche: {exc}")


_register_bundled_extension_generators()


