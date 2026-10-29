"""
Generators for nodes/visuals_more.py.

Call register(visual_generator) the same way visual_generators_extra.py
does -- see register_extensions.py for the wiring (and the bug fix that
was needed there).
"""
from __future__ import annotations


def register(visual_generator):
    from conkystudio.codegen.lua_gen import lua_safe_id, lua_string_literal
    from conkystudio.codegen.color import lua_rgb_literal
    from conkystudio.codegen.gradient_integration import fill_source_lua

    def _split_rgb(hex_str: str):
        return tuple(lua_rgb_literal(hex_str).split(", "))

    # -----------------------------------------------------------------
    # Needle Gauge
    # -----------------------------------------------------------------
    @visual_generator("visual.needle_gauge")
    def _gen_needle_gauge(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        cx = int(p.get("cx", 120))
        cy = int(p.get("cy", 120))
        radius = float(p.get("radius", 80))
        start_a = float(p.get("start_angle", 135.0))
        end_a = float(p.get("end_angle", 45.0))
        sweep = (end_a - start_a) % 360.0
        if sweep <= 0:
            sweep = 360.0
        track_w = float(p.get("track_width", 10.0))
        min_v = float(p.get("min_value", 0.0))
        max_v = float(p.get("max_value", 100.0))
        tick_count = max(2, int(p.get("tick_count", 8)))
        minor = bool(p.get("show_minor_ticks", True))
        use_zones = bool(p.get("use_zones", True))
        warn_pct = float(p.get("zone_warn_pct", 60.0))
        danger_pct = float(p.get("zone_danger_pct", 85.0))
        show_val = bool(p.get("show_value_text", True))
        font = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
        fsize = int(p.get("font_size", 14))
        suffix = str(p.get("value_suffix", "") or "")
        opacity = float(p.get("opacity", 1.0))

        tr, tg, tb = _split_rgb(p.get("track_color", "#33313a"))
        ok_r, ok_g, ok_b = _split_rgb(p.get("zone_ok_color", "#4fd1c5"))
        wr, wg, wb = _split_rgb(p.get("zone_warn_color", "#e8b84f"))
        dr, dg, db = _split_rgb(p.get("zone_danger_color", "#ff6b6b"))
        nr, ng, nb = _split_rgb(p.get("needle_color", "#e8eaed"))
        hr, hg, hb = _split_rgb(p.get("hub_color", "#1a222c"))
        tkr, tkg, tkb = _split_rgb(p.get("tick_color", "#9aa2ad"))

        value_expr = ctx.resolve(node, "value")

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local cx, cy, radius = {cx}, {cy}, {radius}",
            f"    local track_w = {track_w}",
            f"    local opacity = {opacity}",
            f"    local min_v, max_v = {min_v}, {max_v}",
            f"    local start_a, sweep = {start_a}, {sweep}",
            f"    local span = (max_v - min_v)",
            f"    if span == 0 then span = 1 end",
            f"    local val = tonumber({value_expr}) or min_v",
            f"    local pct = clamp((val - min_v) / span, 0, 1)",
            f"",
            f"    cairo_set_line_cap(cr, CAIRO_LINE_CAP_BUTT)",
            f"    cairo_set_line_width(cr, track_w)",
            f"    cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, opacity)",
            f"    cairo_new_sub_path(cr)",
            f"    cairo_arc(cr, cx, cy, radius, math.rad(start_a), math.rad(start_a + sweep))",
            f"    cairo_stroke(cr)",
        ]

        if use_zones:
            lines += [
                f"    local ok_end = start_a + sweep * ({warn_pct} / 100)",
                f"    local warn_end = start_a + sweep * ({danger_pct} / 100)",
                f"    local danger_end = start_a + sweep",
                f"    cairo_set_source_rgba(cr, {ok_r}, {ok_g}, {ok_b}, opacity)",
                f"    cairo_new_sub_path(cr); cairo_arc(cr, cx, cy, radius, math.rad(start_a), math.rad(ok_end)); cairo_stroke(cr)",
                f"    cairo_set_source_rgba(cr, {wr}, {wg}, {wb}, opacity)",
                f"    cairo_new_sub_path(cr); cairo_arc(cr, cx, cy, radius, math.rad(ok_end), math.rad(warn_end)); cairo_stroke(cr)",
                f"    cairo_set_source_rgba(cr, {dr}, {dg}, {db}, opacity)",
                f"    cairo_new_sub_path(cr); cairo_arc(cr, cx, cy, radius, math.rad(warn_end), math.rad(danger_end)); cairo_stroke(cr)",
            ]

        lines += [
            f"    cairo_set_line_width(cr, 2)",
            f"    cairo_set_source_rgba(cr, {tkr}, {tkg}, {tkb}, opacity)",
            f"    for i = 0, {tick_count} do",
            f"        local ta = math.rad(start_a + sweep * (i / {tick_count}))",
            f"        local x1 = cx + math.cos(ta) * (radius - track_w / 2 - 2)",
            f"        local y1 = cy + math.sin(ta) * (radius - track_w / 2 - 2)",
            f"        local x2 = cx + math.cos(ta) * (radius - track_w / 2 - 12)",
            f"        local y2 = cy + math.sin(ta) * (radius - track_w / 2 - 12)",
            f"        cairo_move_to(cr, x1, y1); cairo_line_to(cr, x2, y2); cairo_stroke(cr)",
            f"    end",
        ]
        if minor:
            lines += [
                f"    cairo_set_line_width(cr, 1)",
                f"    cairo_set_source_rgba(cr, {tkr}, {tkg}, {tkb}, opacity * 0.6)",
                f"    for i = 0, {tick_count * 4} do",
                f"        local ta = math.rad(start_a + sweep * (i / {tick_count * 4}))",
                f"        local x1 = cx + math.cos(ta) * (radius - track_w / 2 - 2)",
                f"        local y1 = cy + math.sin(ta) * (radius - track_w / 2 - 2)",
                f"        local x2 = cx + math.cos(ta) * (radius - track_w / 2 - 7)",
                f"        local y2 = cy + math.sin(ta) * (radius - track_w / 2 - 7)",
                f"        cairo_move_to(cr, x1, y1); cairo_line_to(cr, x2, y2); cairo_stroke(cr)",
                f"    end",
            ]

        lines += [
            f"    local needle_a = math.rad(start_a + sweep * pct)",
            f"    local nlen = radius - track_w - 6",
            f"    cairo_set_line_width(cr, 3)",
            f"    cairo_set_source_rgba(cr, {nr}, {ng}, {nb}, opacity)",
            f"    cairo_move_to(cr, cx, cy)",
            f"    cairo_line_to(cr, cx + math.cos(needle_a) * nlen, cy + math.sin(needle_a) * nlen)",
            f"    cairo_stroke(cr)",
            f"    cairo_set_source_rgba(cr, {hr}, {hg}, {hb}, opacity)",
            f"    cairo_arc(cr, cx, cy, math.max(4, track_w * 0.6), 0, 2 * math.pi)",
            f"    cairo_fill(cr)",
        ]
        if show_val:
            lines += [
                f"    studio_draw_text(cr, string.format('%.0f', val) .. {lua_string_literal(suffix)}, "
                f"cx, cy + radius * 0.55, {{family = '{font}', size = {fsize}, "
                f"r = {nr}, g = {ng}, b = {nb}, a = opacity, align = 'center', halo = true}})",
            ]
        lines.append("end")
        return "\n".join(lines)

  
    # -----------------------------------------------------------------
    # Equalizer Bars
    # -----------------------------------------------------------------
    @visual_generator("visual.equalizer_bars")
    def _gen_equalizer_bars(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        x = int(p.get("x", 20))
        y = int(p.get("y", 140))
        bar_count = max(2, int(p.get("bar_count", 16)))
        bar_w = int(p.get("bar_width", 6))
        gap = int(p.get("gap", 3))
        max_h = int(p.get("max_height", 60))
        min_h = int(p.get("min_height", 4))
        rounded = bool(p.get("rounded_caps", True))
        mirror = bool(p.get("mirror", False))
        speed = float(p.get("speed", 1.0))
        idle_energy = float(p.get("idle_energy", 25.0))
        opacity = float(p.get("opacity", 0.9))
        heat = bool(p.get("heat_map", False))
        fill_mode = str(p.get("fill_mode", "solid"))
        color_r, color_g, color_b = _split_rgb(p.get("color", "#4fd1c5"))

        total_w = bar_count * bar_w + (bar_count - 1) * gap
        trigger_expr = ctx.resolve(node, "trigger")

        setup, destroy = fill_source_lua(
            p, color_key="color", alpha=opacity,
            box=(x, y - max_h, total_w, max_h * (2 if mirror else 1)),
        )
        use_grad = fill_mode != "solid" and not heat

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local x0, y0 = {x}, {y}",
            f"    local bar_w, gap = {bar_w}, {gap}",
            f"    local max_h, min_h = {max_h}, {min_h}",
            f"    local opacity = {opacity}",
            f"    local t = wall_clock()",
            # NOTE: an unbound `trigger` still resolves to its literal
            # default (0.0), not nil -- `tonumber(...) or idle_energy`
            # would never fall through, since 0 is truthy in Lua. A
            # floor achieves the intended "idle ambient minimum" instead:
            # bound-and-low reads the same as unbound, which is the
            # honest behaviour given there's no way to detect "unbound"
            # at runtime here.
            f"    local energy = math.max(tonumber({trigger_expr}) or 0, {idle_energy})",
        ]
        if use_grad:
            lines.append("    " + setup.replace("\n", "\n    "))
        elif not heat:
            lines.append(f"    cairo_set_source_rgba(cr, {color_r}, {color_g}, {color_b}, opacity)")
        lines += [
            f"    for i = 1, {bar_count} do",
            f"        local seed = i * 12.9898",
            f"        local freq = 1.3 + (i % 5) * 0.37",
            f"        local phase = i * 0.9 + math.sin(seed)",
            f"        local osc = math.sin(t * {speed} * freq + phase) * 0.5 + 0.5",
            f"        local h = min_h + (max_h - min_h) * clamp((energy / 100) * (0.35 + 0.65 * osc), 0, 1)",
            f"        local bx = x0 + (i - 1) * (bar_w + gap)",
        ]
        if heat:
            lines.append("        local hr, hg, hb = studio_heat_rgb(h / math.max(max_h, 1))")
            lines.append("        cairo_set_source_rgba(cr, hr, hg, hb, opacity)")
        elif use_grad:
            lines.append("        cairo_set_source(cr, _grad)")
        if rounded:
            lines += [
                f"        rounded_rect(cr, bx, y0 - h, bar_w, h, bar_w / 2)",
                f"        cairo_fill(cr)",
            ]
        else:
            lines += [
                f"        cairo_rectangle(cr, bx, y0 - h, bar_w, h)",
                f"        cairo_fill(cr)",
            ]
        if mirror:
            if rounded:
                lines += [
                    f"        rounded_rect(cr, bx, y0, bar_w, h, bar_w / 2)",
                    f"        cairo_fill(cr)",
                ]
            else:
                lines += [
                    f"        cairo_rectangle(cr, bx, y0, bar_w, h)",
                    f"        cairo_fill(cr)",
                ]
        lines.append("    end")
        if use_grad and destroy:
            lines.append(f"    {destroy}")
        lines.append("end")
        return "\n".join(lines)
