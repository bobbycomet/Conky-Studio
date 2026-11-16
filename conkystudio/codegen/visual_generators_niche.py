"""
Generators for nodes/visuals_niche.py.

Wire it up the same way visual_generators_extra.py / visual_generators_more.py
are wired -- e.g. from register_extensions.py or the tail of lua_gen.py:

    from conkystudio.codegen.visual_generators_niche import register as _reg_visual_niche
    _reg_visual_niche(visual_generator)

Everything here only touches the framework helpers already spliced into
FRAMEWORK_LUA (wall_clock, clamp, lerp, rounded_rect, studio_draw_text,
studio_heat_rgb, STATE) -- no new framework additions required.
"""
from __future__ import annotations


def register(visual_generator):
    from conkystudio.codegen.lua_gen import lua_safe_id, lua_string_literal
    from conkystudio.codegen.color import lua_rgb_literal

    def _split_rgb(hex_str: str):
        return tuple(lua_rgb_literal(hex_str).split(", "))

    # -----------------------------------------------------------------
    # Spinning Fan
    # -----------------------------------------------------------------
    @visual_generator("visual.spinning_fan")
    def _gen_spinning_fan(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        cx = int(p.get("cx", 120))
        cy = int(p.get("cy", 120))
        blades = max(2, min(9, int(p.get("blade_count", 5))))
        blen = float(p.get("blade_length", 60.0))
        bwid = float(p.get("blade_width", 22.0))
        hub_r = float(p.get("hub_radius", 10.0))
        base_rps = float(p.get("base_rps", 0.3))
        max_rps = float(p.get("max_rps", 6.0))
        direction = 1 if bool(p.get("clockwise", True)) else -1
        heat = bool(p.get("heat_map", False))
        blur = bool(p.get("motion_blur", True))
        opacity = float(p.get("opacity", 1.0))
        br, bg, bb = _split_rgb(p.get("blade_color", "#9aa2ad"))
        hr, hg, hb = _split_rgb(p.get("hub_color", "#1a222c"))
        speed_expr = ctx.resolve(node, "speed_pct")

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local cx, cy = {cx}, {cy}",
            f"    local blen, bwid, hub_r = {blen}, {bwid}, {hub_r}",
            f"    local opacity = {opacity}",
            f"    local pct = clamp((tonumber({speed_expr}) or 0) / 100, 0, 1)",
            f"    local rps = {base_rps} + pct * ({max_rps} - {base_rps})",
            f"    local base_angle = wall_clock() * rps * 360 * ({direction})",
            f"",
            f"    local fr, fg, fb",
        ]
        if heat:
            lines.append("    fr, fg, fb = studio_heat_rgb(pct)")
        else:
            lines.append(f"    fr, fg, fb = {br}, {bg}, {bb}")
        lines += [
            f"",
            f"    local function draw_blade(angle, alpha)",
            f"        cairo_save(cr)",
            f"        cairo_translate(cr, cx, cy)",
            f"        cairo_rotate(cr, math.rad(angle))",
            f"        cairo_new_sub_path(cr)",
            f"        cairo_move_to(cr, 0, -bwid / 2)",
            f"        cairo_curve_to(cr, blen * 0.55, -bwid / 2, blen * 0.9, -bwid * 0.12, blen, 0)",
            f"        cairo_curve_to(cr, blen * 0.9, bwid * 0.12, blen * 0.55, bwid / 2, 0, bwid / 2)",
            f"        cairo_close_path(cr)",
            f"        cairo_set_source_rgba(cr, fr, fg, fb, alpha)",
            f"        cairo_fill(cr)",
            f"        cairo_restore(cr)",
            f"    end",
            f"",
        ]
        if blur:
            lines += [
                f"    if pct > 0.02 then",
                f"        for k = 1, 2 do",
                f"            local ghost_angle = base_angle - k * (10 + pct * 26) * ({direction})",
                f"            for i = 1, {blades} do",
                f"                draw_blade(ghost_angle + (i - 1) * (360 / {blades}), opacity * (0.16 / k))",
                f"            end",
                f"        end",
                f"    end",
            ]
        lines += [
            f"    for i = 1, {blades} do",
            f"        draw_blade(base_angle + (i - 1) * (360 / {blades}), opacity)",
            f"    end",
            f"",
            f"    cairo_set_source_rgba(cr, {hr}, {hg}, {hb}, opacity)",
            f"    cairo_arc(cr, cx, cy, hub_r, 0, 2 * math.pi)",
            f"    cairo_fill(cr)",
            f"end",
        ]
        return "\n".join(lines)

    # -----------------------------------------------------------------
    # Radial Spectrum
    # -----------------------------------------------------------------
    @visual_generator("visual.radial_spectrum")
    def _gen_radial_spectrum(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        cx = int(p.get("cx", 120))
        cy = int(p.get("cy", 120))
        inner_r = float(p.get("inner_radius", 30.0))
        bars = max(4, min(96, int(p.get("bar_count", 24))))
        bar_w_deg = float(p.get("bar_width_deg", 6.0))
        min_len = float(p.get("min_length", 4.0))
        max_len = float(p.get("max_length", 45.0))
        rounded = bool(p.get("rounded_caps", True))
        speed = float(p.get("speed", 1.0))
        idle_energy = float(p.get("idle_energy", 25.0))
        heat = bool(p.get("heat_map", False))
        draw_center = bool(p.get("draw_center", True))
        opacity = float(p.get("opacity", 0.9))
        r, g, b = _split_rgb(p.get("color", "#4fd1c5"))
        ccr, ccg, ccb = _split_rgb(p.get("center_color", "#1a222c"))
        trigger_expr = ctx.resolve(node, "trigger")

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local cx, cy = {cx}, {cy}",
            f"    local inner_r = {inner_r}",
            f"    local opacity = {opacity}",
            f"    local t = wall_clock()",
            f"    local energy = math.max(tonumber({trigger_expr}) or 0, {idle_energy})",
            f"    cairo_set_line_cap(cr, {'CAIRO_LINE_CAP_ROUND' if rounded else 'CAIRO_LINE_CAP_BUTT'})",
            f"    cairo_set_line_width(cr, math.max(1, inner_r * math.rad({bar_w_deg})))",
        ]
        if not heat:
            lines.append(f"    cairo_set_source_rgba(cr, {r}, {g}, {b}, opacity)")
        lines += [
            f"    for i = 1, {bars} do",
            f"        local ang = math.rad((i - 1) * (360 / {bars}))",
            f"        local seed = i * 12.9898",
            f"        local phase = i * 0.8 + math.sin(seed)",
            f"        local osc = math.sin(t * {speed} * (1.1 + (i % 5) * 0.23) + phase) * 0.5 + 0.5",
            f"        local len = {min_len} + ({max_len} - {min_len}) * clamp((energy / 100) * (0.3 + 0.7 * osc), 0, 1)",
            f"        local x1 = cx + math.cos(ang) * inner_r",
            f"        local y1 = cy + math.sin(ang) * inner_r",
            f"        local x2 = cx + math.cos(ang) * (inner_r + len)",
            f"        local y2 = cy + math.sin(ang) * (inner_r + len)",
        ]
        if heat:
            lines += [
                f"        local hr, hg, hb = studio_heat_rgb(len / math.max({max_len}, 1))",
                f"        cairo_set_source_rgba(cr, hr, hg, hb, opacity)",
            ]
        lines += [
            f"        cairo_move_to(cr, x1, y1)",
            f"        cairo_line_to(cr, x2, y2)",
            f"        cairo_stroke(cr)",
            f"    end",
        ]
        if draw_center:
            lines += [
                f"    cairo_set_source_rgba(cr, {ccr}, {ccg}, {ccb}, opacity)",
                f"    cairo_arc(cr, cx, cy, inner_r, 0, 2 * math.pi)",
                f"    cairo_fill(cr)",
            ]
        lines.append("end")
        return "\n".join(lines)

    # -----------------------------------------------------------------
    # Vinyl Spinner
    # -----------------------------------------------------------------
    @visual_generator("visual.vinyl_spinner")
    def _gen_vinyl_spinner(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        cx = int(p.get("cx", 120))
        cy = int(p.get("cy", 120))
        radius = float(p.get("radius", 90.0))
        label_r = float(p.get("label_radius", 32.0))
        spindle_r = float(p.get("spindle_radius", 3.0))
        grooves = max(0, min(60, int(p.get("groove_count", 14))))
        rpm = float(p.get("rpm", 33.3))
        disc_r, disc_g, disc_b = _split_rgb(p.get("disc_color", "#15161a"))
        groove_r, groove_g, groove_b = _split_rgb(p.get("groove_color", "#2c2e35"))
        lbl_r, lbl_g, lbl_b = _split_rgb(p.get("label_color", "#4fd1c5"))
        show_tonearm = bool(p.get("show_tonearm", False))
        tone_r, tone_g, tone_b = _split_rgb(p.get("tonearm_color", "#9aa2ad"))
        specular = bool(p.get("specular", True))
        opacity = float(p.get("opacity", 1.0))
        key = lua_string_literal(node.id)
        gate_expr = ctx.resolve(node, "spin_gate")

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local cx, cy, R = {cx}, {cy}, {radius}",
            f"    local opacity = {opacity}",
            f"    local key = {key}",
            f"    local st = STATE[key]",
            f"    local t = wall_clock()",
            f"    if st == nil then st = {{angle = 0, last_t = t}}; STATE[key] = st end",
            f"    local dt = t - st.last_t",
            f"    if dt < 0 or dt > 1 then dt = 0 end",
            f"    local gate = tonumber({gate_expr})",
            f"    if gate == nil or gate >= 0.5 then",
            f"        st.angle = st.angle + dt * ({rpm} / 60) * 360",
            f"    end",
            f"    st.last_t = t",
            f"    local ang = st.angle % 360",
            f"",
            f"    cairo_save(cr)",
            f"    cairo_translate(cr, cx, cy)",
            f"    cairo_rotate(cr, math.rad(ang))",
            f"    cairo_set_source_rgba(cr, {disc_r}, {disc_g}, {disc_b}, opacity)",
            f"    cairo_arc(cr, 0, 0, R, 0, 2 * math.pi)",
            f"    cairo_fill(cr)",
        ]
        if grooves > 0:
            lines += [
                f"    cairo_set_line_width(cr, 1)",
                f"    cairo_set_source_rgba(cr, {groove_r}, {groove_g}, {groove_b}, opacity * 0.8)",
                f"    for gi = 1, {grooves} do",
                f"        local gr = {label_r} + (R - {label_r}) * (gi / {grooves})",
                f"        cairo_new_sub_path(cr)",
                f"        cairo_arc(cr, 0, 0, gr, 0, 2 * math.pi)",
                f"        cairo_stroke(cr)",
                f"    end",
            ]
        lines += [
            f"    cairo_set_source_rgba(cr, {lbl_r}, {lbl_g}, {lbl_b}, opacity)",
            f"    cairo_arc(cr, 0, 0, {label_r}, 0, 2 * math.pi)",
            f"    cairo_fill(cr)",
        ]
        if spindle_r > 0:
            lines += [
                f"    cairo_set_source_rgba(cr, 0, 0, 0, opacity * 0.9)",
                f"    cairo_arc(cr, 0, 0, {spindle_r}, 0, 2 * math.pi)",
                f"    cairo_fill(cr)",
            ]
        if specular:
            lines += [
                f"    cairo_set_source_rgba(cr, 1, 1, 1, opacity * 0.08)",
                f"    cairo_move_to(cr, -R, -R * 0.15)",
                f"    cairo_line_to(cr, R, -R * 0.65)",
                f"    cairo_line_to(cr, R, -R * 0.35)",
                f"    cairo_line_to(cr, -R, R * 0.15)",
                f"    cairo_close_path(cr)",
                f"    cairo_fill(cr)",
            ]
        lines.append("    cairo_restore(cr)")
        if show_tonearm:
            lines += [
                f"    cairo_set_line_width(cr, 3)",
                f"    cairo_set_line_cap(cr, CAIRO_LINE_CAP_ROUND)",
                f"    cairo_set_source_rgba(cr, {tone_r}, {tone_g}, {tone_b}, opacity)",
                f"    local pivot_x, pivot_y = cx + R * 0.9, cy - R * 0.9",
                f"    local rest_x, rest_y = cx + R * 0.15, cy - R * 0.05",
                f"    cairo_move_to(cr, pivot_x, pivot_y)",
                f"    cairo_line_to(cr, rest_x, rest_y)",
                f"    cairo_stroke(cr)",
                f"    cairo_arc(cr, pivot_x, pivot_y, 4, 0, 2 * math.pi)",
                f"    cairo_fill(cr)",
            ]
        lines.append("end")
        return "\n".join(lines)

    # -----------------------------------------------------------------
    # Matrix Rain
    # -----------------------------------------------------------------
    @visual_generator("visual.matrix_rain")
    def _gen_matrix_rain(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        x = int(p.get("x", 20))
        y = int(p.get("y", 20))
        w = int(p.get("width", 160))
        h = int(p.get("height", 200))
        fsize = int(p.get("font_size", 14))
        gap = int(p.get("column_gap", 2))
        trail = max(2, int(p.get("trail_length", 10)))
        speed = float(p.get("speed", 1.0))
        flicker = float(p.get("flicker_hz", 6.0))
        charset = str(p.get("charset", "01$%#@&*+=-:.") or "01")
        opacity = float(p.get("opacity", 0.9))
        hr, hg, hb = _split_rgb(p.get("color", "#39ff14"))
        tr, tg, tb = _split_rgb(p.get("tail_color", "#0b6b12"))
        charset_lit = lua_string_literal(charset)
        col_w = fsize + gap

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local x0, y0 = {x}, {y}",
            f"    local bw, bh = {w}, {h}",
            f"    local fsize = {fsize}",
            f"    local col_w = {col_w}",
            f"    local opacity = {opacity}",
            f"    local charset = {charset_lit}",
            f"    local nchars = #charset",
            f"    if nchars == 0 then return end",
            f"    local t = wall_clock()",
            f"    cairo_save(cr)",
            f"    cairo_rectangle(cr, x0, y0, bw, bh)",
            f"    cairo_clip(cr)",
            f"    cairo_select_font_face(cr, 'Monospace', CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_BOLD)",
            f"    cairo_set_font_size(cr, fsize)",
            f"    local ncols = math.max(1, math.floor(bw / col_w))",
            f"    for c = 1, ncols do",
            f"        local seed = c * 12.9898",
            f"        local frac = seed - math.floor(seed)",
            f"        local col_speed = {speed} * (0.6 + 0.8 * frac) * 60",
            f"        local total = bh + {trail} * fsize",
            f"        local head = ((t * col_speed + seed * 37) % total) - {trail} * fsize",
            f"        local cx = x0 + (c - 1) * col_w",
            f"        for k = 0, {trail} - 1 do",
            f"            local gy = head - k * fsize",
            f"            if gy >= -fsize and gy <= bh then",
            f"                local bucket = math.floor(t * {flicker})",
            f"                local hseed = c * 91.7 + math.floor(gy / fsize) * 13.1 + bucket * 3.7",
            f"                local hfrac = math.abs(math.sin(hseed) * 43758.5453)",
            f"                hfrac = hfrac - math.floor(hfrac)",
            f"                local idx = math.floor(hfrac * nchars) + 1",
            f"                local ch = string.sub(charset, idx, idx)",
            f"                local fade = 1 - (k / {trail})",
            f"                local rr = {tr} + ({hr} - {tr}) * fade",
            f"                local gg = {tg} + ({hg} - {tg}) * fade",
            f"                local bbv = {tb} + ({hb} - {tb}) * fade",
            f"                local a = opacity * (k == 0 and 1 or (0.15 + 0.7 * fade))",
            f"                cairo_set_source_rgba(cr, rr, gg, bbv, a)",
            f"                cairo_move_to(cr, cx, y0 + gy + fsize)",
            f"                cairo_show_text(cr, ch)",
            f"            end",
            f"        end",
            f"    end",
            f"    cairo_restore(cr)",
            f"end",
        ]
        return "\n".join(lines)

    # -----------------------------------------------------------------
    # Flip Card
    # -----------------------------------------------------------------
    @visual_generator("visual.flip_digit")
    def _gen_flip_digit(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        x = int(p.get("x", 20))
        y = int(p.get("y", 20))
        w = int(p.get("width", 56))
        h = int(p.get("height", 72))
        radius = float(p.get("corner_radius", 6.0))
        dur = max(0.05, float(p.get("flip_duration", 0.35)))
        font = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
        fsize = int(p.get("font_size", 36))
        card_r, card_g, card_b = _split_rgb(p.get("card_color", "#1a222c"))
        text_r, text_g, text_b = _split_rgb(p.get("text_color", "#e8eaed"))
        div_r, div_g, div_b = _split_rgb(p.get("divider_color", "#0c0f14"))
        flap_r, flap_g, flap_b = _split_rgb(p.get("flap_color", "#262c38"))
        opacity = float(p.get("opacity", 1.0))
        key = lua_string_literal(node.id)
        value_expr = ctx.resolve(node, "value")
        text_opts = (f"{{family = '{font}', size = {fsize}, "
                     f"r = {text_r}, g = {text_g}, b = {text_b}, a = opacity, align = 'center'}}")

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local x0, y0, w, h = {x}, {y}, {w}, {h}",
            f"    local mid = y0 + h / 2",
            f"    local opacity = {opacity}",
            f"    local key = {key}",
            f"    local val = tostring({value_expr})",
            f"    local st = STATE[key]",
            f"    local t = wall_clock()",
            f"    if st == nil then st = {{cur = val, prev = val, flip_t = -999}}; STATE[key] = st end",
            f"    if val ~= st.cur then st.prev = st.cur; st.cur = val; st.flip_t = t end",
            f"    local progress = clamp((t - st.flip_t) / {dur}, 0, 1)",
            f"",
            f"    rounded_rect(cr, x0, y0, w, h, {radius})",
            f"    cairo_set_source_rgba(cr, {card_r}, {card_g}, {card_b}, opacity)",
            f"    cairo_fill(cr)",
            f"",
            f"    local function draw_half(y_top, y_bot)",
            f"        cairo_save(cr)",
            f"        cairo_rectangle(cr, x0, y_top, w, y_bot - y_top)",
            f"        cairo_clip(cr)",
            f"        studio_draw_text(cr, st.cur, x0 + w / 2, y0 + h / 2 + {fsize} * 0.36, {text_opts})",
            f"        cairo_restore(cr)",
            f"    end",
            f"    draw_half(y0, mid)",
            f"",
            f"    cairo_set_line_width(cr, 1)",
            f"    cairo_set_source_rgba(cr, {div_r}, {div_g}, {div_b}, opacity)",
            f"    cairo_move_to(cr, x0, mid)",
            f"    cairo_line_to(cr, x0 + w, mid)",
            f"    cairo_stroke(cr)",
            f"",
            f"    if progress < 1 then",
            f"        local scale = math.max(1 - progress, 0.02)",
            f"        cairo_save(cr)",
            f"        cairo_translate(cr, 0, mid)",
            f"        cairo_scale(cr, 1, scale)",
            f"        cairo_translate(cr, 0, -mid)",
            f"        rounded_rect(cr, x0, y0, w, mid - y0, {radius})",
            f"        cairo_set_source_rgba(cr, {flap_r}, {flap_g}, {flap_b}, opacity)",
            f"        cairo_fill(cr)",
            f"        cairo_save(cr)",
            f"        cairo_rectangle(cr, x0, y0, w, mid - y0)",
            f"        cairo_clip(cr)",
            f"        studio_draw_text(cr, st.prev, x0 + w / 2, y0 + h / 2 + {fsize} * 0.36, {text_opts})",
            f"        cairo_restore(cr)",
            f"        cairo_set_source_rgba(cr, 0, 0, 0, opacity * 0.35 * (1 - scale))",
            f"        cairo_rectangle(cr, x0, mid - 4, w, 4)",
            f"        cairo_fill(cr)",
            f"        cairo_restore(cr)",
            f"    end",
            f"",
            f"    draw_half(mid, y0 + h)",
            f"end",
        ]
        return "\n".join(lines)

    # -----------------------------------------------------------------
    # Radar Chart
    # -----------------------------------------------------------------
    @visual_generator("visual.radar_chart")
    def _gen_radar_chart(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        cx = int(p.get("cx", 120))
        cy = int(p.get("cy", 120))
        radius = float(p.get("radius", 80.0))
        axis_count = max(3, min(6, int(p.get("axis_count", 5))))
        min_v = float(p.get("min_value", 0.0))
        max_v = float(p.get("max_value", 100.0))
        span = (max_v - min_v) or 1.0
        grid_rings = max(0, int(p.get("grid_rings", 4)))
        grid_r, grid_g, grid_b = _split_rgb(p.get("grid_color", "#33313a"))
        fill_r, fill_g, fill_b = _split_rgb(p.get("fill_color", "#4fd1c5"))
        fill_opacity = float(p.get("fill_opacity", 0.35))
        line_width = float(p.get("line_width", 2.0))
        show_dots = bool(p.get("show_dots", True))
        show_labels = bool(p.get("show_labels", True))
        font = str(p.get("font_family", "Sans") or "Sans").replace("'", "")
        fsize = int(p.get("font_size", 11))
        lbl_r, lbl_g, lbl_b = _split_rgb(p.get("label_color", "#9aa2ad"))
        opacity = float(p.get("opacity", 1.0))

        value_exprs = [ctx.resolve(node, f"value_{i}") for i in range(1, axis_count + 1)]
        labels = [str(p.get(f"label_{i}", "") or "") for i in range(1, axis_count + 1)]

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local cx, cy, R = {cx}, {cy}, {radius}",
            f"    local opacity = {opacity}",
            f"    local min_v, span = {min_v}, {span}",
        ]
        if grid_rings > 0:
            lines += [
                f"    cairo_set_line_width(cr, 1)",
                f"    cairo_set_source_rgba(cr, {grid_r}, {grid_g}, {grid_b}, opacity * 0.7)",
                f"    for ring = 1, {grid_rings} do",
                f"        local rr = R * (ring / {grid_rings})",
                f"        cairo_new_sub_path(cr)",
                f"        for i = 0, {axis_count - 1} do",
                f"            local a = math.rad(-90 + i * (360 / {axis_count}))",
                f"            local px, py = cx + math.cos(a) * rr, cy + math.sin(a) * rr",
                f"            if i == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end",
                f"        end",
                f"        cairo_close_path(cr)",
                f"        cairo_stroke(cr)",
                f"    end",
            ]
        lines += [
            f"    cairo_set_source_rgba(cr, {grid_r}, {grid_g}, {grid_b}, opacity * 0.7)",
            f"    for i = 0, {axis_count - 1} do",
            f"        local a = math.rad(-90 + i * (360 / {axis_count}))",
            f"        cairo_move_to(cr, cx, cy)",
            f"        cairo_line_to(cr, cx + math.cos(a) * R, cy + math.sin(a) * R)",
            f"        cairo_stroke(cr)",
            f"    end",
            f"    local pts = {{}}",
        ]
        for i, vexpr in enumerate(value_exprs):
            lines += [
                f"    do",
                f"        local a = math.rad(-90 + {i} * (360 / {axis_count}))",
                f"        local v = tonumber({vexpr}) or min_v",
                f"        local pct = clamp((v - min_v) / span, 0, 1)",
                f"        pts[{i + 1}] = {{cx + math.cos(a) * R * pct, cy + math.sin(a) * R * pct}}",
                f"    end",
            ]
        lines += [
            f"    cairo_new_sub_path(cr)",
            f"    for i = 1, #pts do",
            f"        if i == 1 then cairo_move_to(cr, pts[i][1], pts[i][2]) else cairo_line_to(cr, pts[i][1], pts[i][2]) end",
            f"    end",
            f"    cairo_close_path(cr)",
            f"    cairo_set_source_rgba(cr, {fill_r}, {fill_g}, {fill_b}, opacity * {fill_opacity})",
            f"    cairo_fill_preserve(cr)",
            f"    cairo_set_line_width(cr, {line_width})",
            f"    cairo_set_source_rgba(cr, {fill_r}, {fill_g}, {fill_b}, opacity)",
            f"    cairo_stroke(cr)",
        ]
        if show_dots:
            lines += [
                f"    cairo_set_source_rgba(cr, {fill_r}, {fill_g}, {fill_b}, opacity)",
                f"    for i = 1, #pts do",
                f"        cairo_arc(cr, pts[i][1], pts[i][2], math.max(2, {line_width}), 0, 2 * math.pi)",
                f"        cairo_fill(cr)",
                f"    end",
            ]
        if show_labels:
            lines += [
                f"    cairo_select_font_face(cr, '{font}', CAIRO_FONT_SLANT_NORMAL, CAIRO_FONT_WEIGHT_NORMAL)",
                f"    cairo_set_font_size(cr, {fsize})",
            ]
            for i, lbl in enumerate(labels):
                lit = lua_string_literal(lbl)
                lines += [
                    f"    do",
                    f"        local a = math.rad(-90 + {i} * (360 / {axis_count}))",
                    f"        local lx = cx + math.cos(a) * (R + 14)",
                    f"        local ly = cy + math.sin(a) * (R + 14)",
                    f"        studio_draw_text(cr, {lit}, lx, ly, "
                    f"{{family = '{font}', size = {fsize}, r = {lbl_r}, g = {lbl_g}, b = {lbl_b}, "
                    f"a = opacity, align = 'center'}})",
                    f"    end",
                ]
        lines.append("end")
        return "\n".join(lines)

    # -----------------------------------------------------------------
    # Loading Dots
    # -----------------------------------------------------------------
    @visual_generator("visual.loading_dots")
    def _gen_loading_dots(node, ctx):
        fn = f"draw_node_{lua_safe_id(node.id)}"
        p = node.props
        x = int(p.get("x", 20))
        y = int(p.get("y", 20))
        dot_r = float(p.get("dot_radius", 4.0))
        gap = float(p.get("gap", 14.0))
        bounce = float(p.get("bounce_height", 8.0))
        speed = float(p.get("speed", 2.0))
        opacity = float(p.get("opacity", 1.0))
        r, g, b = _split_rgb(p.get("color", "#e8eaed"))

        lines = [
            f"local function {fn}(cr, W, H)",
            f"    local x0, y0 = {x}, {y}",
            f"    local t = wall_clock()",
            f"    cairo_set_source_rgba(cr, {r}, {g}, {b}, {opacity})",
            f"    for i = 0, 2 do",
            f"        local phase = t * {speed} - i * 0.6",
            f"        local bounce = math.max(0, math.sin(phase)) * {bounce}",
            f"        cairo_arc(cr, x0 + i * {gap}, y0 - bounce, {dot_r}, 0, 2 * math.pi)",
            f"        cairo_fill(cr)",
            f"    end",
            f"end",
        ]
        return "\n".join(lines)
