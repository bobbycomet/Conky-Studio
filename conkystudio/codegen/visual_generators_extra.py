"""
Visual generators for visuals_extra.py.

Call register(visual_generator) after lua_gen defines the decorator:

    from conkystudio.codegen.visual_generators_extra import register as _reg_visual_extra
    _reg_visual_extra(visual_generator)
"""
from __future__ import annotations


def register(visual_generator):
    from conkystudio.codegen.lua_gen import lua_safe_id
    from conkystudio.codegen.color import lua_rgb_literal

    def _split_rgb(hex_str: str):
        lit = lua_rgb_literal(hex_str)
        return tuple(lit.split(", "))

    @visual_generator("visual.top_table")
    def _gen_top_table(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        x = int(p.get("x", 20))
        y = int(p.get("y", 20))
        rows = max(1, min(15, int(p.get("rows", 5))))
        rh = int(p.get("row_height", 18))
        w_rank = int(p.get("col_rank_w", 28))
        w_name = int(p.get("col_name_w", 140))
        w_cpu = int(p.get("col_cpu_w", 48))
        w_mem = int(p.get("col_mem_w", 48))
        show_hdr = bool(p.get("show_header", True))
        font = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
        fsize = int(p.get("font_size", 11))
        tr, tg, tb = _split_rgb(p.get("color", "#e8eaed"))
        hr, hg, hb = _split_rgb(p.get("header_color", "#4fd1c5"))
        ar, ag, ab = _split_rgb(p.get("alt_row_color", "#1a222c"))
        alt = bool(p.get("show_alt_rows", True))
        opacity = float(p.get("opacity", 1.0))

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local x0, y0 = {x}, {y}",
            f"    local rh = {rh}",
            f"    local opacity = {opacity}",
            f"    cairo_select_font_face(cr, '{font}', CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)",
            f"    cairo_set_font_size(cr, {fsize})",
        ]
        y_off = 0
        if show_hdr:
            lines += [
                f"    cairo_set_source_rgba(cr, {hr}, {hg}, {hb}, opacity)",
                f"    cairo_move_to(cr, x0, y0 + {fsize})",
                f"    cairo_show_text(cr, '#')",
                f"    cairo_move_to(cr, x0 + {w_rank}, y0 + {fsize})",
                f"    cairo_show_text(cr, 'Name')",
                f"    cairo_move_to(cr, x0 + {w_rank + w_name}, y0 + {fsize})",
                f"    cairo_show_text(cr, 'CPU')",
                f"    cairo_move_to(cr, x0 + {w_rank + w_name + w_cpu}, y0 + {fsize})",
                f"    cairo_show_text(cr, 'MEM')",
            ]
            y_off = rh

        lines.append(f"    for rank = 1, {rows} do")
        if alt:
            lines += [
                f"        if rank % 2 == 0 then",
                f"            cairo_set_source_rgba(cr, {ar}, {ag}, {ab}, opacity * 0.35)",
                f"            cairo_rectangle(cr, x0 - 2, y0 + {y_off} + (rank - 1) * rh - 2, "
                f"{w_rank + w_name + w_cpu + w_mem + 8}, rh)",
                f"            cairo_fill(cr)",
                f"        end",
            ]
        lines += [
            f"        local name = safe_parse('${{top name ' .. rank .. '}}', '')",
            f"        local cpu = safe_parse('${{top cpu ' .. rank .. '}}', '0')",
            f"        local mem = safe_parse('${{top mem ' .. rank .. '}}', '0')",
            f"        local yy = y0 + {y_off} + (rank - 1) * rh + {fsize}",
            f"        cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, opacity)",
            f"        cairo_move_to(cr, x0, yy)",
            f"        cairo_show_text(cr, tostring(rank))",
            f"        cairo_move_to(cr, x0 + {w_rank}, yy)",
            f"        cairo_show_text(cr, name)",
            f"        cairo_move_to(cr, x0 + {w_rank + w_name}, yy)",
            f"        cairo_show_text(cr, cpu)",
            f"        cairo_move_to(cr, x0 + {w_rank + w_name + w_cpu}, yy)",
            f"        cairo_show_text(cr, mem)",
            f"    end",
            f"end",
        ]
        return "\n".join(lines)

    @visual_generator("visual.core_strip")
    def _gen_core_strip(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        x = int(p.get("x", 20))
        y = int(p.get("y", 20))
        ncores = max(1, min(64, int(p.get("core_count", 8))))
        bw = int(p.get("bar_width", 10))
        bh = int(p.get("bar_height", 48))
        gap = int(p.get("gap", 3))
        heat = bool(p.get("heat_map", False))
        opacity = float(p.get("opacity", 1.0))
        show_lab = bool(p.get("show_labels", False))
        fsize = int(p.get("font_size", 8))
        tr, tg, tb = _split_rgb(p.get("track_color", "#33313a"))
        fr, fg, fb = _split_rgb(p.get("color", "#4fd1c5"))

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local x0, y0, bw, bh, gap = {x}, {y}, {bw}, {bh}, {gap}",
            f"    local opacity = {opacity}",
            f"    for i = 1, {ncores} do",
            f"        local usage = safe_number('${{cpu cpu' .. i .. '}}', 0)",
            f"        if usage < 0 then usage = 0 end",
            f"        if usage > 100 then usage = 100 end",
            f"        local bx = x0 + (i - 1) * (bw + gap)",
            f"        cairo_set_source_rgba(cr, {tr}, {tg}, {tb}, opacity * 0.7)",
            f"        cairo_rectangle(cr, bx, y0, bw, bh)",
            f"        cairo_fill(cr)",
            f"        local fill_h = bh * usage / 100",
        ]
        if heat:
            lines += [
                f"        local hr, hg, hb = studio_heat_rgb(usage / 100)",
                f"        cairo_set_source_rgba(cr, hr, hg, hb, opacity)",
            ]
        else:
            lines += [
                f"        cairo_set_source_rgba(cr, {fr}, {fg}, {fb}, opacity)",
            ]
        lines += [
            f"        cairo_rectangle(cr, bx, y0 + bh - fill_h, bw, fill_h)",
            f"        cairo_fill(cr)",
        ]
        if show_lab:
            lines += [
                f"        cairo_select_font_face(cr, 'Sans', CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)",
                f"        cairo_set_font_size(cr, {fsize})",
                f"        cairo_set_source_rgba(cr, {fr}, {fg}, {fb}, opacity * 0.8)",
                f"        cairo_move_to(cr, bx, y0 + bh + {fsize + 2})",
                f"        cairo_show_text(cr, tostring(i))",
            ]
        lines += [
            f"    end",
            f"end",
        ]
        return "\n".join(lines)

    @visual_generator("visual.orbit_field")
    def _gen_orbit_field(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        cx = int(p.get("cx", 120))
        cy = int(p.get("cy", 120))
        radius = int(p.get("radius", 70))
        dots = max(3, min(48, int(p.get("dot_count", 12))))
        dr = float(p.get("dot_radius", 2.5))
        rings = max(1, min(4, int(p.get("rings", 1))))
        speed = float(p.get("speed_dps", 25.0))
        opacity = float(p.get("opacity", 0.85))
        tscale = float(p.get("trigger_scale", 0.5))
        trigger = ctx.resolve(node, "trigger")
        r, g, b = _split_rgb(p.get("color", "#26fdf1"))

        return f"""local function {fn}(cr, W, H)
    local cx, cy = {cx}, {cy}
    local base_r = {radius}
    local dots, rings = {dots}, {rings}
    local dr = {dr}
    local opacity = {opacity}
    local trig = tonumber({trigger}) or 0
    local speed = ({speed}) * (1 + (trig / 100) * ({tscale}))
    local t = wall_clock()
    local phase = t * speed * math.pi / 180
    for ring = 1, rings do
        local rad = base_r * (0.55 + 0.45 * ring / rings)
        rad = rad * (1 + math.min(trig, 100) / 800)
        for i = 1, dots do
            local a = phase * (ring % 2 == 0 and -1 or 1) + (i - 1) * (2 * math.pi / dots)
            local px = cx + math.cos(a) * rad
            local py = cy + math.sin(a) * rad
            local fade = 0.45 + 0.55 * ((i % 3) / 2)
            cairo_set_source_rgba(cr, {r}, {g}, {b}, opacity * fade)
            cairo_arc(cr, px, py, dr, 0, 2 * math.pi)
            cairo_fill(cr)
        end
    end
end"""
