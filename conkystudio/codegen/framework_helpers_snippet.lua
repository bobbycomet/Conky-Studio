-- ---------------------------------------------------------------------
--  Studio extensions: state helpers, text block, heat colour
--  (splice into FRAMEWORK_LUA in lua_framework.py)
-- ---------------------------------------------------------------------
-- ---------------------------------------------------------------------
--  Studio extensions: state helpers, text block, heat colour, math,
--  colour science, path builders, noise, animation, composition
--  (already spliced into FRAMEWORK_LUA in lua_framework.py)
--
--  This file is kept as a human-readable reference of the public API
--  that every generated render.lua and every Custom Lua node can call.
-- ---------------------------------------------------------------------

--[[
  MATH / EASING
  clamp(v, lo, hi)
  lerp(a, b, t)
  remap(v, in_lo, in_hi, out_lo, out_hi)
  fract(x)
  smoothstep(edge0, edge1, x)
  smootherstep(edge0, edge1, x)
  ease_in_out_cubic(t)
  ease_out_expo(t)
  ease_in_out_expo(t)
  ping_pong(t)
  spring(current, target, velocity, stiffness, damping, dt) → new_val, new_vel

  STATE / ANIMATION
  studio_get_state(key, default)
  studio_set_state(key, value)
  studio_anim(key, target, {stiffness, damping, immediate}) → current
  studio_set_ttl(key, value, seconds)
  studio_get_ttl(key, default)

  COLOUR
  studio_heat_rgb(t)          -- teal → yellow → red
  studio_cool_warm_rgb(t)
  studio_fire_rgb(t)
  hsl_to_rgb(h, s, l) → r,g,b
  rgb_to_hsl(r, g, b) → h,s,l
  lerp_rgb(r0,g0,b0, r1,g1,b1, t)
  desaturate(r, g, b, amount)

  TEXT
  studio_draw_text(cr, text, x, y, opts)
      opts: family, size, bold, italic, r,g,b,a, align, halo, outline
  studio_measure_text(cr, text, opts) → width, height
  studio_draw_text_wrapped(cr, text, x, y, max_width, opts) → total_height
  studio_draw_pill(cr, text, x, y, opts) → width, height
      extra opts: pad_x, pad_y, radius, bg_r,bg_g,bg_b,bg_a

  PATHS / PRIMITIVES
  rounded_rect(cr, x, y, w, h, r)
  regular_polygon_path(cr, cx, cy, radius, sides, rotation_deg)
  star_path(cr, cx, cy, outer_r, inner_r, points, rotation_deg)
  dashed_line(cr, x1, y1, x2, y2, dash, gap)
  arrow_path(cr, x1, y1, x2, y2, head_len, head_angle_deg)
  studio_glow(cr, r, g, b, a, layers)   -- stroke_preserve glow
  soft_shadow_rect(cr, x, y, w, h, radius, blur, alpha)

  IMAGE
  load_image_cached(path)
  draw_image_fit(cr, img, x, y, size, rotation_deg, opacity)
  draw_image_box(cr, img, x, y, w, h, mode, rotation_deg, opacity)
      mode = "fit" | "fill" | "stretch"
  load_image_periodic(path, state_key)

  NOISE
  value_noise(x, y)
  fbm(x, y, octaves)

  TRANSFORMS
  with_transform(cr, function() ... end)
  with_clip_rect(cr, x, y, w, h, function() ... end)

  TIME / FORMAT
  wall_clock()
  format_seconds(sec)
  format_bytes(n)
  greeting_for_hour(h)
]]

local function studio_get_state(key, default)
    local v = STATE[key]
    if v == nil then return default end
    return v
end

local function studio_set_state(key, value)
    STATE[key] = value
    return value
end

-- Simple left/center/right text with optional soft halo (parchment readability).
-- opts: { family, size, bold, italic, r, g, b, a, align, halo }
local function studio_draw_text(cr, text, x, y, opts)
    opts = opts or {}
    local family = opts.family or "Sans"
    local size = opts.size or 12
    local slant = (opts.italic and CAIRO_FONT_SLANT_ITALIC) or CAIRO_FONT_SLANT_NORMAL
    local weight = (opts.bold and CAIRO_FONT_WEIGHT_BOLD) or CAIRO_FONT_WEIGHT_NORMAL
    local r = opts.r or 1
    local g = opts.g or 1
    local b = opts.b or 1
    local a = opts.a or 1
    local align = opts.align or "left"
    text = tostring(text or "")

    cairo_select_font_face(cr, family, slant, weight)
    cairo_set_font_size(cr, size)
    local ext = cairo_text_extents_t:create()
    tolua.takeownership(ext)
    cairo_text_extents(cr, text, ext)

    local tx = x
    if align == "center" then
        tx = x - ext.width / 2 - ext.x_bearing
    elseif align == "right" then
        tx = x - ext.width - ext.x_bearing
    else
        tx = x - ext.x_bearing
    end
    local ty = y - ext.y_bearing

    if opts.halo then
        cairo_set_source_rgba(cr, 0, 0, 0, a * 0.45)
        for dx = -1, 1 do
            for dy = -1, 1 do
                if dx ~= 0 or dy ~= 0 then
                    cairo_move_to(cr, tx + dx, ty + dy)
                    cairo_show_text(cr, text)
                end
            end
        end
    end
    cairo_set_source_rgba(cr, r, g, b, a)
    cairo_move_to(cr, tx, ty)
    cairo_show_text(cr, text)
end

-- Map t in [0,1] to a cool→warm RGB triple (teal → yellow → red).
local function studio_heat_rgb(t)
    t = clamp(tonumber(t) or 0, 0, 1)
    if t < 0.5 then
        local u = t * 2
        return lerp(0.31, 0.96, u), lerp(0.82, 0.84, u), lerp(0.77, 0.25, u)
    end
    local u = (t - 0.5) * 2
    return lerp(0.96, 0.88, u), lerp(0.84, 0.25, u), lerp(0.25, 0.25, u)
end
