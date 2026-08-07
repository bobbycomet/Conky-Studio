"""
Node graph -> render.lua.

The generator works in two passes:

  1. build_refresh_sources() walks every data-source node that's actually
     wired to something (unused sources are never polled -- no point
     spawning nvidia-smi for a node nobody's listening to) and emits one
     Lua line per node assigning SRC['<node_id>']. Native sources read
     straight from conky_parse; external sources read from a per-family
     cache table (deduplicating e.g. GPU Util + GPU Temp down to a single
     gpu_stats.cache read per refresh) or an execi expression.

  2. Each visual node gets its own draw_node_<id>(cr, W, H) function from
     the matching _gen_visual_<type> below. Bound properties resolve to
     `SRC['<src_id>']`; unbound ones resolve to a Lua literal baked in at
     build time. main_draw_impl() then calls every visual node's function
     in ascending z-order.

Every _gen_visual_* function is registered in _VISUAL_GENERATORS, and
tests/test_codegen_smoke.py asserts that set matches nodes.registry's
"visual" category exactly -- so a node type you can drag onto the canvas
can never silently compile to nothing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from conkystudio.model.project import Project, NodeInstance
from conkystudio.nodes import registry
from conkystudio.codegen.color import lua_rgb_literal
from conkystudio.codegen.lua_framework import FRAMEWORK_LUA

_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def lua_safe_id(node_id: str) -> str:
    """Node ids are already uuid-hex-based (see model.project.new_id) and
    therefore already Lua-identifier-safe, but this is the single place
    that guarantee is enforced, in case a project file was hand-edited."""
    return _IDENT_RE.sub("_", node_id)


def lua_string_literal(s: str) -> str:
    escaped = (s or "").replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{escaped}'"


def lua_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return lua_string_literal(str(value))


# ---------------------------------------------------------------------------
@dataclass
class GenContext:
    project: Project
    used_source_ids: set = field(default_factory=set)
    uses_svg: bool = False

    def resolve(self, node: NodeInstance, prop_key: str) -> str:
        """Lua expression yielding this property's current value at draw time."""
        spec = registry.get(node.type)
        pspec = spec.prop(prop_key)
        edge = self.project.edge_for_prop(node.id, prop_key)
        if edge is not None and pspec is not None and pspec.bindable:
            # SRC[...] is nil until refresh_sources() has run at least once,
            # which (by design -- see build_refresh_sources) doesn't happen
            # until STATS_EVERY frames after startup, while draw calls
            # start immediately -- falling back to the property's own
            # declared default (not a bare 0) keeps that brief window from
            # crashing on nil arithmetic, and shows something type-sensible
            # (a real default, not just a blank/zero flash) until real data
            # arrives.
            fallback = lua_literal(pspec.default)
            return f"(SRC[{lua_string_literal(edge.src_node)}] or {fallback})"
        value = node.props.get(prop_key, pspec.default if pspec else None)
        return lua_literal(value)

    def resolve_const(self, node: NodeInstance, prop_key: str):
        """The raw (unresolved) constant, for properties that can only ever
        be constants (colours, paths, enums) -- never bindable."""
        spec = registry.get(node.type)
        pspec = spec.prop(prop_key)
        return node.props.get(prop_key, pspec.default if pspec else None)


def compute_used_sources(project: Project) -> set:
    """Direct edges only isn't enough once logic nodes exist: a Math node
    might feed another Math node that only THEN feeds a visual. Walk
    backward from every edge target, and whenever the thing we land on is
    itself a logic node, keep walking through ITS inputs too."""
    used: set = set()
    frontier = {e.src_node for e in project.edges}
    while frontier:
        node_id = frontier.pop()
        if node_id in used:
            continue
        used.add(node_id)
        n = project.node(node_id)
        if n is None:
            continue
        if registry.get(n.type).category == "logic":
            for e in project.edges_into(node_id):
                if e.src_node not in used:
                    frontier.add(e.src_node)
    return used


def topological_order(project: Project, used: set) -> list:
    """Kahn's algorithm restricted to `used`, so refresh_sources() computes
    every node's SRC[] entry only after everything it reads from is
    already fresh this frame -- otherwise a logic node chained after
    another logic node could read last frame's stale value instead of a
    silent crash, which would be a much harder bug to notice."""
    deps: dict[str, set] = {}
    for nid in used:
        n = project.node(nid)
        d = set()
        if n is not None and registry.get(n.type).category == "logic":
            d = {e.src_node for e in project.edges_into(nid) if e.src_node in used}
        deps[nid] = d

    ordered: list = []
    done: set = set()
    remaining = set(used)
    while remaining:
        ready = sorted(nid for nid in remaining if deps[nid] <= done)
        if not ready:
            # A cycle (e.g. two logic nodes bound to each other) shouldn't
            # be reachable through the UI (no self-loops, and the canvas
            # doesn't offer a way to wire A<-B<-A without one of those
            # being a no-op), but don't hang the build if one shows up --
            # just drain whatever's left in a stable order instead.
            ready = sorted(remaining)
        for nid in ready:
            ordered.append(nid)
            done.add(nid)
            remaining.discard(nid)
    return ordered


# ---------------------------------------------------------------------------
#  Pass 1: refresh_sources()
# ---------------------------------------------------------------------------

def _native_source_expr(node: NodeInstance) -> tuple[str, str]:
    """Returns (lua_expr, kind) for a source.* native node -- kind is 'number' or 'text'."""
    t = node.type
    p = node.props

    def g(key, default):
        return p.get(key, default)

    if t == "source.cpu_percent":
        core = g("core", "overall")
        expr = "${cpu}" if core == "overall" else f"${{cpu {core}}}"
        return f"safe_number({lua_string_literal(expr)}, SRC[{lua_string_literal(node.id)}] or 0)", "number"
    if t == "source.ram_percent":
        return f"safe_number('${{memperc}}', SRC[{lua_string_literal(node.id)}] or 0)", "number"
    if t == "source.disk_percent":
        path = g("mount_path", "/")
        return f"safe_number('${{fs_used_perc {path}}}', SRC[{lua_string_literal(node.id)}] or 0)", "number"
    if t == "source.net_down":
        iface = g("interface", "auto")
        iface_expr = "resolve_net_iface()" if iface == "auto" else lua_string_literal(iface)
        return (f"safe_number('${{downspeedf ' .. {iface_expr} .. '}}', SRC[{lua_string_literal(node.id)}] or 0)", "number")
    if t == "source.net_up":
        iface = g("interface", "auto")
        iface_expr = "resolve_net_iface()" if iface == "auto" else lua_string_literal(iface)
        return (f"safe_number('${{upspeedf ' .. {iface_expr} .. '}}', SRC[{lua_string_literal(node.id)}] or 0)", "number")
    if t == "source.uptime":
        var = "${uptime}" if g("format", "short") == "long" else "${uptime_short}"
        return f"safe_parse({lua_string_literal(var)}, '')", "text"
    if t == "source.hostname":
        return "safe_parse('${nodename}', '')", "text"
    if t == "source.kernel":
        return "safe_parse('${kernel}', '')", "text"
    if t == "source.process_count":
        return f"safe_number('${{processes}}', SRC[{lua_string_literal(node.id)}] or 0)", "number"
    if t == "source.battery_percent":
        device = g("device", "BAT0")
        guarded = (
            f"(battery_exists({lua_string_literal(device)}) and "
            f"safe_number('${{battery_percent {device}}}', 0) or nil)"
        )
        return guarded, "number"
    if t == "source.datetime":
        fmt = g("strftime_format", "%A, %B %d  %H:%M")
        return f"safe_parse('${{time {fmt}}}', '')", "text"
    if t == "source.greeting":
        return "greeting_for_hour(tonumber(os.date('%H')))", "text"
    if t == "source.cpu_freq":
        core = g("core", "overall")
        expr = "${freq}" if core == "overall" else f"${{freq {core.replace('cpu', '')}}}"
        return f"safe_number({lua_string_literal(expr)}, SRC[{lua_string_literal(node.id)}] or 0)", "number"
    if t == "source.ram_used":
        return "safe_parse('${mem}', '')", "text"
    if t == "source.ram_total":
        return "safe_parse('${memmax}', '')", "text"
    if t == "source.swap_percent":
        return f"safe_number('${{swapperc}}', SRC[{lua_string_literal(node.id)}] or 0)", "number"
    if t == "source.net_total_down":
        iface = g("interface", "auto")
        iface_expr = "resolve_net_iface()" if iface == "auto" else lua_string_literal(iface)
        return f"safe_parse('${{totaldown ' .. {iface_expr} .. '}}', '')", "text"
    if t == "source.net_total_up":
        iface = g("interface", "auto")
        iface_expr = "resolve_net_iface()" if iface == "auto" else lua_string_literal(iface)
        return f"safe_parse('${{totalup ' .. {iface_expr} .. '}}', '')", "text"
    if t == "source.wifi_ssid":
        iface = g("interface", "auto")
        iface_expr = "resolve_net_iface()" if iface == "auto" else lua_string_literal(iface)
        return f"safe_parse('${{wireless_essid ' .. {iface_expr} .. '}}', '')", "text"
    if t == "source.wifi_signal":
        iface = g("interface", "auto")
        iface_expr = "resolve_net_iface()" if iface == "auto" else lua_string_literal(iface)
        return (f"safe_number('${{wireless_link_qual_perc ' .. {iface_expr} .. '}}', "
                f"SRC[{lua_string_literal(node.id)}] or 0)", "number")
    if t in ("source.top_process_name", "source.top_process_cpu", "source.top_process_mem"):
        rank = g("rank", "1")
        field = {"source.top_process_name": "name",
                 "source.top_process_cpu": "cpu",
                 "source.top_process_mem": "mem"}[t]
        expr = f"${{top {field} {rank}}}"
        if field == "name":
            return f"safe_parse({lua_string_literal(expr)}, '')", "text"
        return f"safe_number({lua_string_literal(expr)}, SRC[{lua_string_literal(node.id)}] or 0)", "number"
    # v1.0.6 extension sources
    try:
        from conkystudio.codegen.source_generators_extra import extra_native_source_expr
        extra = extra_native_source_expr(node)
        if extra is not None:
            return extra
    except ImportError:
        pass
    raise ValueError(f"Unhandled native source type: {t}")


def _external_family_key(node: NodeInstance) -> str:
    spec = registry.get(node.type)
    return spec.script_family or node.id


def _external_cache_filename(family_key: str) -> str:
    return f"{family_key}.cache"


def _external_source_lines(node: NodeInstance, script_filenames: dict) -> tuple[list[str], str]:
    """Returns (extra_lines_before_assignment, value_expr). `script_filenames`
    maps family_key -> the .sh filename the builder actually wrote for it."""
    spec = registry.get(node.type)
    p = node.props
    poll_mode = p.get("poll_mode", "execi")
    interval = int(p.get("poll_interval", 5))
    family_key = _external_family_key(node)
    out_key = spec.script_output_key or "value"
    # custom_script is registered with a fixed KIND_TEXT so it's always
    # offered as a source, but each instance carries its own "output_kind"
    # property (see sources_external.py) letting the user -- or
    # legacy_parser.py's fallback-placeholder path -- declare it numeric.
    # That per-instance choice must win over the registry's static kind,
    # or every custom script would render as a string and silently break
    # any numeric binding (Bar/Gauge/History Graph/Math) downstream.
    effective_kind = p.get("output_kind", spec.output_kind) if spec.type == "source.custom_script" else spec.output_kind
    is_text = effective_kind in ("text", "category")

    if poll_mode == "daemon":
        # Custom Script nodes are wrapped by shell_gen.gen_custom_script_wrapper(),
        # which names its cache file "custom_<node_id>.cache" (its `family`
        # local there is f"custom_{node_id}"). family_key here is just the
        # bare node_id (see _external_family_key), so the on-disk filename
        # has to be built the same way the wrapper built it, or this reads
        # a cache file that was never written and silently gets "" / 0.
        cache_filename = (
            f"custom_{family_key}.cache" if spec.type == "source.custom_script"
            else _external_cache_filename(family_key)
        )
        cache_var = f"CACHE_KV[{lua_string_literal(family_key)}]"
        lines = [
            f"if {cache_var} == nil then "
            f"{cache_var} = read_kv_cache(CACHE_DIR .. '/{cache_filename}') end",
        ]
        if is_text:
            expr = f"({cache_var}.{out_key} or '')"
        else:
            expr = f"(tonumber({cache_var}.{out_key}) or SRC[{lua_string_literal(node.id)}] or 0)"
        return lines, expr

    # execi mode
    script_filename = script_filenames.get(family_key, f"{family_key}.sh")
    is_custom = spec.type == "source.custom_script"
    key_arg = "" if is_custom else f" --key {out_key}"
    execi_expr = f"'${{execi {interval} ' .. SCRIPTS_DIR .. '/{script_filename}{key_arg}}}'"
    if is_text:
        return [], f"safe_parse({execi_expr}, '')"
    return [], f"safe_number({execi_expr}, SRC[{lua_string_literal(node.id)}] or 0)"


# node.type -> [(bindable_prop_key, HIST-key suffix), ...]. A node with one
# entry and suffix "" keeps its buffer at HIST[node.id] (history_graph's
# original, unchanged key); a node with several entries -- currently only
# multi_line_graph's three series -- gets one buffer per entry at
# HIST[node.id .. suffix], so three lines on one node don't collide.
_HISTORY_SERIES: dict[str, list[tuple[str, str]]] = {
    "visual.history_graph": [("value", "")],
    "visual.sparkline": [("value", "")],
    "visual.multi_line_graph": [("value_a", "_a"), ("value_b", "_b"), ("value_c", "_c")],
}


def _history_hist_key(node_id: str, suffix: str) -> str:
    return f"{node_id}{suffix}"


_LOGIC_GENERATORS = {}


def logic_generator(node_type):
    def deco(fn):
        _LOGIC_GENERATORS[node_type] = fn
        return fn
    return deco


@logic_generator("logic.math")
def _logic_math(node: NodeInstance, ctx: GenContext) -> str:
    p = node.props
    a = ctx.resolve(node, "input_a")
    b = ctx.resolve(node, "input_b")
    op = p.get("operation", "add")
    if op == "add":
        return f"(({a}) + ({b}))"
    if op == "subtract":
        return f"(({a}) - ({b}))"
    if op == "multiply":
        return f"(({a}) * ({b}))"
    if op == "divide":
        return f"((({b}) ~= 0) and (({a}) / ({b})) or 0)"
    if op == "average":
        return f"((({a}) + ({b})) / 2)"
    if op == "min":
        return f"math.min(({a}), ({b}))"
    if op == "max":
        return f"math.max(({a}), ({b}))"
    return f"({a})"


@logic_generator("logic.conditional")
def _logic_conditional(node: NodeInstance, ctx: GenContext) -> str:
    p = node.props
    inp = ctx.resolve(node, "input")
    cmp_op = p.get("comparison", ">")
    if cmp_op not in (">", ">=", "<", "<=", "=="):
        cmp_op = ">"
    threshold = p.get("threshold", 80.0)
    then_v = p.get("then_value", 1.0)
    else_v = p.get("else_value", 0.0)
    return f"((({inp}) {cmp_op} ({threshold})) and ({then_v}) or ({else_v}))"


@logic_generator("logic.string_format")
def _logic_string_format(node: NodeInstance, ctx: GenContext) -> str:
    p = node.props
    inp = ctx.resolve(node, "input")
    template = lua_string_literal(p.get("template", "{value}"))
    decimals = int(p.get("decimals", 0))
    return (
        "(function() "
        f"local raw = {inp}; local s; "
        f"if type(raw) == 'number' then s = string.format('%.{decimals}f', raw) else s = tostring(raw) end; "
        "local safe = s:gsub('%%', '%%%%'); "
        f"return ({template}):gsub('{{value}}', safe) "
        "end)()"
    )


def _logic_expr(node: NodeInstance, ctx: GenContext) -> str:
    gen = _LOGIC_GENERATORS.get(node.type)
    if gen is None:
        raise ValueError(f"Unhandled logic node type: {node.type} (no generator registered -- "
                          f"if this is a plugin node, check it loaded before build_render_lua ran)")
    return gen(node, ctx)


def build_refresh_sources(ctx: GenContext, script_filenames: dict) -> str:
    project = ctx.project
    lines = ["local function refresh_sources()"]
    cache_reset_families = set()
    body_lines: list[str] = []

    ordered_ids = topological_order(project, ctx.used_source_ids)
    for node_id in ordered_ids:
        node = project.node(node_id)
        if node is None:
            continue
        spec = registry.get(node.type)

        if spec.category == "logic":
            expr = _logic_expr(node, ctx)
            body_lines.append(f"    SRC[{lua_string_literal(node.id)}] = {expr}")
            continue
        if spec.category != "source":
            continue

        if spec.type.startswith("source.") and spec.script_family is None and spec.type != "source.custom_script":
            # native
            expr, _kind = _native_source_expr(node)
            body_lines.append(f"    SRC[{lua_string_literal(node.id)}] = {expr}")
            continue

        if spec.type == "source.custom_script":
            extra, expr = _external_source_lines(node, script_filenames)
            body_lines.extend(f"    {ln}" for ln in extra)
            body_lines.append(f"    SRC[{lua_string_literal(node.id)}] = {expr}")
            continue

        # external, family-backed (cpu_sensors / gpu_stats / disk_sensors / weather)
        family_key = _external_family_key(node)
        if node.props.get("poll_mode", "execi") == "daemon" and family_key not in cache_reset_families:
            cache_reset_families.add(family_key)
        extra, expr = _external_source_lines(node, script_filenames)
        body_lines.extend(f"    {ln}" for ln in extra)
        body_lines.append(f"    SRC[{lua_string_literal(node.id)}] = {expr}")

    if cache_reset_families:
        # Daemon-mode caches are only re-read once per refresh tick (not once
        # per node that shares them) -- CACHE_KV is cleared right before the
        # per-node loop above so the first node in each family does the read
        # and the rest reuse it.
        reset_lines = [f"    CACHE_KV[{lua_string_literal(f)}] = nil" for f in sorted(cache_reset_families)]
        lines.extend(reset_lines)

    lines.extend(body_lines)
    lines.append("end")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
#  Pass 2: per-visual-node draw functions
# ---------------------------------------------------------------------------
_VISUAL_GENERATORS = {}


def visual_generator(node_type):
    def deco(fn):
        _VISUAL_GENERATORS[node_type] = fn
        return fn
    return deco


_SLANT = {True: "CAIRO_FONT_SLANT_ITALIC", False: "CAIRO_FONT_SLANT_NORMAL"}
_WEIGHT = {True: "CAIRO_FONT_WEIGHT_BOLD", False: "CAIRO_FONT_WEIGHT_NORMAL"}


@visual_generator("visual.text")
def _gen_text(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    value_expr = ctx.resolve(node, "value")
    decimals = int(p.get("decimals", 0))
    prefix = lua_string_literal(p.get("prefix", ""))
    suffix = lua_string_literal(p.get("suffix", ""))
    font = lua_string_literal(p.get("font_family", "Sans"))
    size = p.get("font_size", 16)
    align = p.get("align", "left")
    x = p.get("x", 20)
    y = p.get("y", 20)
    r, g, b = _split_rgb(p.get("color", "#FFFFFF"))
    halo = bool(p.get("halo", False))
    slant = _SLANT[bool(p.get("italic", False))]
    weight = _WEIGHT[bool(p.get("bold", False))]

    show = (
        f"        cairo_set_source_rgba(cr, {r}, {g}, {b}, 1)\n"
        f"        cairo_move_to(cr, tx, {y})\n"
        f"        cairo_show_text(cr, text)"
    )
    if halo:
        show = (
            "        cairo_set_source_rgba(cr, 1, 1, 1, 0.5)\n"
            f"        cairo_move_to(cr, tx - 1, {y}); cairo_show_text(cr, text)\n"
            f"        cairo_move_to(cr, tx + 1, {y}); cairo_show_text(cr, text)\n"
            f"        cairo_move_to(cr, tx, {y} - 1); cairo_show_text(cr, text)\n"
            f"        cairo_move_to(cr, tx, {y} + 1); cairo_show_text(cr, text)\n"
        ) + show

    return f'''
local function {fn}(cr, W, H)
    local raw = {value_expr}
    local text
    if type(raw) == 'number' then
        text = string.format('%.{decimals}f', raw)
    else
        text = tostring(raw)
    end
    text = {prefix} .. text .. {suffix}
    cairo_select_font_face(cr, {font}, {slant}, {weight})
    cairo_set_font_size(cr, {size})
    local tx = {x}
    if '{align}' ~= 'left' then
        local ext = cairo_text_extents_t:create()
        cairo_text_extents(cr, text, ext)
        if '{align}' == 'center' then tx = {x} - ext.width / 2 end
        if '{align}' == 'right' then tx = {x} - ext.width end
    end
{show}
end'''


@visual_generator("visual.arc_gauge")
def _gen_arc_gauge(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    value_expr = ctx.resolve(node, "value")
    mn, mx = p.get("min_value", 0.0), p.get("max_value", 100.0)
    cx, cy = p.get("cx", 100), p.get("cy", 100)
    radius, thickness = p.get("radius", 70), p.get("thickness", 10)
    start_deg, sweep_deg = p.get("start_angle_deg", -90), p.get("sweep_deg", 360)
    cap = "CAIRO_LINE_CAP_ROUND" if p.get("cap_style", "round") == "round" else "CAIRO_LINE_CAP_BUTT"
    cr_, cg_, cb_ = _split_rgb(p.get("color", "#4fd1c5"))
    tr_, tg_, tb_ = _split_rgb(p.get("track_color", "#33313a"))
    track_alpha = p.get("track_alpha", 0.6)
    show_value = bool(p.get("show_value_text", True))
    value_font_size = p.get("value_font_size", 20)
    value_suffix = lua_string_literal(p.get("value_suffix", "%"))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha="1",
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
    )

    value_text_block = ""
    if show_value:
        value_text_block = f'''
    if show_text then
        local label = string.format('%.0f', raw) .. {value_suffix}
        cairo_select_font_face(cr, 'Sans', CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
        cairo_set_font_size(cr, {value_font_size})
        local ext = cairo_text_extents_t:create()
        cairo_text_extents(cr, label, ext)
        cairo_set_source_rgba(cr, {cr_}, {cg_}, {cb_}, 1)
        cairo_move_to(cr, {cx} - ext.width / 2, {cy} + ext.height / 2)
        cairo_show_text(cr, label)
    end'''

    return f'''
local function {fn}(cr, W, H)
    local raw = {value_expr}
    local pct = clamp((raw - ({mn})) / (({mx}) - ({mn})), 0, 1)
    local start_a = ({start_deg}) * math.pi / 180
    local sweep_a = ({sweep_deg}) * math.pi / 180
    local show_text = {"true" if show_value else "false"}

    cairo_set_line_cap(cr, {cap})
    cairo_new_path(cr)
    cairo_set_source_rgba(cr, {tr_}, {tg_}, {tb_}, {track_alpha})
    cairo_set_line_width(cr, {thickness})
    cairo_arc(cr, {cx}, {cy}, {radius}, start_a, start_a + sweep_a)
    cairo_stroke(cr)

    cairo_new_path(cr)
{fill_setup}
    cairo_set_line_width(cr, {thickness})
    cairo_arc(cr, {cx}, {cy}, {radius}, start_a, start_a + sweep_a * pct)
    cairo_stroke(cr)
{fill_destroy}
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
{value_text_block}
end'''


@visual_generator("visual.segmented_gauge")
def _gen_segmented_gauge(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    value_expr = ctx.resolve(node, "value")
    mn, mx = p.get("min_value", 0.0), p.get("max_value", 100.0)
    cx, cy = p.get("cx", 100), p.get("cy", 100)
    radius, thickness = p.get("radius", 70), p.get("thickness", 12)
    start_deg, sweep_deg = p.get("start_angle_deg", -90), p.get("sweep_deg", 270)
    segments = int(p.get("segment_count", 12))
    gap_deg = p.get("gap_deg", 4.0)
    cr_, cg_, cb_ = _split_rgb(p.get("color", "#4fd1c5"))
    tr_, tg_, tb_ = _split_rgb(p.get("track_color", "#33313a"))
    show_value = bool(p.get("show_value_text", True))
    value_font_size = p.get("value_font_size", 20)
    value_suffix = lua_string_literal(p.get("value_suffix", "%"))

    value_text_block = ""
    if show_value:
        value_text_block = f'''
    local label = string.format('%.0f', raw) .. {value_suffix}
    cairo_select_font_face(cr, 'Sans', CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, {value_font_size})
    local ext = cairo_text_extents_t:create()
    cairo_text_extents(cr, label, ext)
    cairo_set_source_rgba(cr, {cr_}, {cg_}, {cb_}, 1)
    cairo_move_to(cr, {cx} - ext.width / 2, {cy} + ext.height / 2)
    cairo_show_text(cr, label)'''

    return f'''
local function {fn}(cr, W, H)
    local raw = {value_expr}
    local pct = clamp((raw - ({mn})) / (({mx}) - ({mn})), 0, 1)
    local lit = math.floor(pct * {segments} + 0.5)
    local seg_sweep = (({sweep_deg}) - ({gap_deg}) * ({segments} - 1)) / {segments}
    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)
    for i = 0, {segments} - 1 do
        local seg_start = ({start_deg}) + i * (seg_sweep + ({gap_deg}))
        local a0 = math.rad(seg_start)
        local a1 = math.rad(seg_start + seg_sweep)
        cairo_new_path(cr)
        if i < lit then
            cairo_set_source_rgba(cr, {cr_}, {cg_}, {cb_}, 1)
        else
            cairo_set_source_rgba(cr, {tr_}, {tg_}, {tb_}, 0.6)
        end
        cairo_set_line_width(cr, {thickness})
        cairo_arc(cr, {cx}, {cy}, {radius}, a0, a1)
        cairo_stroke(cr)
    end
{value_text_block}
end'''


@visual_generator("visual.bar")
def _gen_bar(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    value_expr = ctx.resolve(node, "value")
    mn, mx = p.get("min_value", 0.0), p.get("max_value", 100.0)
    x, y = p.get("x", 20), p.get("y", 20)
    w, h = p.get("width", 220), p.get("height", 18)
    orientation = p.get("orientation", "horizontal")
    style = p.get("style", "solid")
    segments = int(p.get("segment_count", 22))
    corner_r = p.get("corner_radius", 4)
    cr_, cg_, cb_ = _split_rgb(p.get("color", "#4fd1c5"))
    tr_, tg_, tb_ = _split_rgb(p.get("track_color", "#33313a"))
    pulse = bool(p.get("pulse_when_critical", False))
    threshold = p.get("critical_threshold", 85.0)
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha="alpha_mul",
        box=(x, y, w, h),
        radial=(x + w / 2, y + h / 2, min(w, h) / 2),
    )

    pulse_block = "local alpha_mul = 1"
    if pulse:
        pulse_block = (
            f"local alpha_mul = 1\n"
            f"    if pct >= (({threshold}) - ({mn})) / (({mx}) - ({mn})) then\n"
            f"        alpha_mul = 0.55 + ((math.sin(wall_clock() * 6) + 1) / 2) * 0.45\n"
            f"    end"
        )

    if style == "segmented":
        body = f'''
    local gap = 2
    local seg_w, seg_h
    if '{orientation}' == 'horizontal' then
        seg_w = ({w} - gap * ({segments} - 1)) / {segments}
        seg_h = {h}
    else
        seg_w = {w}
        seg_h = ({h} - gap * ({segments} - 1)) / {segments}
    end
    local lit = math.floor(pct * {segments} + 0.5)
    for i = 0, {segments} - 1 do
        local sx, sy
        if '{orientation}' == 'horizontal' then
            sx, sy = {x} + i * (seg_w + gap), {y}
        else
            sx, sy = {x}, {y} + {h} - seg_h - i * (seg_h + gap)
        end
        if i < lit then
{fill_setup}
        else
            cairo_set_source_rgba(cr, {tr_}, {tg_}, {tb_}, 0.6)
        end
        cairo_rectangle(cr, sx, sy, seg_w, seg_h)
        cairo_fill(cr)
        if i < lit then
{fill_destroy}
        end
    end'''
    elif style == "trapezoid":
        body = f'''
    bar_trapezoid_path(cr, {x}, {y}, {w}, {h})
    cairo_set_source_rgba(cr, {tr_}, {tg_}, {tb_}, 0.6)
    cairo_fill(cr)
    cairo_save(cr)
    bar_trapezoid_path(cr, {x}, {y}, {w}, {h})
    cairo_clip(cr)
    local fill_w = ('{orientation}' == 'horizontal') and ({w} * pct) or {w}
    local fill_h = ('{orientation}' == 'horizontal') and {h} or ({h} * pct)
    local fill_x = {x}
    local fill_y = ('{orientation}' == 'horizontal') and {y} or ({y} + {h} - fill_h)
{fill_setup}
    cairo_rectangle(cr, fill_x, fill_y, fill_w, fill_h)
    cairo_fill(cr)
{fill_destroy}
    cairo_restore(cr)'''
    else:  # solid
        body = f'''
    rounded_rect(cr, {x}, {y}, {w}, {h}, {corner_r})
    cairo_set_source_rgba(cr, {tr_}, {tg_}, {tb_}, 0.6)
    cairo_fill(cr)
    cairo_save(cr)
    rounded_rect(cr, {x}, {y}, {w}, {h}, {corner_r})
    cairo_clip(cr)
    local fill_w = ('{orientation}' == 'horizontal') and ({w} * pct) or {w}
    local fill_h = ('{orientation}' == 'horizontal') and {h} or ({h} * pct)
    local fill_x = {x}
    local fill_y = ('{orientation}' == 'horizontal') and {y} or ({y} + {h} - fill_h)
{fill_setup}
    cairo_rectangle(cr, fill_x, fill_y, fill_w, fill_h)
    cairo_fill(cr)
{fill_destroy}
    cairo_restore(cr)'''

    return f'''
local function {fn}(cr, W, H)
    local raw = {value_expr}
    local pct = clamp((raw - ({mn})) / (({mx}) - ({mn})), 0, 1)
    {pulse_block}
{body}
end'''


@visual_generator("visual.glow_pulse")
def _gen_glow_pulse(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx = int(p.get("cx", 100))
    cy = int(p.get("cy", 100))
    radius = int(p.get("radius", 60))
    mode = str(p.get("mode", "circle"))
    path = p.get("path", "") or ""
    img_expr = _image_path_expr(path)
    star_points = int(p.get("star_points", 5))
    star_inner = float(p.get("star_inner_ratio", 0.4))
    layers = int(p.get("layers", 4))
    spread = float(p.get("spread", 0.35))
    cr_, cg_, cb_ = _split_rgb(p.get("color", "#4fd1c5"))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha="a",
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
    )
    pulse_hz = float(p.get("pulse_hz", 0.5))
    a_min = float(p.get("alpha_min", 0.15))
    a_max = float(p.get("alpha_max", 0.55))
    # Whether the Trigger socket actually has a wire connected. This is the
    # only reliable way to know "is this bound" -- a resolved trigger value
    # of 0 is indistinguishable from "unbound" at runtime, since an unbound
    # bindable property still resolves to a real Lua literal (its default),
    # never to nil (see GenContext.resolve). Deciding "bound-ness" from the
    # resolved value (or from whether the threshold was left at its default)
    # was tried and removed -- it made changing Trigger threshold silently
    # flip whether an unbound glow pulsed at all. Checking the edge directly,
    # the same way visual.image_icon's swap_trigger handling does, has no
    # such ambiguity.
    has_trigger = ctx.project.edge_for_prop(node.id, "trigger") is not None
    trigger_expr = ctx.resolve(node, "trigger")
    thresh = float(p.get("trigger_threshold", 80.0))
    tmode = str(p.get("trigger_mode", "above"))

    # Image silhouette glow: draw the same PNG scaled up per layer with colour × alpha.
    # Transparent pixels stay transparent; the opaque silhouette expands outward.
    image_block = f'''
    local img = load_image_cached({img_expr})
    if img ~= nil then
        local base = {radius} * 2
        for i = layers, 1, -1 do
            local t = i / layers
            local scale = 1 + spread * t
            local a = (a_min + (a_max - a_min) * pulse) * (1 - t * 0.75) * active
            if a > 0.01 then
                cairo_save(cr)
                -- Tint: multiply source by glow colour via operator
                local side = base * scale
                local ix = {cx} - side / 2
                local iy = {cy} - side / 2
{fill_setup}
{fill_destroy}
                -- Mask-style: paint coloured rect, then use image alpha
                cairo_push_group(cr)
                draw_image_fit(cr, img, ix, iy, side, 0, 1)
                local pattern = cairo_pop_group(cr)
{fill_setup}
                cairo_mask(cr, pattern)
                cairo_pattern_destroy(pattern)
{fill_destroy}
                cairo_restore(cr)
            end
        end
        return
    end
'''

    star_path = f'''
        local n, R, r_in = {star_points}, rad, rad * {star_inner}
        cairo_new_path(cr)
        for k = 0, n * 2 do
            local ang = -math.pi / 2 + k * math.pi / n
            local rr = (k % 2 == 0) and R or r_in
            local px = {cx} + math.cos(ang) * rr
            local py = {cy} + math.sin(ang) * rr
            if k == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
        end
        cairo_close_path(cr)
'''
    tri_path = f'''
        cairo_new_path(cr)
        for k = 0, 3 do
            local ang = -math.pi / 2 + k * (2 * math.pi / 3)
            local px = {cx} + math.cos(ang) * rad
            local py = {cy} + math.sin(ang) * rad
            if k == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
        end
        cairo_close_path(cr)
'''

    return f'''
local function {fn}(cr, W, H)
    local layers = math.max(1, {layers})
    local spread = {spread}
    local pulse = (math.sin(wall_clock() * {pulse_hz} * 2 * math.pi) + 1) / 2
    local a_min, a_max = {a_min}, {a_max}
    local trig = {trigger_expr}
    if type(trig) ~= 'number' then trig = tonumber(trig) or 0 end

    -- Gate only when a wire is actually connected to Trigger; with nothing
    -- wired the glow always pulses, regardless of the threshold's value.
    local active = 1
    if {lua_literal(has_trigger)} then
        if {lua_literal(tmode)} == 'above' then
            active = (trig >= {thresh}) and 1 or 0
        else
            active = (trig <= {thresh}) and 1 or 0
        end
    end

    if active < 1 then return end

    local mode = '{mode}'

    if mode == 'image' then
{image_block}
        -- missing image → fall through to circle
    end

    if mode == 'star' or mode == 'triangle' then
        for i = layers, 1, -1 do
            local t = i / layers
            local rad = {radius} * (1 + spread * t)
            local a = (a_min + (a_max - a_min) * pulse) * (1 - t * 0.7)
            if a > 0.01 then
                if mode == 'star' then
{star_path}
                else
{tri_path}
                end
                cairo_set_line_width(cr, 2 + t * 6)
{fill_setup}
                cairo_stroke(cr)
{fill_destroy}
            end
        end
        return
    end

    -- circle (default)
    for i = layers, 1, -1 do
        local t = i / layers
        local rad = {radius} * (1 + spread * t)
        local a = (a_min + (a_max - a_min) * pulse) * (1 - t * 0.7)
        if a > 0.01 then
            cairo_new_path(cr)
            cairo_arc(cr, {cx}, {cy}, rad, 0, 2 * math.pi)
            cairo_set_line_width(cr, 2 + t * 5)
{fill_setup}
            cairo_stroke(cr)
{fill_destroy}
        end
    end
end'''

@visual_generator("visual.spiral")
def _gen_spiral(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = p.get("cx", 100), p.get("cy", 100)
    turns = p.get("turns", 2.5)
    r0, r1 = p.get("radius_start", 8), p.get("radius_end", 90)
    dash_count = int(p.get("dash_count", 0))
    line_w = p.get("line_width", 2.0)
    cr_, cg_, cb_ = _split_rgb(p.get("color", "#4fd1c5"))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha="1",
        box=(cx - r1, cy - r1, r1 * 2, r1 * 2),
        radial=(cx, cy, r1),
    )
    speed = p.get("rotation_speed_dps", 30.0)

    if dash_count > 0:
        body = f'''
    for d = 0, {dash_count} - 1 do
        local t = d / {dash_count}
        local ang = rot + t * ({turns}) * 2 * math.pi
        local rad = lerp({r0}, {r1}, t)
        local px = ({cx}) + math.cos(ang) * rad
        local py = ({cy}) + math.sin(ang) * rad
        local nx = ({cx}) + math.cos(ang + 0.06) * rad
        local ny = ({cy}) + math.sin(ang + 0.06) * rad
        cairo_new_path(cr)
        cairo_move_to(cr, px, py)
        cairo_line_to(cr, nx, ny)
        cairo_stroke(cr)
    end'''
    else:
        body = f'''
    local steps = 128
    cairo_new_path(cr)
    for i = 0, steps do
        local t = i / steps
        local ang = rot + t * ({turns}) * 2 * math.pi
        local rad = lerp({r0}, {r1}, t)
        local px = ({cx}) + math.cos(ang) * rad
        local py = ({cy}) + math.sin(ang) * rad
        if i == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
    end
    cairo_stroke(cr)'''

    return f'''
local function {fn}(cr, W, H)
    local rot = wall_clock() * ({speed}) * math.pi / 180
{fill_setup}
    cairo_set_line_width(cr, {line_w})
{body}
{fill_destroy}
end'''


@visual_generator("visual.image_icon")
def _gen_image_icon(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    path_expr = _image_path_expr(p.get("path", ""))
    x, y, size = p.get("x", 20), p.get("y", 20), p.get("size", 48)
    rotation_expr = ctx.resolve(node, "rotation_deg")
    opacity = p.get("opacity", 1.0)

    swap_above = _image_path_expr(p.get("swap_above_path", ""))
    swap_below = _image_path_expr(p.get("swap_below_path", ""))
    above_thr = p.get("swap_above_threshold", 70.0)
    below_thr = p.get("swap_below_threshold", 35.0)
    has_trigger = ctx.project.edge_for_prop(node.id, "swap_trigger") is not None
    trigger_expr = ctx.resolve(node, "swap_trigger") if has_trigger else None

    swap_block = "local chosen_path = base_path"
    if has_trigger and (p.get("swap_above_path") or p.get("swap_below_path")):
        parts = ["local chosen_path = base_path", f"local trig = {trigger_expr}"]
        if p.get("swap_above_path"):
            parts.append(f"if trig ~= nil and trig >= ({above_thr}) then chosen_path = {swap_above} end")
        if p.get("swap_below_path"):
            parts.append(f"if trig ~= nil and trig <= ({below_thr}) then chosen_path = {swap_below} end")
        swap_block = "\n    ".join(parts)

    return f'''
local function {fn}(cr, W, H)
    local base_path = {path_expr}
    {swap_block}
    local img = load_image_cached(chosen_path)
    if img == nil then return end
    draw_image_fit(cr, img, {x}, {y}, {size}, {rotation_expr}, {opacity})
end'''


@visual_generator("visual.history_graph")
def _gen_history_graph(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    mn, mx = p.get("min_value", 0.0), p.get("max_value", 100.0)
    x, y = p.get("x", 20), p.get("y", 20)
    w, h = p.get("width", 200), p.get("height", 60)
    fill = bool(p.get("fill", True))
    cr_, cg_, cb_ = _split_rgb(p.get("color", "#4fd1c5"))
    tr_, tg_, tb_ = _split_rgb(p.get("track_color", "#33313a"))
    node_id_lit = lua_string_literal(node.id)
    title_expr = ctx.resolve(node, "title_label")
    tfs = int(p.get("title_font_size", 11))
    ttr, ttg, ttb = _split_rgb(p.get("title_color", "#9aa2ad"))
    area_setup, area_destroy = _lua_fill_source(
        p, alpha="0.25", box=(x, y, w, h),
        radial=(x + w / 2, y + h / 2, min(w, h) / 2))
    line_setup, line_destroy = _lua_fill_source(
        p, alpha="1", box=(x, y, w, h),
        radial=(x + w / 2, y + h / 2, min(w, h) / 2))

    fill_block = ""
    if fill:
        fill_block = f'''
    cairo_line_to(cr, {x} + {w}, {y} + {h})
    cairo_line_to(cr, {x}, {y} + {h})
    cairo_close_path(cr)
{area_setup}
    cairo_fill_preserve(cr)
{area_destroy}'''

    return f'''
local function {fn}(cr, W, H)
    local hist = HIST[{node_id_lit}]
    if hist == nil or #hist < 2 then return end
    local _title = tostring({title_expr} or '')
    if _title ~= '' then
        cairo_select_font_face(cr, 'Sans', CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
        cairo_set_font_size(cr, {tfs})
        cairo_set_source_rgba(cr, {ttr}, {ttg}, {ttb}, 1)
        cairo_move_to(cr, {x}, {y} - 4)
        cairo_show_text(cr, _title)
    end
    cairo_set_source_rgba(cr, {tr_}, {tg_}, {tb_}, 0.6)
    cairo_rectangle(cr, {x}, {y}, {w}, {h})
    cairo_stroke(cr)
    cairo_new_path(cr)
    local n = #hist
    for i = 1, n do
        local v = clamp((hist[i] - ({mn})) / (({mx}) - ({mn})), 0, 1)
        local px = {x} + (i - 1) / (n - 1) * {w}
        local py = {y} + {h} - v * {h}
        if i == 1 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
    end
{fill_block}
{line_setup}
    cairo_set_line_width(cr, 2)
    cairo_stroke(cr)
{line_destroy}
end'''


@visual_generator("visual.sparkline")
def _gen_sparkline(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = p.get("x", 20), p.get("y", 20)
    w, h = p.get("width", 120), p.get("height", 28)
    auto_scale = bool(p.get("auto_scale", True))
    mn, mx = p.get("min_value", 0.0), p.get("max_value", 100.0)
    fill = bool(p.get("fill", False))
    line_width = p.get("line_width", 1.5)
    cr_, cg_, cb_ = _split_rgb(p.get("color", "#4fd1c5"))
    node_id_lit = lua_string_literal(node.id)

    if auto_scale:
        # Fits the line to whatever range the visible samples actually
        # span, rather than a fixed Min/Max -- the point of a sparkline is
        # to show shape/trend, not an absolute scale. Falls back to a
        # 1-unit span if every sample is identical so 0/0 doesn't NaN it.
        scale_block = (
            "local lo, hi = math.huge, -math.huge\n"
            "    for i = 1, n do\n"
            "        if hist[i] < lo then lo = hist[i] end\n"
            "        if hist[i] > hi then hi = hist[i] end\n"
            "    end\n"
            "    if lo == hi then lo, hi = lo - 1, hi + 1 end"
        )
    else:
        scale_block = f"local lo, hi = ({mn}), ({mx})"

    fill_block = ""
    if fill:
        fill_block = f'''
    cairo_line_to(cr, {x} + {w}, {y} + {h})
    cairo_line_to(cr, {x}, {y} + {h})
    cairo_close_path(cr)
    cairo_set_source_rgba(cr, {cr_}, {cg_}, {cb_}, 0.18)
    cairo_fill_preserve(cr)'''

    return f'''
local function {fn}(cr, W, H)
    local hist = HIST[{node_id_lit}]
    if hist == nil or #hist < 2 then return end
    local n = #hist
    {scale_block}
    cairo_new_path(cr)
    for i = 1, n do
        local v = clamp((hist[i] - lo) / (hi - lo), 0, 1)
        local px = {x} + (i - 1) / (n - 1) * {w}
        local py = {y} + {h} - v * {h}
        if i == 1 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
    end
{fill_block}
    cairo_set_source_rgba(cr, {cr_}, {cg_}, {cb_}, 1)
    cairo_set_line_width(cr, {line_width})
    cairo_stroke(cr)
end'''


@visual_generator("visual.multi_line_graph")
def _gen_multi_line_graph(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    title_expr = ctx.resolve(node, "title_label")
    tfs = int(p.get("title_font_size", 11))
    ttr, ttg, ttb = _split_rgb(p.get("title_color", "#9aa2ad"))
    mn, mx = p.get("min_value", 0.0), p.get("max_value", 100.0)
    x, y = p.get("x", 20), p.get("y", 20)
    w, h = p.get("width", 220), p.get("height", 70)
    line_width = p.get("line_width", 2.0)
    tr_, tg_, tb_ = _split_rgb(p.get("track_color", "#33313a"))

    series_blocks = []
    for suffix, color_key in (("_a", "color_a"), ("_b", "color_b"), ("_c", "color_c")):
        value_prop = f"value{suffix}"
        edge = ctx.project.edge_for_prop(node.id, value_prop)
        if edge is None:
            continue  # nothing wired to this slot -- no buffer exists, nothing to draw
        cr_, cg_, cb_ = _split_rgb(p.get(color_key, "#4fd1c5"))
        hist_key = lua_string_literal(_history_hist_key(node.id, suffix))
        series_blocks.append(f'''
    do
        local hist = HIST[{hist_key}]
        if hist ~= nil and #hist >= 2 then
            local n = #hist
            cairo_new_path(cr)
            for i = 1, n do
                local v = clamp((hist[i] - ({mn})) / (({mx}) - ({mn})), 0, 1)
                local px = {x} + (i - 1) / (n - 1) * {w}
                local py = {y} + {h} - v * {h}
                if i == 1 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
            end
            cairo_set_source_rgba(cr, {cr_}, {cg_}, {cb_}, 1)
            cairo_set_line_width(cr, {line_width})
            cairo_stroke(cr)
        end
    end''')

    if not series_blocks:
        # Nothing wired at all yet -- still draw the frame so the node
        # isn't a total no-op while it's being set up in the editor.
        series_blocks = ["    -- no series wired yet"]

    return f'''
local function {fn}(cr, W, H)
    local _title = tostring({title_expr} or '')
    if _title ~= '' then
        cairo_select_font_face(cr, 'Sans', CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
        cairo_set_font_size(cr, {tfs})
        cairo_set_source_rgba(cr, {ttr}, {ttg}, {ttb}, 1)
        cairo_move_to(cr, {x}, {y} - 4)
        cairo_show_text(cr, _title)
    end
    cairo_set_source_rgba(cr, {tr_}, {tg_}, {tb_}, 0.6)
    cairo_rectangle(cr, {x}, {y}, {w}, {h})
    cairo_stroke(cr)
{chr(10).join(series_blocks)}
end'''


@visual_generator("visual.weather_icon")
def _gen_weather_icon(node: NodeInstance, ctx: GenContext) -> str:
    # Direct port of skyrim_anim.lua's draw_weather_icon(): pure Cairo
    # vector strokes/fills chosen by category token, no image assets.
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy, size = p.get("cx", 30), p.get("cy", 30), p.get("size", 28)
    cat_expr = ctx.resolve(node, "category")
    ink_r, ink_g, ink_b = _split_rgb(p.get("color", "#B8A888"))
    gold_r, gold_g, gold_b = _split_rgb("#C9A227")
    # Coordinates below are post cairo_translate(cx, cy), so the gradient box/
    # radius is centred on the local origin rather than the node's cx/cy.
    ink_setup, ink_destroy = _lua_fill_source(p, alpha="1", box=("-r", "-r", "r*2", "r*2"), radial=("0", "0", "r"))
    fog_setup, fog_destroy = _lua_fill_source(p, alpha="0.9", box=("-r", "-r", "r*2", "r*2"), radial=("0", "0", "r"))

    return f'''
local function {fn}(cr, W, H)
    local category = tostring({cat_expr})
    local r = ({size}) / 2
    cairo_save(cr)
    cairo_translate(cr, {cx}, {cy})

    if category == 'clear' or category == 'hot' then
        if category == 'hot' then cairo_set_source_rgba(cr, 0.75, 0.30, 0.10, 1)
        else cairo_set_source_rgba(cr, {gold_r}, {gold_g}, {gold_b}, 1) end
        for i = 0, 7 do
            local a = i * math.pi / 4
            cairo_move_to(cr, math.cos(a) * r * 0.55, math.sin(a) * r * 0.55)
            cairo_line_to(cr, math.cos(a) * r, math.sin(a) * r)
            cairo_set_line_width(cr, 1.6)
            cairo_stroke(cr)
        end
        cairo_new_sub_path(cr)
        cairo_arc(cr, 0, 0, r * 0.5, 0, 2 * math.pi)
        cairo_fill(cr)
    elseif category == 'cloud' or category == 'overcast' then
{ink_setup}
        cairo_new_sub_path(cr); cairo_arc(cr, -r*0.35, r*0.15, r*0.42, 0, 2*math.pi)
        cairo_new_sub_path(cr); cairo_arc(cr,  r*0.15, -r*0.05, r*0.5, 0, 2*math.pi)
        cairo_new_sub_path(cr); cairo_arc(cr,  r*0.5,  r*0.2, r*0.32, 0, 2*math.pi)
        cairo_fill(cr)
{ink_destroy}
    elseif category == 'rain' or category == 'storm' then
{ink_setup}
        cairo_new_sub_path(cr); cairo_arc(cr, -r*0.2, -r*0.1, r*0.5, 0, 2*math.pi)
        cairo_new_sub_path(cr); cairo_arc(cr,  r*0.3, -r*0.15, r*0.35, 0, 2*math.pi)
        cairo_fill(cr)
{ink_destroy}
        cairo_set_source_rgba(cr, 0.20, 0.30, 0.45, 1)
        cairo_set_line_width(cr, 1.6)
        for _, dx in ipairs({{-r*0.3, 0, r*0.35}}) do
            cairo_move_to(cr, dx, r*0.35)
            cairo_line_to(cr, dx - r*0.12, r*0.85)
            cairo_stroke(cr)
        end
        if category == 'storm' then
            cairo_set_source_rgba(cr, 0.55, 0.42, 0.10, 1)
            cairo_move_to(cr, r*0.05, r*0.3)
            cairo_line_to(cr, -r*0.15, r*0.7)
            cairo_line_to(cr, r*0.05, r*0.7)
            cairo_line_to(cr, -r*0.1, r*1.05)
            cairo_stroke(cr)
        end
    elseif category == 'snow' or category == 'cold' then
        cairo_set_source_rgba(cr, 0.30, 0.42, 0.55, 1)
        cairo_set_line_width(cr, 1.6)
        for i = 0, 2 do
            local a = i * math.pi / 3
            cairo_move_to(cr, -math.cos(a)*r*0.8, -math.sin(a)*r*0.8)
            cairo_line_to(cr,  math.cos(a)*r*0.8,  math.sin(a)*r*0.8)
            cairo_stroke(cr)
        end
    elseif category == 'fog' then
{fog_setup}
        cairo_set_line_width(cr, 2)
        for i, dy in ipairs({{-r*0.4, 0, r*0.4}}) do
            cairo_move_to(cr, -r*0.75, dy)
            cairo_line_to(cr,  r*0.75, dy)
            cairo_stroke(cr)
        end
{fog_destroy}
    elseif category == 'wind' then
{ink_setup}
        cairo_set_line_width(cr, 1.8)
        for i, dy in ipairs({{-r*0.35, r*0, r*0.35}}) do
            cairo_move_to(cr, -r*0.8, dy)
            cairo_line_to(cr, r*0.5 - (i%2)*r*0.2, dy)
            cairo_line_to(cr, r*0.7 - (i%2)*r*0.2, dy - r*0.18)
            cairo_stroke(cr)
        end
{ink_destroy}
    elseif category == 'dust' then
        cairo_set_source_rgba(cr, 0.55, 0.42, 0.20, 1)
        for _, pt in ipairs({{{{-r*0.4,-r*0.2}},{{r*0.1,-r*0.4}},{{r*0.4,r*0.1}},{{-r*0.1,r*0.4}}}}) do
            cairo_new_sub_path(cr)
            cairo_arc(cr, pt[1], pt[2], r*0.14, 0, 2*math.pi)
            cairo_fill(cr)
        end
    else
        cairo_set_source_rgba(cr, {gold_r}, {gold_g}, {gold_b}, 1)
        cairo_move_to(cr, 0, -r); cairo_line_to(cr, r, 0)
        cairo_line_to(cr, 0, r); cairo_line_to(cr, -r, 0)
        cairo_close_path(cr)
        cairo_set_line_width(cr, 1.6)
        cairo_stroke(cr)
    end

    cairo_restore(cr)
end'''


@visual_generator("visual.album_art")
def _gen_album_art(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y, size = p.get("x", 20), p.get("y", 20), p.get("size", 96)
    corner_r = p.get("corner_radius", 0)
    art_filename = f"album_art_{node.id}.png"
    node_id_lit = lua_string_literal(node.id)

    clip_block = ""
    if corner_r:
        clip_block = f"        rounded_rect(cr, {x}, {y}, {size}, {size}, {corner_r})\n        cairo_clip(cr)\n"

    return f'''
local {fn}_cached = nil
local function {fn}(cr, W, H)
    if {fn}_cached == nil or frame % STATS_EVERY == 0 then
        {fn}_cached = load_image_periodic(CACHE_DIR .. '/{art_filename}', {node_id_lit})
    end
    if {fn}_cached == nil then return end
    cairo_save(cr)
{clip_block}    draw_image_fit(cr, {fn}_cached, {x}, {y}, {size}, 0, 1)
    cairo_restore(cr)
end'''


@visual_generator("visual.icon_glyph")
def _gen_icon_glyph(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    char_expr = ctx.resolve(node, "character")
    input_mode = p.get("input_mode", "character")
    font = lua_string_literal(p.get("font_family", "Sans"))
    x, y, size = p.get("x", 20), p.get("y", 20), p.get("size", 32)
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha="1",
        box=(x, y - size, size, size),
        radial=(x + size / 2, y - size / 2, size / 2),
    )

    if input_mode == "codepoint":
        char_resolve = f"utf8_encode(tonumber(tostring({char_expr}), 16) or 0x3F)"
    else:
        char_resolve = f"tostring({char_expr})"

    return f'''
local function {fn}(cr, W, H)
    local ch = {char_resolve}
    cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, {size})
{fill_setup}
    cairo_move_to(cr, {x}, {y})
    cairo_show_text(cr, ch)
{fill_destroy}
end'''


@visual_generator("visual.text_list")
def _gen_text_list(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    value_expr = ctx.resolve(node, "value")
    x, y = p.get("x", 20), p.get("y", 20)
    max_lines = int(p.get("max_lines", 10))
    line_h = p.get("line_height", 18)
    font = lua_string_literal(p.get("font_family", "Sans"))
    size = p.get("font_size", 12)
    block_h = max_lines * line_h
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha="1",
        box=(x, y - line_h, 240, block_h + line_h),
        radial=(x + 120, y + block_h / 2, max(120, block_h / 2)),
    )

    return f'''
local function {fn}(cr, W, H)
    local raw = {value_expr}
    local text = (type(raw) == 'string') and raw or tostring(raw)
    cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, {size})
{fill_setup}
    local line_num = 0
    for line in text:gmatch('[^\\n]+') do
        if line_num >= {max_lines} then break end
        cairo_move_to(cr, {x}, {y} + line_num * {line_h})
        cairo_show_text(cr, line)
        line_num = line_num + 1
    end
{fill_destroy}
end'''


@visual_generator("visual.moon_phase")
def _gen_moon_phase(node: NodeInstance, ctx: GenContext) -> str:
    """Phase-accurate moon disc + labels. Brackets frame the widget (moon +
    labels), not the whole canvas — length/thickness are user-editable."""
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx = int(p.get("cx", 50))
    cy = int(p.get("cy", 160))
    radius = int(p.get("radius", 36))
    show_labels = bool(p.get("show_labels", True))
    label_gap = int(p.get("label_gap", 26))
    font = lua_string_literal(p.get("font_family", "Sans"))
    name_size = int(p.get("font_size", 15))
    detail_size = int(p.get("detail_font_size", 12))
    lit_r, lit_g, lit_b = _split_rgb(p.get("color", "#26fdf1"))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha="1",
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
    )
    dark_r, dark_g, dark_b = _split_rgb(p.get("dark_color", "#0a2226"))
    rim_r, rim_g, rim_b = _split_rgb(p.get("rim_color", "#0fb7ad"))
    text_r, text_g, text_b = _split_rgb(p.get("text_color", "#5fd8ce"))
    show_brackets = bool(p.get("show_brackets", True))
    bracket_pad = int(p.get("bracket_pad", 12))
    bracket_len = int(p.get("bracket_length", 18))
    bracket_th = float(p.get("bracket_thickness", 2.0))
    southern = "true" if p.get("southern_hemisphere") else "false"

    # Labels sit to the right of the moon; estimate text block width for bracket box
    labels_block = ""
    label_w_expr = "0"
    if show_labels:
        label_w_expr = f"({label_gap} + 200)"  # room for phase + eclipse lines without clipping
        labels_block = f'''
    local text_x = {cx} + {radius} + {label_gap}
    cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
    cairo_set_font_size(cr, {name_size})
    cairo_set_source_rgba(cr, {lit_r}, {lit_g}, {lit_b}, 1)
    cairo_move_to(cr, text_x, {cy} - 14)
    cairo_show_text(cr, name)
    cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, {detail_size})
    cairo_set_source_rgba(cr, {text_r}, {text_g}, {text_b}, 0.9)
    cairo_move_to(cr, text_x, {cy} + 6)
    cairo_show_text(cr, string.format('%d%% ILLUMINATED', math.floor(illum + 0.5)))
    cairo_move_to(cr, text_x, {cy} + 24)
    cairo_show_text(cr, string.format('%s in %d d', next_event, math.floor(math.abs(next_days) + 0.5)))
    if blood_soon or blood_near then
        cairo_move_to(cr, text_x, {cy} + 42)
        local ed = math.floor(math.abs(next_blood_days) + 0.5)
        cairo_show_text(cr, string.format('Eclipse ~%dd (%s)', ed, hemi))
    elseif solar_near then
        cairo_move_to(cr, text_x, {cy} + 42)
        cairo_show_text(cr, string.format('Solar season (%s)', hemi))
    end
'''

    brackets_block = ""
    if show_brackets:
        # Box hugs the moon (+ labels if on), not the full window
        brackets_block = f'''
    do
        local content_w = {radius} * 2 + {label_w_expr}
        local content_h = math.max({radius} * 2, 78)
        local bx = {cx} - {radius} - {bracket_pad}
        local by = {cy} - content_h / 2 - {bracket_pad}
        local bw = content_w + {bracket_pad} * 2
        local bh = content_h + {bracket_pad} * 2
        local blen = math.min({bracket_len}, bw / 2, bh / 2)
        cairo_set_source_rgba(cr, {lit_r}, {lit_g}, {lit_b}, 0.6)
        cairo_set_line_width(cr, {bracket_th})
        cairo_new_path(cr)
        cairo_move_to(cr, bx, by + blen); cairo_line_to(cr, bx, by); cairo_line_to(cr, bx + blen, by)
        cairo_move_to(cr, bx + bw - blen, by); cairo_line_to(cr, bx + bw, by); cairo_line_to(cr, bx + bw, by + blen)
        cairo_move_to(cr, bx, by + bh - blen); cairo_line_to(cr, bx, by + bh); cairo_line_to(cr, bx + blen, by + bh)
        cairo_move_to(cr, bx + bw - blen, by + bh); cairo_line_to(cr, bx + bw, by + bh); cairo_line_to(cr, bx + bw, by + bh - blen)
        cairo_stroke(cr)
    end
'''

    return f'''
local function {fn}(cr, W, H)
    local SYNODIC = 29.530588853
    local KNOWN_NEW = 2451549.5
    local NAMES = {{'New Moon','Waxing Crescent','First Quarter','Waxing Gibbous',
                   'Full Moon','Waning Gibbous','Last Quarter','Waning Crescent'}}
    local jd = os.time() / 86400 + 2440587.5
    local phase = ((jd - KNOWN_NEW) / SYNODIC) % 1
    if phase < 0 then phase = phase + 1 end
    local name = NAMES[(math.floor(phase * 8 + 0.5) % 8) + 1]
    local illum = (1 - math.cos(phase * 2 * math.pi)) / 2 * 100
    local days_to_full = ((0.5 - phase) % 1) * SYNODIC
    local days_to_new  = ((1.0 - phase) % 1) * SYNODIC
    -- Approximate total lunar eclipses (blood moons). JD mid-eclipse centroids (±1 day).
    local LUNAR_ECL = {{
        2460257.0, -- 2023-11-08 total
        2460748.8, -- 2025-03-14 total
        2460926.2, -- 2025-09-07 total
        2461103.0, -- 2026-03-03 total
        2461280.7, -- 2026-08-27/28 deep partial
        2462137.2, -- 2028-12-31 / 2029-01-01 total
        2462313.6, -- 2029-06-26
        2462491.5, -- 2029-12-20
        2462668.2, -- 2030-06-15
        2462845.0, -- 2030-12-09
        2463348.0, -- 2032-04-25
        2463524.0, -- 2032-10-18
        2463702.0, -- 2033-04-14
        2463879.0, -- 2033-10-08
    }}
    local next_blood_days = 9999
    for _, ejd in ipairs(LUNAR_ECL) do
        local d = ejd - jd
        if d >= -0.6 and d < next_blood_days then
            next_blood_days = d
        end
    end
    local blood_near = next_blood_days >= -0.6 and next_blood_days <= 1.2
    local blood_soon = next_blood_days > 1.2 and next_blood_days < 90
    local ECLIPSE_SEASON = 173.31
    local KNOWN_SOLAR = 2460109.0
    local solar_phase = ((jd - KNOWN_SOLAR) / ECLIPSE_SEASON) % 1
    if solar_phase < 0 then solar_phase = solar_phase + 1 end
    local days_to_solar_season = ((0 - solar_phase) % 1) * ECLIPSE_SEASON
    if days_to_solar_season > ECLIPSE_SEASON / 2 then
        days_to_solar_season = days_to_solar_season - ECLIPSE_SEASON
    end
    local solar_near = math.abs(days_to_solar_season) < 8 and days_to_new < 3
    local hemi = ({southern} and 'S' or 'N')
    local next_event, next_days
    if blood_near then
        next_event, next_days = 'BLOOD', math.max(0, next_blood_days)
        name = 'Blood Moon'
    elseif blood_soon and days_to_full <= days_to_new and days_to_full < 16 then
        next_event, next_days = 'BLOOD', next_blood_days
    elseif solar_near then
        next_event, next_days = 'SOLAR', math.max(0, days_to_new)
    elseif days_to_full <= days_to_new then
        next_event, next_days = 'FULL', days_to_full
    else
        next_event, next_days = 'NEW', days_to_new
    end
{brackets_block}
    cairo_new_path(cr)
    cairo_arc(cr, {cx}, {cy}, {radius}, 0, 2 * math.pi)
    cairo_set_source_rgba(cr, {dark_r}, {dark_g}, {dark_b}, 1)
    cairo_fill(cr)
    local gamma = -math.cos(phase * 2 * math.pi)
    local waxing = phase < 0.5
    if {southern} then waxing = not waxing end
    cairo_save(cr)
    cairo_new_path(cr)
    if waxing then
        cairo_arc(cr, {cx}, {cy}, {radius}, -math.pi / 2, math.pi / 2)
    else
        cairo_arc(cr, {cx}, {cy}, {radius}, math.pi / 2, 3 * math.pi / 2)
    end
    cairo_translate(cr, {cx}, {cy})
    cairo_scale(cr, gamma, 1)
    cairo_translate(cr, -{cx}, -{cy})
    if waxing then
        cairo_arc(cr, {cx}, {cy}, {radius}, math.pi / 2, 3 * math.pi / 2)
    else
        cairo_arc(cr, {cx}, {cy}, {radius}, -math.pi / 2, math.pi / 2)
    end
    cairo_close_path(cr)
{fill_setup}
    cairo_fill(cr)
{fill_destroy}
    cairo_restore(cr)
    cairo_new_path(cr)
    cairo_arc(cr, {cx}, {cy}, {radius}, 0, 2 * math.pi)
    cairo_set_source_rgba(cr, {rim_r}, {rim_g}, {rim_b}, 0.6)
    cairo_set_line_width(cr, 1)
    cairo_stroke(cr)
{labels_block}
end'''


@visual_generator("visual.corner_brackets")
def _gen_corner_brackets(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x = int(p.get("x", 20))
    y = int(p.get("y", 20))
    w = int(p.get("width", 200))
    h = int(p.get("height", 120))
    arm = int(p.get("arm_length", 20))
    th = float(p.get("thickness", 2.0))
    r, g, b = _split_rgb(p.get("color", "#26fdf1"))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha=str(float(p.get("opacity", 1.0))),
        box=(x, y, w, h),
        radial=(x + w / 2, y + h / 2, min(w, h) / 2),
    )
    opacity = float(p.get("opacity", 0.6))
    tl = bool(p.get("top_left", True))
    tr = bool(p.get("top_right", True))
    bl = bool(p.get("bottom_left", True))
    br = bool(p.get("bottom_right", True))

    parts = []
    if tl:
        parts.append(f"cairo_move_to(cr, {x}, {y} + blen); cairo_line_to(cr, {x}, {y}); cairo_line_to(cr, {x} + blen, {y})")
    if tr:
        parts.append(f"cairo_move_to(cr, {x} + {w} - blen, {y}); cairo_line_to(cr, {x} + {w}, {y}); cairo_line_to(cr, {x} + {w}, {y} + blen)")
    if bl:
        parts.append(f"cairo_move_to(cr, {x}, {y} + {h} - blen); cairo_line_to(cr, {x}, {y} + {h}); cairo_line_to(cr, {x} + blen, {y} + {h})")
    if br:
        parts.append(f"cairo_move_to(cr, {x} + {w} - blen, {y} + {h}); cairo_line_to(cr, {x} + {w}, {y} + {h}); cairo_line_to(cr, {x} + {w}, {y} + {h} - blen)")
    path_body = "\n    ".join(parts) if parts else "-- no corners enabled"

    return f'''
local function {fn}(cr, W, H)
    local blen = math.min({arm}, {w} / 2, {h} / 2)
    {fill_setup}
    cairo_set_line_width(cr, {th})
    cairo_new_path(cr)
    {path_body}
    cairo_stroke(cr)
{fill_destroy}
end'''


@visual_generator("visual.custom_lua")
def _gen_custom_lua(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    code = node.props.get("code", "") or ""
    indented = "\n".join(("    " + line) if line.strip() else line for line in code.splitlines())
    x = int(node.props.get("x", 0) or 0)
    y = int(node.props.get("y", 0) or 0)
    # Inject bound Data inputs as locals in1..in12. Unwired slots are nil
    # (not 0) so imported Lua can do: tonumber(in1) or safe_number('${cpu}', 0)
    # without treating "not wired" as a real zero reading.
    inj_lines = []
    for i in range(1, 13):
        key = f"in{i}"
        edge = ctx.project.edge_for_prop(node.id, key)
        if edge is not None:
            expr = ctx.resolve(node, key)
            inj_lines.append(f"    local {key} = {expr}")
        else:
            inj_lines.append(f"    local {key} = nil")
    injections = "\n".join(inj_lines)
    return f'''
local function {fn}(cr, W, H)
    cairo_save(cr)
    cairo_translate(cr, {x}, {y})
{injections}
{indented}
    cairo_restore(cr)
end'''

@visual_generator("visual.radar_sweep")
def _gen_radar_sweep(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx = int(p.get("cx", 100))
    cy = int(p.get("cy", 100))
    radius = int(p.get("radius", 68))
    ring_count = int(p.get("ring_count", 3))
    show_cross = bool(p.get("show_crosshairs", True))
    trail = int(p.get("trail_length", 24))
    speed = float(p.get("sweep_speed_dps", 90.0))
    pr, pg, pb = _split_rgb(p.get("color", "#26fdf1"))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha="alpha",
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
    )
    dr, dg, db = _split_rgb(p.get("dim_color", "#0fb7ad"))
    br, bg, bb = _split_rgb(p.get("blip_color", "#ffcf5c"))
    blip_count = int(p.get("blip_count", 3))
    blip_seed = int(p.get("blip_seed", 1))
    cross_block = ""
    if show_cross:
        cross_block = f'''
    cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.25)
    cairo_set_line_width(cr, 1)
    cairo_new_path(cr); cairo_move_to(cr, {cx} - {radius}, {cy}); cairo_line_to(cr, {cx} + {radius}, {cy}); cairo_stroke(cr)
    cairo_new_path(cr); cairo_move_to(cr, {cx}, {cy} - {radius}); cairo_line_to(cr, {cx}, {cy} + {radius}); cairo_stroke(cr)
'''
    return f'''
local function {fn}(cr, W, H)
    local cx, cy, r = {cx}, {cy}, {radius}
    local rings = math.max(1, {ring_count})
    local trail = math.max(4, {trail})
    local speed = {speed}
    local n_blips = math.max(0, {blip_count})
    local seed = {blip_seed}

    for i = 1, rings do
        local rr = r * i / rings
        cairo_new_path(cr)
        cairo_arc(cr, cx, cy, rr, 0, 2 * math.pi)
        cairo_set_line_width(cr, 1)
        cairo_set_source_rgba(cr, {dr}, {dg}, {db}, 0.25)
        cairo_stroke(cr)
    end
{cross_block}
    local sweep = (wall_clock() * speed) % 360
    for i = 0, trail - 1 do
        local a = math.rad(sweep - i * 2 - 90)
        local alpha = (1 - i / trail) * 0.5
        cairo_set_source_rgba(cr, {pr}, {pg}, {pb}, alpha)
        cairo_set_line_width(cr, 2)
        cairo_new_path(cr)
        cairo_move_to(cr, cx, cy)
        cairo_line_to(cr, cx + math.cos(a) * r, cy + math.sin(a) * r)
        cairo_stroke(cr)
    end

    for b = 1, n_blips do
        local deg = ((seed * 37 + b * 97) % 360)
        local rr = 0.25 + ((seed * 13 + b * 41) % 70) / 100
        local diff = math.abs(((sweep - deg + 180) % 360) - 180)
        local flare = math.max(0, 1 - diff / 30)
        local a = math.rad(deg - 90)
        local bx = cx + math.cos(a) * r * rr
        local by = cy + math.sin(a) * r * rr
        cairo_set_source_rgba(cr, {br}, {bg}, {bb}, 0.4 + flare * 0.6)
        cairo_new_path(cr)
        cairo_arc(cr, bx, by, 2.5 + flare * 3, 0, 2 * math.pi)
        cairo_fill(cr)
    end
end'''


@visual_generator("visual.reactor_gauge")
def _gen_reactor_gauge(node: NodeInstance, ctx: GenContext) -> str:
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

@visual_generator("visual.analog_clock")
def _gen_analog_clock(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    state_key = lua_string_literal(f"analog_clock_{node.id}")
    p = node.props
    cx = int(p.get("cx", 120))
    cy = int(p.get("cy", 120))
    radius = int(p.get("radius", 80))
    show_seconds = bool(p.get("show_seconds", True))
    smooth_seconds = bool(p.get("smooth_seconds", True))
    show_numerals = bool(p.get("show_numerals", True))
    show_minute_ticks = bool(p.get("show_minute_ticks", True))
    show_digital = bool(p.get("show_digital", False))
    digital_with_seconds = bool(p.get("digital_with_seconds", True))
    font = lua_string_literal(p.get("font_family", "Share Tech Mono"))
    numeral_size = int(p.get("numeral_size", 14))
    digital_size = int(p.get("digital_size", 12))
    face_r, face_g, face_b = _split_rgb(p.get("face_color", "#0a2226"))
    # Map face_color through gradient props (color=face via temporary)
    _face_props = dict(p)
    _face_props["color"] = p.get("face_color", "#0a2226")
    if "color_end" not in _face_props or not _face_props.get("color_end"):
        _face_props["color_end"] = p.get("color_end", "#0a2226")
    face_setup, face_destroy = _lua_fill_source(
        _face_props, alpha="1",
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
    )
    rim_r, rim_g, rim_b = _split_rgb(p.get("rim_color", "#0fb7ad"))
    tick_r, tick_g, tick_b = _split_rgb(p.get("tick_color", "#26fdf1"))
    num_r, num_g, num_b = _split_rgb(p.get("numeral_color", "#5fd8ce"))
    hr_r, hr_g, hr_b = _split_rgb(p.get("hour_hand_color", "#26fdf1"))
    mn_r, mn_g, mn_b = _split_rgb(p.get("minute_hand_color", "#26fdf1"))
    sc_r, sc_g, sc_b = _split_rgb(p.get("second_hand_color", "#ffcf5c"))
    hub_r, hub_g, hub_b = _split_rgb(p.get("hub_color", "#ffcf5c"))
    rim_th = float(p.get("rim_thickness", 2.0))

    numerals_block = ""
    if show_numerals:
        numerals_block = f'''
    cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, {numeral_size})
    cairo_set_source_rgba(cr, {num_r}, {num_g}, {num_b}, 0.95)
    for h = 1, 12 do
        local a = math.rad(h * 30 - 90)
        local tx = {cx} + math.cos(a) * ({radius} * 0.72)
        local ty = {cy} + math.sin(a) * ({radius} * 0.72)
        local label = tostring(h)
        local ext = cairo_text_extents_t:create()
        cairo_text_extents(cr, label, ext)
        cairo_move_to(cr, tx - ext.width / 2 - ext.x_bearing, ty + ext.height / 2)
        cairo_show_text(cr, label)
    end
'''

    minute_ticks_block = ""
    if show_minute_ticks:
        minute_ticks_block = f'''
    for i = 0, 59 do
        if i % 5 ~= 0 then
            local a = math.rad(i * 6 - 90)
            local x1 = {cx} + math.cos(a) * ({radius} - 4)
            local y1 = {cy} + math.sin(a) * ({radius} - 4)
            local x2 = {cx} + math.cos(a) * ({radius} - 10)
            local y2 = {cy} + math.sin(a) * ({radius} - 10)
            cairo_new_path(cr)
            cairo_move_to(cr, x1, y1)
            cairo_line_to(cr, x2, y2)
            cairo_set_line_width(cr, 1)
            cairo_set_source_rgba(cr, {tick_r}, {tick_g}, {tick_b}, 0.35)
            cairo_stroke(cr)
        end
    end
'''

    if smooth_seconds:
        sec_f_expr = "sec_f"
    else:
        sec_f_expr = "sec"

    seconds_block = ""
    if show_seconds:
        seconds_block = f'''
    do
        local a = math.rad(({sec_f_expr} * 6) - 90)
        local len = {radius} * 0.82
        cairo_new_path(cr)
        cairo_move_to(cr, {cx} - math.cos(a) * ({radius} * 0.12), {cy} - math.sin(a) * ({radius} * 0.12))
        cairo_line_to(cr, {cx} + math.cos(a) * len, {cy} + math.sin(a) * len)
        cairo_set_line_width(cr, 1.5)
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
        cairo_set_source_rgba(cr, {sc_r}, {sc_g}, {sc_b}, 0.95)
        cairo_stroke(cr)
    end
'''

    digital_block = ""
    if show_digital:
        fmt = "%H:%M:%S" if digital_with_seconds else "%H:%M"
        digital_block = f'''
    do
        local dig = os.date('{fmt}')
        cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
        cairo_set_font_size(cr, {digital_size})
        cairo_set_source_rgba(cr, {num_r}, {num_g}, {num_b}, 0.9)
        local ext = cairo_text_extents_t:create()
        cairo_text_extents(cr, dig, ext)
        cairo_move_to(cr, {cx} - ext.width / 2 - ext.x_bearing, {cy} + {radius} + {digital_size} + 6)
        cairo_show_text(cr, dig)
    end
'''

    # Smooth fraction: re-anchor wall_clock whenever civil `sec` changes so
    # the fractional part never runs ahead of/behind os.date and the hand
    # cannot jump backward within the same second.
    time_block = f'''
    local od = os.date('*t')
    local hour = od.hour % 12
    local minute = od.min
    local sec = od.sec
    local sec_f = sec
    if {lua_literal(smooth_seconds)} then
        local st = STATE[{state_key}]
        local w = wall_clock()
        if st == nil or st.sec ~= sec then
            st = {{ sec = sec, t0 = w }}
            STATE[{state_key}] = st
        end
        sec_f = sec + math.min(0.999, math.max(0, w - st.t0))
    end
'''

    return f'''
local function {fn}(cr, W, H)
{time_block}
    -- face fill
    cairo_new_path(cr)
    cairo_arc(cr, {cx}, {cy}, {radius}, 0, 2 * math.pi)
    {face_setup}
    cairo_fill(cr)
    {face_destroy}

    -- rim
    cairo_new_path(cr)
    cairo_arc(cr, {cx}, {cy}, {radius}, 0, 2 * math.pi)
    cairo_set_line_width(cr, {rim_th})
    cairo_set_source_rgba(cr, {rim_r}, {rim_g}, {rim_b}, 0.9)
    cairo_stroke(cr)

    -- hour ticks
    for i = 0, 11 do
        local a = math.rad(i * 30 - 90)
        local x1 = {cx} + math.cos(a) * ({radius} - 4)
        local y1 = {cy} + math.sin(a) * ({radius} - 4)
        local x2 = {cx} + math.cos(a) * ({radius} - 16)
        local y2 = {cy} + math.sin(a) * ({radius} - 16)
        cairo_new_path(cr)
        cairo_move_to(cr, x1, y1)
        cairo_line_to(cr, x2, y2)
        cairo_set_line_width(cr, 2.5)
        cairo_set_source_rgba(cr, {tick_r}, {tick_g}, {tick_b}, 0.9)
        cairo_stroke(cr)
    end
{minute_ticks_block}
{numerals_block}

    -- hour hand
    do
        local a = math.rad((hour + minute / 60 + sec_f / 3600) * 30 - 90)
        local len = {radius} * 0.5
        cairo_new_path(cr)
        cairo_move_to(cr, {cx}, {cy})
        cairo_line_to(cr, {cx} + math.cos(a) * len, {cy} + math.sin(a) * len)
        cairo_set_line_width(cr, 4)
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
        cairo_set_source_rgba(cr, {hr_r}, {hr_g}, {hr_b}, 0.95)
        cairo_stroke(cr)
    end

    -- minute hand
    do
        local a = math.rad((minute + sec_f / 60) * 6 - 90)
        local len = {radius} * 0.72
        cairo_new_path(cr)
        cairo_move_to(cr, {cx}, {cy})
        cairo_line_to(cr, {cx} + math.cos(a) * len, {cy} + math.sin(a) * len)
        cairo_set_line_width(cr, 2.5)
        cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)
        cairo_set_source_rgba(cr, {mn_r}, {mn_g}, {mn_b}, 0.95)
        cairo_stroke(cr)
    end
{seconds_block}

    -- centre hub
    cairo_new_path(cr)
    cairo_arc(cr, {cx}, {cy}, 4, 0, 2 * math.pi)
    cairo_set_source_rgba(cr, {hub_r}, {hub_g}, {hub_b}, 1)
    cairo_fill(cr)
{digital_block}
end'''

@visual_generator("visual.star")
def _gen_star(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx = int(p.get("cx", 80))
    cy = int(p.get("cy", 80))
    radius = int(p.get("radius", 48))
    style = str(p.get("style", "regular"))
    points = int(p.get("points", 5))
    inner_ratio = float(p.get("inner_ratio", 0.4))
    rot_expr = ctx.resolve(node, "rotation_deg")
    do_fill = bool(p.get("fill", True))
    do_stroke = bool(p.get("stroke", True))
    line_width = float(p.get("line_width", 2.0))
    fr, fg, fb = _split_rgb(p.get("color", "#ffcf5c"))
    sr, sg, sb = _split_rgb(p.get("stroke_color", "#26fdf1"))
    opacity = float(p.get("opacity", 1.0))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha=str(opacity),
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
    )

    # Path builders per style — all leave a closed path on `cr`
    if style == "pentagram":
        # Unicursal pentagram: every 2nd vertex of a regular pentagon
        path_lua = f'''
    local n, step, R = 5, 2, {radius}
    local rot = math.rad(rot_deg)
    cairo_new_path(cr)
    for i = 0, n do
        local a = rot + (i * step) * (2 * math.pi / n)
        local x = {cx} + math.cos(a) * R
        local y = {cy} + math.sin(a) * R
        if i == 0 then cairo_move_to(cr, x, y) else cairo_line_to(cr, x, y) end
    end
    cairo_close_path(cr)
'''
    elif style == "star_of_david":
        # Two equilateral triangles, one upright, one inverted
        path_lua = f'''
    local R, rot = {radius}, math.rad(rot_deg)
    cairo_new_path(cr)
    -- upright
    for i = 0, 3 do
        local a = rot - math.pi / 2 + i * (2 * math.pi / 3)
        local x = {cx} + math.cos(a) * R
        local y = {cy} + math.sin(a) * R
        if i == 0 then cairo_move_to(cr, x, y) else cairo_line_to(cr, x, y) end
    end
    cairo_close_path(cr)
    -- inverted (new subpath so both fill)
    for i = 0, 3 do
        local a = rot + math.pi / 2 + i * (2 * math.pi / 3)
        local x = {cx} + math.cos(a) * R
        local y = {cy} + math.sin(a) * R
        if i == 0 then cairo_move_to(cr, x, y) else cairo_line_to(cr, x, y) end
    end
    cairo_close_path(cr)
'''
    elif style == "christmas":
        # Tall 4-point star (elongated on Y) with a small centre diamond feel
        path_lua = f'''
    local R, rot = {radius}, math.rad(rot_deg)
    local rx, ry = R, R * 1.35
    local inner = R * 0.22
    -- 8 verts alternating outer long / inner short, stretched vertically
    cairo_new_path(cr)
    for i = 0, 8 do
        local a = rot + i * (math.pi / 4)
        local out = (i % 2 == 0)
        local rad = out and 1.0 or (inner / R)
        -- stretch Y for the classic tree-topper look
        local x = {cx} + math.cos(a) * R * rad
        local y = {cy} + math.sin(a) * ry * rad
        if i == 0 then cairo_move_to(cr, x, y) else cairo_line_to(cr, x, y) end
    end
    cairo_close_path(cr)
'''
    else:
        # Regular n-point star
        path_lua = f'''
    local n = math.max(3, {points})
    local R, r_in = {radius}, {radius} * {inner_ratio}
    local rot = math.rad(rot_deg)
    cairo_new_path(cr)
    for i = 0, n * 2 do
        local a = rot + i * math.pi / n
        local rad = (i % 2 == 0) and R or r_in
        local x = {cx} + math.cos(a) * rad
        local y = {cy} + math.sin(a) * rad
        if i == 0 then cairo_move_to(cr, x, y) else cairo_line_to(cr, x, y) end
    end
    cairo_close_path(cr)
'''

    fill_stroke = ""
    if do_fill and do_stroke:
        fill_stroke = f'''
{fill_setup}
    cairo_fill_preserve(cr)
{fill_destroy}
    cairo_set_line_width(cr, {line_width})
    cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})
    cairo_stroke(cr)
'''
    elif do_fill:
        fill_stroke = f'''
{fill_setup}
    cairo_fill(cr)
{fill_destroy}
'''
    elif do_stroke:
        fill_stroke = f'''
    cairo_set_line_width(cr, {line_width})
    cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})
    cairo_stroke(cr)
'''

    return f'''
local function {fn}(cr, W, H)
    local rot_deg = {rot_expr}
    if type(rot_deg) ~= 'number' then rot_deg = tonumber(rot_deg) or -90 end
{path_lua}{fill_stroke}
end'''


@visual_generator("visual.triangle")
def _gen_triangle(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx = int(p.get("cx", 80))
    cy = int(p.get("cy", 80))
    size = int(p.get("size", 64))
    rot_expr = ctx.resolve(node, "rotation_deg")
    free = bool(p.get("free_corners", False))
    x1, y1 = int(p.get("x1", 0)), int(p.get("y1", -40))
    x2, y2 = int(p.get("x2", -35)), int(p.get("y2", 24))
    x3, y3 = int(p.get("x3", 35)), int(p.get("y3", 24))
    do_fill = bool(p.get("fill", True))
    do_stroke = bool(p.get("stroke", True))
    line_width = float(p.get("line_width", 2.0))
    fr, fg, fb = _split_rgb(p.get("color", "#4fd1c5"))
    sr, sg, sb = _split_rgb(p.get("stroke_color", "#26fdf1"))
    opacity = float(p.get("opacity", 1.0))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha=str(opacity),
        box=(cx - size, cy - size, size * 2, size * 2),
        radial=(cx, cy, size / 2),
    )

    if free:
        path_lua = f'''
    local rot = math.rad(rot_deg)
    local function xf(ox, oy)
        return {cx} + ox * math.cos(rot) - oy * math.sin(rot),
               {cy} + ox * math.sin(rot) + oy * math.cos(rot)
    end
    local ax, ay = xf({x1}, {y1})
    local bx, by = xf({x2}, {y2})
    local cx_, cy_ = xf({x3}, {y3})
    cairo_new_path(cr)
    cairo_move_to(cr, ax, ay)
    cairo_line_to(cr, bx, by)
    cairo_line_to(cr, cx_, cy_)
    cairo_close_path(cr)
'''
    else:
        path_lua = f'''
    local R, rot = {size} / 2, math.rad(rot_deg)
    cairo_new_path(cr)
    for i = 0, 3 do
        local a = rot + i * (2 * math.pi / 3)
        local x = {cx} + math.cos(a) * R
        local y = {cy} + math.sin(a) * R
        if i == 0 then cairo_move_to(cr, x, y) else cairo_line_to(cr, x, y) end
    end
    cairo_close_path(cr)
'''

    fill_stroke = ""
    if do_fill and do_stroke:
        fill_stroke = f'''
{fill_setup}
    cairo_fill_preserve(cr)
{fill_destroy}
    cairo_set_line_width(cr, {line_width})
    cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})
    cairo_stroke(cr)
'''
    elif do_fill:
        fill_stroke = f'''
{fill_setup}
    cairo_fill(cr)
{fill_destroy}
'''
    elif do_stroke:
        fill_stroke = f'''
    cairo_set_line_width(cr, {line_width})
    cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})
    cairo_stroke(cr)
'''

    return f'''
local function {fn}(cr, W, H)
    local rot_deg = {rot_expr}
    if type(rot_deg) ~= 'number' then rot_deg = tonumber(rot_deg) or -90 end
{path_lua}{fill_stroke}
end'''


@visual_generator("visual.circle")
def _gen_circle(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx = int(p.get("cx", 80))
    cy = int(p.get("cy", 80))
    radius = int(p.get("radius", 40))
    width = int(p.get("width", 0))
    height = int(p.get("height", 0))
    start_deg = int(p.get("start_angle_deg", 0))
    sweep_deg = int(p.get("sweep_deg", 360))
    pie = bool(p.get("pie", False))
    do_fill = bool(p.get("fill", True))
    do_stroke = bool(p.get("stroke", True))
    line_width = float(p.get("line_width", 2.0))
    fr, fg, fb = _split_rgb(p.get("color", "#4fd1c5"))
    sr, sg, sb = _split_rgb(p.get("stroke_color", "#26fdf1"))
    opacity = float(p.get("opacity", 1.0))
    _box = (cx - (width / 2 if width > 0 else radius),
            cy - (height / 2 if height > 0 else radius),
            width if width > 0 else radius * 2,
            height if height > 0 else radius * 2)
    _rad = (cx, cy, (max(width, height) / 2) if width > 0 and height > 0 else radius)
    fill_setup, fill_destroy = _lua_fill_source(p, alpha=str(opacity), box=_box, radial=_rad)

    # Ellipse via scale if width/height set
    if width > 0 and height > 0:
        path_lua = f'''
    local a0 = math.rad({start_deg} - 90)
    local a1 = math.rad({start_deg} + {sweep_deg} - 90)
    cairo_save(cr)
    cairo_translate(cr, {cx}, {cy})
    cairo_scale(cr, {width} / 2, {height} / 2)
    cairo_new_path(cr)
    if {lua_literal(pie)} and {sweep_deg} < 360 then
        cairo_move_to(cr, 0, 0)
        cairo_arc(cr, 0, 0, 1, a0, a1)
        cairo_close_path(cr)
    else
        cairo_arc(cr, 0, 0, 1, a0, a1)
        if {sweep_deg} >= 360 then cairo_close_path(cr) end
    end
'''
        restore = "    cairo_restore(cr)\n"
    else:
        path_lua = f'''
    local a0 = math.rad({start_deg} - 90)
    local a1 = math.rad({start_deg} + {sweep_deg} - 90)
    cairo_new_path(cr)
    if {lua_literal(pie)} and {sweep_deg} < 360 then
        cairo_move_to(cr, {cx}, {cy})
        cairo_arc(cr, {cx}, {cy}, {radius}, a0, a1)
        cairo_close_path(cr)
    else
        cairo_arc(cr, {cx}, {cy}, {radius}, a0, a1)
        if {sweep_deg} >= 360 then cairo_close_path(cr) end
    end
'''
        restore = ""

    fill_stroke = ""
    if do_fill and do_stroke:
        fill_stroke = f'''
{fill_setup}
    cairo_fill_preserve(cr)
{fill_destroy}
    cairo_set_line_width(cr, {line_width})
    cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})
    cairo_stroke(cr)
'''
    elif do_fill:
        fill_stroke = f'''
{fill_setup}
    cairo_fill(cr)
{fill_destroy}
'''
    elif do_stroke:
        fill_stroke = f'''
    cairo_set_line_width(cr, {line_width})
    cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})
    cairo_stroke(cr)
'''

    return f'''
local function {fn}(cr, W, H)
{path_lua}{fill_stroke}{restore}
end'''

@visual_generator("visual.wall_calendar")
def _gen_wall_calendar(node: NodeInstance, ctx: GenContext) -> str:
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x = int(p.get("x", 20))
    y = int(p.get("y", 20))
    cell_w = int(p.get("cell_w", 36))
    cell_h = int(p.get("cell_h", 28))
    show_title = bool(p.get("show_title", True))
    show_weekdays = bool(p.get("show_weekdays", True))
    week_start = str(p.get("week_start", "monday"))
    show_outside = bool(p.get("show_outside_days", False))
    font = lua_string_literal(p.get("font_family", "Sans"))
    title_size = int(p.get("title_size", 16))
    day_size = int(p.get("day_size", 13))
    weekday_size = int(p.get("weekday_size", 11))
    tr, tg, tb = _split_rgb(p.get("title_color", "#FFFFFF"))
    wr, wg, wb = _split_rgb(p.get("weekday_color", "#9aa2ad"))
    dr, dg, db = _split_rgb(p.get("day_color", "#e8eaed"))
    tcr, tcg, tcb = _split_rgb(p.get("today_color", "#4fd1c5"))
    tfr, tfg, tfb = _split_rgb(p.get("today_fill", "#4fd1c5"))
    _tf_props = dict(p)
    _tf_props["color"] = p.get("today_fill", "#4fd1c5")
    today_setup, today_destroy = _lua_fill_source(
        _tf_props, alpha="opacity * 0.35",
        box=("cx + 1", "cy + 1", "cell_w - 2", "cell_h - 2"),
        radial=("cx + cell_w / 2", "cy + cell_h / 2", "math.min(cell_w, cell_h) / 2"),
        indent="                ",
    )
    ocr, ocg, ocb = _split_rgb(p.get("outside_color", "#5c636d"))
    gr, gg, gb = _split_rgb(p.get("grid_color", "#33313a"))
    show_grid = bool(p.get("show_grid", True))
    today_style = str(p.get("today_style", "fill"))
    opacity = float(p.get("opacity", 1.0))

    week_origin = 1 if week_start == "monday" else 0  # Lua os.date wday: Sun=1 … Sat=7
    # For Monday-first we map so Monday is column 0

    return f'''
local function {fn}(cr, W, H)
    local opacity = {opacity}
    local cell_w, cell_h = {cell_w}, {cell_h}
    local origin_x, origin_y = {x}, {y}
    local od = os.date('*t')
    local year, month, today = od.year, od.month, od.day

    local MONTHS = {{'January','February','March','April','May','June',
                    'July','August','September','October','November','December'}}
    local WDAYS_MON = {{'Mo','Tu','We','Th','Fr','Sa','Su'}}
    local WDAYS_SUN = {{'Su','Mo','Tu','We','Th','Fr','Sa'}}
    local wdays = ({lua_literal(week_start == "monday")}) and WDAYS_MON or WDAYS_SUN

    -- First day of this month (wday: 1=Sun .. 7=Sat)
    local first = os.date('*t', os.time({{year=year, month=month, day=1}}))
    local first_wday = first.wday
    -- Column index 0..6 for day 1
    local col0
    if {lua_literal(week_start == "monday")} then
        col0 = (first_wday == 1) and 6 or (first_wday - 2)
    else
        col0 = first_wday - 1
    end

    -- Days in this month
    local next_m = month + 1
    local next_y = year
    if next_m > 12 then next_m = 1; next_y = year + 1 end
    local dim = os.date('*t', os.time({{year=next_y, month=next_m, day=1}}) - 86400).day

    -- Days in previous month (for outside days)
    local prev_dim = os.date('*t', os.time({{year=year, month=month, day=1}}) - 86400).day

    local grid_top = origin_y
    if {lua_literal(show_title)} then
        local title = MONTHS[month] .. ' ' .. tostring(year)
        cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
        cairo_set_font_size(cr, {title_size})
        cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, opacity)
        local ext = cairo_text_extents_t:create()
        cairo_text_extents(cr, title, ext)
        local title_x = origin_x + (7 * cell_w - ext.width) / 2 - ext.x_bearing
        cairo_move_to(cr, title_x, origin_y + {title_size})
        cairo_show_text(cr, title)
        grid_top = origin_y + {title_size} + 10
    end

    if {lua_literal(show_weekdays)} then
        cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
        cairo_set_font_size(cr, {weekday_size})
        cairo_set_source_rgba(cr, {wr}, {wg}, {wb}, opacity)
        for c = 0, 6 do
            local label = wdays[c + 1]
            local ext = cairo_text_extents_t:create()
            cairo_text_extents(cr, label, ext)
            local tx = origin_x + c * cell_w + (cell_w - ext.width) / 2 - ext.x_bearing
            local ty = grid_top + {weekday_size}
            cairo_move_to(cr, tx, ty)
            cairo_show_text(cr, label)
        end
        grid_top = grid_top + {weekday_size} + 8
    end

    -- 6 rows × 7 cols
    local rows = 6
    if {lua_literal(show_grid)} then
        cairo_set_line_width(cr, 1)
        cairo_set_source_rgba(cr, {gr}, {gg}, {gb}, opacity * 0.7)
        for r = 0, rows do
            local gy = grid_top + r * cell_h
            cairo_new_path(cr)
            cairo_move_to(cr, origin_x, gy)
            cairo_line_to(cr, origin_x + 7 * cell_w, gy)
            cairo_stroke(cr)
        end
        for c = 0, 7 do
            local gx = origin_x + c * cell_w
            cairo_new_path(cr)
            cairo_move_to(cr, gx, grid_top)
            cairo_line_to(cr, gx, grid_top + rows * cell_h)
            cairo_stroke(cr)
        end
    end

    cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, {day_size})

    for i = 0, rows * 7 - 1 do
        local day_num = i - col0 + 1
        local is_outside = (day_num < 1) or (day_num > dim)
        local draw_num = day_num
        if day_num < 1 then
            draw_num = prev_dim + day_num
        elseif day_num > dim then
            draw_num = day_num - dim
        end
        if is_outside and not {lua_literal(show_outside)} then
            -- skip
        else
            local c = i % 7
            local r = math.floor(i / 7)
            local cx = origin_x + c * cell_w
            local cy = grid_top + r * cell_h
            local is_today = (not is_outside) and (day_num == today)

            if is_today and '{today_style}' == 'fill' then
{today_setup}
                cairo_rectangle(cr, cx + 1, cy + 1, cell_w - 2, cell_h - 2)
                cairo_fill(cr)
{today_destroy}
            elseif is_today and '{today_style}' == 'ring' then
                cairo_set_source_rgba(cr, {tcr}, {tcg}, {tcb}, opacity)
                cairo_set_line_width(cr, 1.5)
                cairo_rectangle(cr, cx + 2, cy + 2, cell_w - 4, cell_h - 4)
                cairo_stroke(cr)
            end

            local label = tostring(draw_num)
            if is_today and '{today_style}' == 'bold' then
                cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)
                cairo_set_font_size(cr, {day_size} + 1)
            else
                cairo_select_font_face(cr, {font}, CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)
                cairo_set_font_size(cr, {day_size})
            end

            if is_outside then
                cairo_set_source_rgba(cr, {ocr}, {ocg}, {ocb}, opacity * 0.7)
            elseif is_today then
                cairo_set_source_rgba(cr, {tcr}, {tcg}, {tcb}, opacity)
            else
                cairo_set_source_rgba(cr, {dr}, {dg}, {db}, opacity)
            end

            local ext = cairo_text_extents_t:create()
            cairo_text_extents(cr, label, ext)
            local tx = cx + (cell_w - ext.width) / 2 - ext.x_bearing
            local ty = cy + (cell_h + ext.height) / 2
            cairo_move_to(cr, tx, ty)
            cairo_show_text(cr, label)
        end
    end
end'''

@logic_generator("logic.map_range")
def _logic_map_range(node, ctx):
    v = ctx.resolve(node, "value")
    in_min = ctx.resolve(node, "in_min")
    in_max = ctx.resolve(node, "in_max")
    out_min = float(node.props.get("out_min", 0.0))
    out_max = float(node.props.get("out_max", 1.0))
    do_clamp = bool(node.props.get("clamp", True))
    body = (
        f"(function() local v=({v}); local a=({in_min}); local b=({in_max}); "
        f"if b==a then return {out_min} end; local t=(v-a)/(b-a); "
        f"local o={out_min}+t*({out_max}-{out_min}); "
    )
    if do_clamp:
        lo, hi = (out_min, out_max) if out_min <= out_max else (out_max, out_min)
        body += f"if o<{lo} then o={lo} elseif o>{hi} then o={hi} end; "
    body += "return o end)()"
    return body

@logic_generator("logic.clamp")
def _logic_clamp(node, ctx):
    v = ctx.resolve(node, "value")
    mn = float(node.props.get("min_value", 0.0))
    mx = float(node.props.get("max_value", 100.0))
    return f"math.max({mn}, math.min({mx}, ({v})))"

@logic_generator("logic.lerp")
def _logic_lerp(node, ctx):
    a, b, t = ctx.resolve(node, "a"), ctx.resolve(node, "b"), ctx.resolve(node, "t")
    return f"(({a}) + (({b}) - ({a})) * ({t}))"

@logic_generator("logic.threshold")
def _logic_threshold(node, ctx):
    v = ctx.resolve(node, "value")
    cmp_op = node.props.get("comparison", ">=")
    if cmp_op not in (">", ">=", "<", "<=", "=="):
        cmp_op = ">="
    th = float(node.props.get("threshold", 80.0))
    return f"((({v}) {cmp_op} ({th})) and 1 or 0)"

@logic_generator("logic.deadzone")
def _logic_deadzone(node, ctx):
    v = ctx.resolve(node, "value")
    c = float(node.props.get("centre", 0.0))
    r = float(node.props.get("radius", 1.0))
    return f"(function() local v=({v}); local c={c}; local r={r}; if math.abs(v-c)<=r then return c else return v end end)()"

@logic_generator("logic.invert_percent")
def _logic_invert_percent(node, ctx):
    v = ctx.resolve(node, "value")
    return f"math.max(0, math.min(100, 100 - ({v})))"

@logic_generator("logic.scale")
def _logic_scale(node, ctx):
    v = ctx.resolve(node, "value")
    m = float(node.props.get("multiply", 1.0))
    a = float(node.props.get("add", 0.0))
    return f"(({v}) * ({m}) + ({a}))"

@logic_generator("logic.round")
def _logic_round(node, ctx):
    v = ctx.resolve(node, "value")
    d = int(node.props.get("decimals", 0))
    if d <= 0:
        return f"math.floor(({v}) + 0.5)"
    return f"(function() local m=10^{d}; return math.floor(({v})*m+0.5)/m end)()"

@logic_generator("logic.abs")
def _logic_abs(node, ctx):
    return f"math.abs(({ctx.resolve(node, 'value')}))"

@logic_generator("logic.boolean_and")
def _logic_boolean_and(node, ctx):
    a, b = ctx.resolve(node, "input_a"), ctx.resolve(node, "input_b")
    return f"(((({a}) ~= 0) and (({b}) ~= 0)) and 1 or 0)"

@logic_generator("logic.boolean_or")
def _logic_boolean_or(node, ctx):
    a, b = ctx.resolve(node, "input_a"), ctx.resolve(node, "input_b")
    return f"(((({a}) ~= 0) or (({b}) ~= 0)) and 1 or 0)"

@logic_generator("logic.pick")
def _logic_pick(node, ctx):
    s = ctx.resolve(node, "selector")
    a, b = ctx.resolve(node, "input_a"), ctx.resolve(node, "input_b")
    return f"((({s}) >= 0.5) and ({b}) or ({a}))"

@visual_generator("visual.rectangle")
def _gen_rectangle(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 20))
    w, h = int(p.get("width", 160)), int(p.get("height", 80))
    cr = int(p.get("corner_radius", 0))
    do_fill, do_stroke = bool(p.get("fill", True)), bool(p.get("stroke", True))
    lw = float(p.get("line_width", 1.5))
    opacity = float(p.get("opacity", 1.0))
    sr, sg, sb = _split_rgb(p.get("stroke_color", "#26fdf1"))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha=str(opacity), box=(x, y, w, h),
        radial=(x + w / 2, y + h / 2, min(w, h) / 2),
    )
    path = f"    rounded_rect(cr, {x}, {y}, {w}, {h}, {cr})\n" if cr > 0 else f"    cairo_rectangle(cr, {x}, {y}, {w}, {h})\n"
    body = path
    if do_fill and do_stroke:
        body += f"{fill_setup}\n    cairo_fill_preserve(cr)\n{fill_destroy}\n"
        body += f"    cairo_set_line_width(cr, {lw})\n    cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})\n    cairo_stroke(cr)\n"
    elif do_fill:
        body += f"{fill_setup}\n    cairo_fill(cr)\n{fill_destroy}\n"
    elif do_stroke:
        body += f"    cairo_set_line_width(cr, {lw})\n    cairo_set_source_rgba(cr, {sr}, {sg}, {sb}, {opacity})\n    cairo_stroke(cr)\n"
    return f"local function {fn}(cr, W, H)\n{body}end"

@visual_generator("visual.hline")
def _gen_hline(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 20)), int(p.get("y", 40))
    length = int(p.get("length", 200))
    lw = float(p.get("line_width", 1.5))
    opacity = float(p.get("opacity", 0.85))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha=str(opacity), box=(x, y - lw, length, lw * 2),
        radial=(x + length / 2, y, length / 2),
    )
    return (
        f"local function {fn}(cr, W, H)\n"
        f"    cairo_new_path(cr)\n    cairo_move_to(cr, {x}, {y})\n    cairo_line_to(cr, {x} + {length}, {y})\n"
        f"{fill_setup}\n    cairo_set_line_width(cr, {lw})\n    cairo_stroke(cr)\n{fill_destroy}\nend"
    )

@visual_generator("visual.vline")
def _gen_vline(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    x, y = int(p.get("x", 40)), int(p.get("y", 20))
    length = int(p.get("length", 120))
    lw = float(p.get("line_width", 1.5))
    opacity = float(p.get("opacity", 0.85))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha=str(opacity), box=(x - lw, y, lw * 2, length),
        radial=(x, y + length / 2, length / 2),
    )
    return (
        f"local function {fn}(cr, W, H)\n"
        f"    cairo_new_path(cr)\n    cairo_move_to(cr, {x}, {y})\n    cairo_line_to(cr, {x}, {y} + {length})\n"
        f"{fill_setup}\n    cairo_set_line_width(cr, {lw})\n    cairo_stroke(cr)\n{fill_destroy}\nend"
    )

@visual_generator("visual.crosshair")
def _gen_crosshair(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    size, gap = int(p.get("size", 24)), int(p.get("gap", 4))
    lw = float(p.get("line_width", 1.5))
    opacity = float(p.get("opacity", 0.9))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha=str(opacity),
        box=(cx - size, cy - size, size * 2, size * 2),
        radial=(cx, cy, size),
    )
    return (
        f"local function {fn}(cr, W, H)\n"
        f"    cairo_set_line_width(cr, {lw})\n"
        f"{fill_setup}\n"
        f"    cairo_new_path(cr)\n"
        f"    cairo_move_to(cr, {cx} - {size}, {cy}); cairo_line_to(cr, {cx} - {gap}, {cy})\n"
        f"    cairo_move_to(cr, {cx} + {gap}, {cy}); cairo_line_to(cr, {cx} + {size}, {cy})\n"
        f"    cairo_move_to(cr, {cx}, {cy} - {size}); cairo_line_to(cr, {cx}, {cy} - {gap})\n"
        f"    cairo_move_to(cr, {cx}, {cy} + {gap}); cairo_line_to(cr, {cx}, {cy} + {size})\n"
        f"    cairo_stroke(cr)\n{fill_destroy}\nend"
    )

@visual_generator("visual.ring_track")
def _gen_ring_track(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    cx, cy = int(p.get("cx", 100)), int(p.get("cy", 100))
    radius, thickness = int(p.get("radius", 70)), int(p.get("thickness", 8))
    start_deg, sweep_deg = int(p.get("start_angle_deg", -90)), int(p.get("sweep_deg", 360))
    cap = "CAIRO_LINE_CAP_ROUND" if p.get("cap_style", "round") == "round" else "CAIRO_LINE_CAP_BUTT"
    opacity = float(p.get("opacity", 0.7))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha=str(opacity),
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
    )
    return (
        f"local function {fn}(cr, W, H)\n"
        f"    local a0 = ({start_deg}) * math.pi / 180\n"
        f"    local a1 = a0 + ({sweep_deg}) * math.pi / 180\n"
        f"    cairo_set_line_cap(cr, {cap})\n    cairo_new_path(cr)\n"
        f"{fill_setup}\n    cairo_set_line_width(cr, {thickness})\n"
        f"    cairo_arc(cr, {cx}, {cy}, {radius}, a0, a1)\n    cairo_stroke(cr)\n"
        f"{fill_destroy}\n    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)\nend"
    )

@visual_generator("visual.led_dot")
def _gen_led_dot(node, ctx):
    fn = f"draw_node_{lua_safe_id(node.id)}"
    p = node.props
    value_expr = ctx.resolve(node, "value")
    th = float(p.get("threshold", 0.5))
    cx, cy = int(p.get("cx", 40)), int(p.get("cy", 40))
    radius = int(p.get("radius", 6))
    on_r, on_g, on_b = _split_rgb(p.get("color_on", "#4fd1c5"))
    off_r, off_g, off_b = _split_rgb(p.get("color_off", "#33313a"))
    glow = bool(p.get("glow", True))
    opacity = float(p.get("opacity", 1.0))
    fill_setup, fill_destroy = _lua_fill_source(
        p, alpha=str(opacity),
        box=(cx - radius, cy - radius, radius * 2, radius * 2),
        radial=(cx, cy, radius),
    )
    glow_block = ""
    if glow:
        glow_block = (
            f"    if on then\n"
            f"        cairo_set_source_rgba(cr, {on_r}, {on_g}, {on_b}, {opacity} * 0.25)\n"
            f"        cairo_arc(cr, {cx}, {cy}, {radius} * 2.2, 0, 2 * math.pi)\n"
            f"        cairo_fill(cr)\n    end\n"
        )
    return (
        f"local function {fn}(cr, W, H)\n"
        f"    local raw = {value_expr}\n"
        f"    if type(raw) ~= 'number' then raw = tonumber(raw) or 0 end\n"
        f"    local on = raw >= ({th})\n"
        f"{glow_block}"
        f"    cairo_new_path(cr)\n    cairo_arc(cr, {cx}, {cy}, {radius}, 0, 2 * math.pi)\n"
        f"    if on then\n"
        f"{fill_setup}\n"
        f"        cairo_fill(cr)\n"
        f"{fill_destroy}\n"
        f"    else\n"
        f"        cairo_set_source_rgba(cr, {off_r}, {off_g}, {off_b}, {opacity})\n"
        f"        cairo_fill(cr)\n"
        f"    end\nend"
    )

# ---------------------------------------------------------------------------
def _split_rgb(hex_str: str) -> tuple[str, str, str]:
    lit = lua_rgb_literal(hex_str)
    return tuple(lit.split(", "))  # type: ignore[return-value]

def _lua_fill_source(p, *, alpha="1", box=None, radial=None, indent="    "):
    """Emit Lua for solid or 2-stop gradient fill from node props.

    Reads fill_mode / color / color_end / gradient_angle / gradient_spread.
    Defaults to solid when props are absent (older projects).
    Returns (setup_lines, destroy_line) — destroy_line may be "".
    *alpha* may be a Lua expression string (e.g. "alpha_mul" or "0.25").
    *box* = (x, y, w, h) for linear; *radial* = (cx, cy, radius).
    """
    mode = str(p.get("fill_mode", "solid") or "solid").lower()
    color = str(p.get("color", "#4fd1c5"))
    color_end = str(p.get("color_end", "#1a3a4a"))
    angle = float(p.get("gradient_angle", 0) or 0)
    spread = float(p.get("gradient_spread", 1.0) or 1.0)
    r0, g0, b0 = _split_rgb(color)
    ind = indent

    if mode not in ("linear", "radial") or not color_end:
        setup = f"{ind}cairo_set_source_rgba(cr, {r0}, {g0}, {b0}, {alpha})"
        return setup, ""

    r1, g1, b1 = _split_rgb(color_end)
    if mode == "radial" and radial is not None:
        cx, cy, rad = radial
        setup = (
            f"{ind}local _grad = cairo_pattern_create_radial("
            f"{cx}, {cy}, 0, {cx}, {cy}, ({rad}) * ({spread}))\n"
            f"{ind}cairo_pattern_add_color_stop_rgba(_grad, 0, {r0}, {g0}, {b0}, {alpha})\n"
            f"{ind}cairo_pattern_add_color_stop_rgba(_grad, 1, {r1}, {g1}, {b1}, {alpha})\n"
            f"{ind}cairo_set_source(cr, _grad)"
        )
        destroy = f"{ind}if _grad then cairo_pattern_destroy(_grad) end"
        return setup, destroy

    # linear — use box centre axis, or radial centre as fallback box
    if box is not None:
        x, y, w, h = box
    elif radial is not None:
        cx, cy, rad = radial
        x, y, w, h = cx - rad, cy - rad, rad * 2, rad * 2
    else:
        setup = f"{ind}cairo_set_source_rgba(cr, {r0}, {g0}, {b0}, {alpha})"
        return setup, ""

    setup = (
        f"{ind}local _gx = ({x}) + ({w}) / 2\n"
        f"{ind}local _gy = ({y}) + ({h}) / 2\n"
        f"{ind}local _glen = math.max(({w}), ({h})) / 2\n"
        f"{ind}local _ga = math.rad({angle})\n"
        f"{ind}local _grad = cairo_pattern_create_linear(\n"
        f"{ind}  _gx - math.cos(_ga) * _glen, _gy - math.sin(_ga) * _glen,\n"
        f"{ind}  _gx + math.cos(_ga) * _glen, _gy + math.sin(_ga) * _glen)\n"
        f"{ind}cairo_pattern_add_color_stop_rgba(_grad, 0, {r0}, {g0}, {b0}, {alpha})\n"
        f"{ind}cairo_pattern_add_color_stop_rgba(_grad, 1, {r1}, {g1}, {b1}, {alpha})\n"
        f"{ind}cairo_set_source(cr, _grad)"
    )
    destroy = f"{ind}if _grad then cairo_pattern_destroy(_grad) end"
    return setup, destroy




def _basename(path: str) -> str:
    return (path or "").replace("\\", "/").rsplit("/", 1)[-1]


def _image_path_expr(path: str) -> str:
    if not path:
        return "nil"
    return f"IMAGES_DIR .. '/{_basename(path)}'"


# v1.0.6: register extension generators (no-op if modules missing)
try:
    from conkystudio.codegen.logic_generators_extra import register as _reg_logic_extra
    _reg_logic_extra(logic_generator)
except Exception as _e:
    print(f"[conky-studio] logic_generators_extra: {_e}")
try:
    from conkystudio.codegen.visual_generators_extra import register as _reg_visual_extra
    _reg_visual_extra(visual_generator)
except Exception as _e:
    print(f"[conky-studio] visual_generators_extra: {_e}")


def assert_full_coverage():
    """Every registered visual node type must have a generator -- called by
    the test suite and by builder.py before compiling, so a half-wired
    node type fails loudly at build time instead of silently drawing
    nothing."""
    visual_types = {s.type for s in registry.by_category("visual")}
    missing = visual_types - set(_VISUAL_GENERATORS)
    if missing:
        raise RuntimeError(f"No Lua generator registered for visual node type(s): {sorted(missing)}")


# ---------------------------------------------------------------------------
def has_clickable_nodes(project: Project) -> bool:
    return any(n.visible and n.on_click_command.strip() for n in project.nodes
               if registry.get(n.type).category == "visual")


def build_mouse_handler(project: Project) -> str:
    """conky_mouse_handler(event) -- checks left-click position against every
    clickable node's explicit region and shells out to its command. Same
    button_down / event.x / event.y shape as music-controls.lua; region
    checks are explicit x/y/w/h rather than inferred from each node's own
    drawing geometry, matching how that real theme actually authors them."""
    clickable = [n for n in project.nodes
                 if n.visible and n.on_click_command.strip() and registry.get(n.type).category == "visual"]
    if not clickable:
        return ""

    checks = []
    for n in clickable:
        cmd = n.on_click_command.strip().replace("'", "\\'")
        checks.append(
            f"    if event.x >= {n.click_x} and event.x <= {n.click_x + n.click_w} "
            f"and event.y >= {n.click_y} and event.y <= {n.click_y + n.click_h} then\n"
            f"        os.execute('{cmd} &')\n"
            f"    end"
        )

    return f'''
local function mouse_handler_impl(event)
    if event.type ~= 'button_down' or event.button ~= 'left' then return end
{chr(10).join(checks)}
end

-- NOTE: unlike lua_draw_hook_post/_pre (which call conky_<name>), Conky's
-- lua_mouse_hook calls the configured name LITERALLY with no 'conky_'
-- prefix -- confirmed empirically (xdotool-simulated clicks against a
-- real Conky window; a conky_mouse_handler-named function is simply
-- never invoked). Don't rename this without re-checking that.
function mouse_handler(event)
    local ok, err = pcall(mouse_handler_impl, event)
    if not ok then
        print('[conky-studio] mouse handler error: ' .. tostring(err))
    end
end
'''


def build_render_lua(project: Project, script_filenames: dict, header_comment: str = "") -> str:
    assert_full_coverage()
    ctx = GenContext(project=project)
    ctx.used_source_ids = compute_used_sources(project)

    visual_nodes = sorted(
        (n for n in project.nodes if registry.get(n.type).category == "visual" and n.visible),
        key=lambda n: n.z,
    )

    draw_fns = []
    draw_order_entries = []
    hist_init_lines = []
    for n in visual_nodes:
        spec = registry.get(n.type)
        gen = _VISUAL_GENERATORS[n.type]
        draw_fns.append(gen(n, ctx))
        draw_order_entries.append(f"draw_node_{lua_safe_id(n.id)}")
        for value_prop, suffix in _HISTORY_SERIES.get(n.type, ()):
            edge = project.edge_for_prop(n.id, value_prop)
            if edge is None:
                continue
            length = int(n.props.get("history_length", 48))
            key = _history_hist_key(n.id, suffix)
            hist_init_lines.append(
                f"HIST[{lua_string_literal(key)}] = HIST[{lua_string_literal(key)}] or "
                f"(function() local t = {{}} for i=1,{length} do t[i] = 0 end return t end)()"
            )

    hist_push_lines = []
    for n in visual_nodes:
        for value_prop, suffix in _HISTORY_SERIES.get(n.type, ()):
            edge = project.edge_for_prop(n.id, value_prop)
            if edge is None:
                continue
            key = _history_hist_key(n.id, suffix)
            hist_push_lines.append(
                f"    table.remove(HIST[{lua_string_literal(key)}], 1); "
                f"table.insert(HIST[{lua_string_literal(key)}], SRC[{lua_string_literal(edge.src_node)}] or 0)"
            )

    refresh_fn = build_refresh_sources(ctx, script_filenames)
    stats_interval_frames = "math.max(1, math.floor(CANVAS_FPS / STATS_HZ))"
    mouse_handler_fn = build_mouse_handler(project)

    body = f'''
{header_comment}
local THEME_DIR = (function()
    local src = debug.getinfo(1, 'S').source:gsub('^@', '')
    return (src:match('(.*/)') or './'):gsub('/$', '')
end)()
local SCRIPTS_DIR = THEME_DIR .. '/scripts'
local IMAGES_DIR = THEME_DIR .. '/images'
local CACHE_DIR = THEME_DIR .. '/.runtime-cache'
os.execute("mkdir -p '" .. CACHE_DIR .. "'")

local CANVAS_FPS = {project.canvas.fps}
local STATS_HZ = {project.canvas.stats_hz}
local STATS_EVERY = {stats_interval_frames}

local frame = 0

{refresh_fn}

{chr(10).join(draw_fns)}

-- Every visual node's draw function is collected into ONE table rather
-- than called by name directly from main_draw_impl: a nested function
-- referencing more than 60 distinct outer locals hits a hard Lua 5.1
-- limit (max 60 upvalues per function), which a large real-world HUD
-- (a legacy-theme import, easily) can and does exceed. Looping over one
-- table is a single upvalue regardless of how many nodes exist.
local DRAW_ORDER = {{
{",\n".join(f"    {name}" for name in draw_order_entries) if draw_order_entries else ""}
}}

local function main_draw_impl()
    local cs, W, H, owns_surface = get_draw_surface()
    if cs == nil then return end
    local cr = cairo_create(cs)

    cairo_save(cr)
    cairo_set_operator(cr, CAIRO_OPERATOR_CLEAR)
    cairo_paint(cr)
    cairo_restore(cr)

    local updates = tonumber(safe_parse('${{updates}}', '0')) or 0
    if updates >= 5 then
        frame = frame + 1
        if frame % STATS_EVERY == 0 then
            refresh_sources()
{chr(10).join(hist_push_lines)}
        end

        for _i = 1, #DRAW_ORDER do
            DRAW_ORDER[_i](cr, W, H)
        end
    end

    cairo_destroy(cr)
    if owns_surface then
        cairo_surface_destroy(cs)
    end
end

{chr(10).join(hist_init_lines)}

function conky_main_draw()
    local ok, err = pcall(main_draw_impl)
    if not ok then
        print('[conky-studio] draw error: ' .. tostring(err))
    end
end
{mouse_handler_fn}
'''
    return FRAMEWORK_LUA + body

