"""
The static portion of every generated render.lua. This is plain text,
not a Jinja/format template -- it never varies between projects, so it's
just spliced in verbatim by lua_gen.build_render_lua(). Only the
generated sections below it (constants, refresh_sources, per-node draw
functions, main_draw_impl) differ per project.

Where a pattern below traces back to one of your existing themes, the
comment says so -- this is meant to read as "the validated parts of your
own code, generalized," not a rewrite from scratch.

Extended (v1.1+) with a deep set of math, colour, text, path, animation,
noise and composition helpers while remaining pure Lua 5.1 + Cairo.
"""

FRAMEWORK_LUA = r'''
-- =====================================================================
--  Conky Studio runtime framework (generated, do not hand-edit this
--  section -- re-running Build & Run overwrites it). Node-specific draw
--  functions and refresh_sources() below this block are what changed
--  when you edited the graph.
-- =====================================================================

require 'cairo'
local RSVG_OK = pcall(require, 'rsvg')
-- Guarded with pcall because not every Conky build ships the RSVG Lua
-- binding; a missing `require` at load time would otherwise hard-crash
-- the whole script before any per-frame pcall could catch it. Image/Icon
-- nodes pointed at an .svg just get skipped (with one printed warning)
-- on a build without it, the same graceful-degrade behavior load_image()
-- already uses for a missing PNG.

math.randomseed(os.time())

local IMAGE_CACHE = {}
local CACHE_KV = {}   -- path -> last-parsed key/value table, refreshed by refresh_sources()
local SRC = {}          -- node_id -> resolved current value, refreshed by refresh_sources()
local HIST = {}          -- node_id -> ring buffer of past values, for History Graph nodes
local STATE = {}          -- node_id -> arbitrary persisted per-node state (eased values, phase)

-- ---------------------------------------------------------------------
--  Wall-clock timing.
--  os.clock() measures CPU time *consumed by this process*, not elapsed
--  real time -- it barely advances while Conky sleeps between draws, so
--  anything timed off it (rotation speed, pulse rate) runs at the wrong,
--  system-load-dependent speed. /proc/uptime gives true monotonic wall
--  time instead, so "rotate 360 degrees every 20 seconds" actually means
--  20 real seconds regardless of how busy the machine is.
-- ---------------------------------------------------------------------
local function wall_clock()
    local f = io.open('/proc/uptime', 'r')
    if f then
        local line = f:read('*l')
        f:close()
        if line then
            local secs = tonumber(line:match('^(%S+)'))
            if secs then return secs end
        end
    end
    return os.time()   -- whole-second fallback; still real time, unlike os.clock()
end

local function clamp(v, lo, hi)
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end

local function lerp(a, b, t)
    return a + (b - a) * clamp(t, 0, 1)
end

-- ---------------------------------------------------------------------
--  Extended math / easing
-- ---------------------------------------------------------------------
local function remap(v, in_lo, in_hi, out_lo, out_hi)
    if in_hi == in_lo then return out_lo end
    return out_lo + (out_hi - out_lo) * clamp((v - in_lo) / (in_hi - in_lo), 0, 1)
end

local function fract(x)
    return x - math.floor(x)
end

local function smoothstep(edge0, edge1, x)
    local t = clamp((x - edge0) / (edge1 - edge0), 0, 1)
    return t * t * (3 - 2 * t)
end

local function smootherstep(edge0, edge1, x)
    local t = clamp((x - edge0) / (edge1 - edge0), 0, 1)
    return t * t * t * (t * (t * 6 - 15) + 10)
end

local function ease_in_out_cubic(t)
    t = clamp(t, 0, 1)
    if t < 0.5 then return 4 * t * t * t end
    return 1 - ((-2 * t + 2) ^ 3) / 2
end

local function ease_out_expo(t)
    t = clamp(t, 0, 1)
    if t >= 1 then return 1 end
    return 1 - (2 ^ (-10 * t))
end

local function ease_in_out_expo(t)
    t = clamp(t, 0, 1)
    if t == 0 or t == 1 then return t end
    if t < 0.5 then return (2 ^ (20 * t - 10)) / 2 end
    return (2 - (2 ^ (-20 * t + 10))) / 2
end

local function ping_pong(t)
    t = fract(t)
    if t < 0.5 then return t * 2 end
    return 2 - t * 2
end

-- Simple critically-damped spring approximation (good for UI feel)
local function spring(current, target, velocity, stiffness, damping, dt)
    stiffness = stiffness or 180
    damping = damping or 12
    dt = dt or 0.016
    local force = -stiffness * (current - target)
    local damp = -damping * velocity
    velocity = velocity + (force + damp) * dt
    current = current + velocity * dt
    return current, velocity
end

-- ---------------------------------------------------------------------
--  Safe wrappers around conky_parse
-- ---------------------------------------------------------------------
local function safe_parse(expr, fallback)
    local ok, result = pcall(conky_parse, expr)
    if ok and result ~= nil then return result end
    return fallback
end

local function safe_number(expr, fallback)
    local s = safe_parse(expr, nil)
    local n = tonumber(s)
    if n ~= nil then return n end
    return fallback
end

local function read_kv_cache(path)
    local t = {}
    local f = io.open(path, 'r')
    if not f then return t end
    for line in f:lines() do
        local k, v = line:match('^([%w_]+)=(.*)$')
        if k then t[k] = v end
    end
    f:close()
    return t
end

local _resolved_iface = nil
local function resolve_net_iface()
    if _resolved_iface then return _resolved_iface end
    local up_iface, any_iface = nil, nil
    local p = io.popen('ls /sys/class/net 2>/dev/null')
    if p then
        for name in p:lines() do
            if name ~= 'lo' then
                any_iface = any_iface or name
                local f = io.open('/sys/class/net/' .. name .. '/operstate', 'r')
                if f then
                    local st = f:read('*l')
                    f:close()
                    if st == 'up' and not up_iface then up_iface = name end
                end
            end
        end
        p:close()
    end
    _resolved_iface = up_iface or any_iface or 'eth0'
    return _resolved_iface
end

-- ---------------------------------------------------------------------
--  Drawing surface
-- ---------------------------------------------------------------------
local function get_draw_surface()
    if conky_window == nil then return nil end
    local ww, wh = conky_window.width, conky_window.height
    if ww == nil or wh == nil or ww == 0 or wh == 0 then return nil end

    if conky_surface ~= nil then
        local cs = conky_surface()
        if cs == nil then return nil end
        return cs, ww, wh, false
    end

    if conky_window.display == nil then return nil end
    local cs = cairo_xlib_surface_create(conky_window.display, conky_window.drawable, conky_window.visual, ww, wh)
    return cs, ww, wh, true
end

local function rounded_rect(cr, x, y, w, h, r)
    r = math.min(r, w / 2, h / 2)
    if r <= 0 then
        cairo_rectangle(cr, x, y, w, h)
        return
    end
    cairo_new_sub_path(cr)
    cairo_arc(cr, x + w - r, y + r,     r, -math.pi / 2, 0)
    cairo_arc(cr, x + w - r, y + h - r, r, 0, math.pi / 2)
    cairo_arc(cr, x + r,     y + h - r, r, math.pi / 2, math.pi)
    cairo_arc(cr, x + r,     y + r,     r, math.pi, 3 * math.pi / 2)
    cairo_close_path(cr)
end

-- ---------------------------------------------------------------------
--  Image loading
-- ---------------------------------------------------------------------
local function load_image_cached(path)
    if path == nil or path == '' then return nil end
    local cached = IMAGE_CACHE[path]
    if cached ~= nil then
        if cached == false then return nil end
        return cached
    end

    local is_svg = path:match('%.svg$') ~= nil
    if is_svg then
        if not RSVG_OK then
            print('[conky-studio] WARNING: ' .. path .. ' is an SVG but this Conky build has no RSVG Lua binding -- skipping')
            IMAGE_CACHE[path] = false
            return nil
        end
        local ok, rh = pcall(rsvg_create_handle_from_file, path)
        if not ok or rh == nil then
            print('[conky-studio] WARNING: failed to load ' .. path .. ' -- that element will be skipped')
            IMAGE_CACHE[path] = false
            return nil
        end
        local rd = RsvgDimensionData:create()
        rsvg_handle_get_dimensions(rh, rd)
        local iw, ih = rd:get()
        local entry = { kind = 'svg', handle = rh, w = iw, h = ih }
        IMAGE_CACHE[path] = entry
        return entry
    end

    local ok, surface = pcall(cairo_image_surface_create_from_png, path)
    if not ok or surface == nil then
        print('[conky-studio] WARNING: failed to load ' .. path .. ' -- that element will be skipped')
        IMAGE_CACHE[path] = false
        return nil
    end
    local iw = cairo_image_surface_get_width(surface)
    local ih = cairo_image_surface_get_height(surface)
    local entry = { kind = 'png', surface = surface, w = iw, h = ih }
    IMAGE_CACHE[path] = entry
    return entry
end

local function draw_image_fit(cr, img, x, y, size, rotation_deg, opacity)
    if img == nil then return end
    local scale = math.min(size / img.w, size / img.h)
    local dw, dh = img.w * scale, img.h * scale
    cairo_save(cr)
    cairo_translate(cr, x + size / 2, y + size / 2)
    if rotation_deg and rotation_deg ~= 0 then
        cairo_rotate(cr, rotation_deg * math.pi / 180)
    end
    cairo_translate(cr, -dw / 2, -dh / 2)

    if img.kind == 'svg' then
        cairo_scale(cr, scale, scale)
        cairo_push_group(cr)
        rsvg_handle_render_cairo(img.handle, cr)
        cairo_pop_group_to_source(cr)
        cairo_paint_with_alpha(cr, opacity or 1)
    else
        cairo_scale(cr, scale, scale)
        cairo_set_source_surface(cr, img.surface, 0, 0)
        cairo_paint_with_alpha(cr, opacity or 1)
    end
    cairo_restore(cr)
end

-- Extended image drawing: mode = "fit" | "fill" | "stretch"
local function draw_image_box(cr, img, x, y, w, h, mode, rotation_deg, opacity)
    if img == nil then return end
    mode = mode or "fit"
    opacity = opacity or 1
    local scale_x, scale_y
    if mode == "stretch" then
        scale_x = w / img.w
        scale_y = h / img.h
    elseif mode == "fill" then
        local s = math.max(w / img.w, h / img.h)
        scale_x, scale_y = s, s
    else -- fit
        local s = math.min(w / img.w, h / img.h)
        scale_x, scale_y = s, s
    end
    local dw, dh = img.w * scale_x, img.h * scale_y
    cairo_save(cr)
    cairo_rectangle(cr, x, y, w, h)
    cairo_clip(cr)
    cairo_translate(cr, x + w / 2, y + h / 2)
    if rotation_deg and rotation_deg ~= 0 then
        cairo_rotate(cr, rotation_deg * math.pi / 180)
    end
    cairo_translate(cr, -dw / 2, -dh / 2)
    if img.kind == 'svg' then
        cairo_scale(cr, scale_x, scale_y)
        cairo_push_group(cr)
        rsvg_handle_render_cairo(img.handle, cr)
        cairo_pop_group_to_source(cr)
        cairo_paint_with_alpha(cr, opacity)
    else
        cairo_scale(cr, scale_x, scale_y)
        cairo_set_source_surface(cr, img.surface, 0, 0)
        cairo_paint_with_alpha(cr, opacity)
    end
    cairo_restore(cr)
end

local BAR_SLANT = 650 / 379
local function bar_trapezoid_path(cr, x, y, w, h)
    local inset = math.min(h * BAR_SLANT, w / 2)
    cairo_new_sub_path(cr)
    cairo_move_to(cr, x, y)
    cairo_line_to(cr, x + w, y)
    cairo_line_to(cr, x + w - inset, y + h)
    cairo_line_to(cr, x + inset, y + h)
    cairo_close_path(cr)
end

local function battery_exists(device)
    local f = io.open('/sys/class/power_supply/' .. (device or 'BAT0') .. '/capacity', 'r')
    if f then f:close(); return true end
    return false
end

local function greeting_for_hour(h)
    if h == nil then return 'Hello' end
    if h >= 5 and h < 12 then return 'Good Morning' end
    if h >= 12 and h < 17 then return 'Good Afternoon' end
    if h >= 17 and h < 22 then return 'Good Evening' end
    return 'Good Night'
end

local function utf8_encode(cp)
    if cp < 0x80 then
        return string.char(cp)
    elseif cp < 0x800 then
        return string.char(0xC0 + math.floor(cp / 0x40), 0x80 + (cp % 0x40))
    elseif cp < 0x10000 then
        return string.char(
            0xE0 + math.floor(cp / 0x1000),
            0x80 + (math.floor(cp / 0x40) % 0x40),
            0x80 + (cp % 0x40))
    else
        return string.char(
            0xF0 + math.floor(cp / 0x40000),
            0x80 + (math.floor(cp / 0x1000) % 0x40),
            0x80 + (math.floor(cp / 0x40) % 0x40),
            0x80 + (cp % 0x40))
    end
end

local _PERIODIC_IMAGE_STATE = {}
local function load_image_periodic(path, state_key)
    local prev = _PERIODIC_IMAGE_STATE[state_key]
    local mtime = nil
    local f = io.open(path, 'rb')
    if f then f:close() end
    local stat = io.popen and io.popen("stat -c %Y '" .. path .. "' 2>/dev/null")
    if stat then
        mtime = stat:read('*l')
        stat:close()
    end
    if prev and prev.mtime == mtime and prev.entry then
        return prev.entry
    end
    if IMAGE_CACHE[path] ~= nil then
        IMAGE_CACHE[path] = nil
    end
    local entry = load_image_cached(path)
    _PERIODIC_IMAGE_STATE[state_key] = { mtime = mtime, entry = entry }
    return entry
end

-- ---------------------------------------------------------------------
--  State helpers
-- ---------------------------------------------------------------------
local function studio_get_state(key, default)
    local v = STATE[key]
    if v == nil then return default end
    return v
end

local function studio_set_state(key, value)
    STATE[key] = value
    return value
end

-- Persistent animated value with optional spring physics
-- Usage: local v = studio_anim(key, target, {stiffness=180, damping=12})
local function studio_anim(key, target, opts)
    opts = opts or {}
    local st = STATE[key]
    local t = wall_clock()
    if st == nil then
        st = { value = target, velocity = 0, last_t = t }
        STATE[key] = st
        return target
    end
    local dt = t - st.last_t
    if dt < 0 or dt > 0.25 then dt = 0.016 end
    st.last_t = t
    if opts.immediate then
        st.value = target
        st.velocity = 0
        return st.value
    end
    st.value, st.velocity = spring(st.value, target, st.velocity,
                                   opts.stiffness or 180, opts.damping or 12, dt)
    return st.value
end

-- Simple expiring state (auto-clears after seconds)
local function studio_set_ttl(key, value, seconds)
    STATE[key] = { value = value, expires = wall_clock() + (seconds or 1) }
    return value
end

local function studio_get_ttl(key, default)
    local st = STATE[key]
    if st == nil then return default end
    if type(st) == "table" and st.expires then
        if wall_clock() > st.expires then
            STATE[key] = nil
            return default
        end
        return st.value
    end
    return st
end

-- ---------------------------------------------------------------------
--  Plugin / Custom Lua SDK
--
--  Everything above (STATE[key], the pcall wrappers, every drawing/
--  colour/math helper) keeps working exactly as before -- this section
--  is purely additive. It exists because a flat STATE table and 12
--  numbered Data inputs are fine for a handful of hand-tuned nodes, but
--  become the limiting factor the moment someone starts building a real
--  plugin: shared code has nowhere to live except copy-pasted into every
--  node, and two nodes that both reach for STATE['angle'] silently
--  stomp each other. Generated by conkystudio.codegen.lua_gen for every
--  Custom Lua node -- see _gen_custom_lua's docstring for the NODE_ID /
--  NS / PROPS locals every Custom Lua node box gets, and the 'module'
--  run_mode this registry enables.
-- ---------------------------------------------------------------------

-- One persistent, private table per node id. Prefer this over STATE[key]
-- inside a Custom Lua node -- NS.angle is never going to collide with
-- another node's NS.angle, even if that node's code was copy-pasted from
-- this one. Safe to call every frame; the table is created once and
-- reused after that.
local _NODE_STATE = {}
local function studio_node_state(id)
    local t = _NODE_STATE[id]
    if t == nil then
        t = {}
        _NODE_STATE[id] = t
    end
    return t
end

-- Runs fn() at most once per id, ever (for the life of the Conky
-- process). Useful inside a 'draw'-mode Custom Lua node for one-time
-- setup (building a lookup table, parsing a config string) that would
-- be wasteful to redo on every single frame.
local _RUN_ONCE_DONE = {}
local function studio_run_once(id, fn)
    if _RUN_ONCE_DONE[id] then return end
    _RUN_ONCE_DONE[id] = true
    fn()
end

-- A `require`-like module registry that works inside one already-loaded
-- Lua chunk -- real `require` of a second file isn't something a
-- distributable plugin can rely on, since Conky's Lua doesn't promise a
-- writable/predictable package.path. A 'module' run_mode Custom Lua node
-- calls studio_define(name, value_or_factory_fn) once at load time; any
-- number of ordinary 'draw' Custom Lua nodes then call studio_use(name)
-- to pull in that shared table of functions, instead of pasting the same
-- helper code into every node's box. If value is a function, it's called
-- once (with no args) and its return value is what gets stored/returned
-- -- pass a table directly instead if you don't need setup logic.
local _MODULES = {}
local function studio_define(name, value)
    if _MODULES[name] ~= nil then
        print("[conky-studio] plugin warning: module '" .. tostring(name) ..
              "' defined more than once -- the later definition wins. " ..
              "Check for a duplicate 'module' node or a stray load_order tie.")
    end
    if type(value) == "function" then
        _MODULES[name] = value()
    else
        _MODULES[name] = value
    end
    return _MODULES[name]
end

local function studio_has_module(name)
    return _MODULES[name] ~= nil
end

local function studio_use(name)
    local m = _MODULES[name]
    if m == nil then
        error("[conky-studio] plugin error: module '" .. tostring(name) ..
              "' was never defined. Make sure its 'module' node exists, is " ..
              "part of this project, and (if load order matters) has a lower " ..
              "load_order than whatever is calling studio_use() here.", 0)
    end
    return m
end

-- Runs fn(...) protected by pcall, throttling repeated error prints for
-- the same label to once per _ERROR_THROTTLE_SECS instead of once a
-- frame -- a broken plugin node fails loudly once, not forever. This is
-- what the generated per-node DRAW_ORDER loop uses (see lua_gen.py) so
-- one node's runtime error only skips that node's output for the frame,
-- not the whole HUD; it's exported here too so a Custom Lua node's own
-- code can wrap a risky sub-call (a shelled-out command, an optional
-- module) the same way. Returns the pcall's ok boolean.
local _ERROR_LAST_PRINTED = {}
local _ERROR_THROTTLE_SECS = 30
local function studio_safe_call(label, fn, ...)
    local ok, err = pcall(fn, ...)
    if not ok then
        local now = wall_clock()
        local last = _ERROR_LAST_PRINTED[label]
        if last == nil or (now - last) >= _ERROR_THROTTLE_SECS then
            _ERROR_LAST_PRINTED[label] = now
            print("[conky-studio] '" .. tostring(label) .. "' error: " .. tostring(err))
        end
    end
    return ok
end

-- ---------------------------------------------------------------------
--  Colour utilities
-- ---------------------------------------------------------------------
local function studio_heat_rgb(t)
    t = clamp(tonumber(t) or 0, 0, 1)
    if t < 0.5 then
        local u = t * 2
        return lerp(0.31, 0.96, u), lerp(0.82, 0.84, u), lerp(0.77, 0.25, u)
    end
    local u = (t - 0.5) * 2
    return lerp(0.96, 0.88, u), lerp(0.84, 0.25, u), lerp(0.25, 0.25, u)
end

-- Cool → warm cyan/magenta palette (good for modern HUDs)
local function studio_cool_warm_rgb(t)
    t = clamp(tonumber(t) or 0, 0, 1)
    return lerp(0.2, 0.95, t), lerp(0.75, 0.35, t), lerp(0.9, 0.55, t)
end

-- Fire palette
local function studio_fire_rgb(t)
    t = clamp(tonumber(t) or 0, 0, 1)
    if t < 0.33 then
        local u = t / 0.33
        return lerp(0.05, 0.9, u), lerp(0.02, 0.25, u), lerp(0.0, 0.05, u)
    elseif t < 0.66 then
        local u = (t - 0.33) / 0.33
        return lerp(0.9, 1.0, u), lerp(0.25, 0.75, u), lerp(0.05, 0.15, u)
    end
    local u = (t - 0.66) / 0.34
    return 1.0, lerp(0.75, 1.0, u), lerp(0.15, 0.85, u)
end

local function hsl_to_rgb(h, s, l)
    h = (h % 360) / 360
    s = clamp(s, 0, 1)
    l = clamp(l, 0, 1)
    if s == 0 then return l, l, l end
    local function hue2rgb(p, q, t)
        if t < 0 then t = t + 1 end
        if t > 1 then t = t - 1 end
        if t < 1/6 then return p + (q - p) * 6 * t end
        if t < 1/2 then return q end
        if t < 2/3 then return p + (q - p) * (2/3 - t) * 6 end
        return p
    end
    local q = l < 0.5 and l * (1 + s) or l + s - l * s
    local p = 2 * l - q
    return hue2rgb(p, q, h + 1/3), hue2rgb(p, q, h), hue2rgb(p, q, h - 1/3)
end

local function rgb_to_hsl(r, g, b)
    local maxc = math.max(r, g, b)
    local minc = math.min(r, g, b)
    local l = (maxc + minc) / 2
    if maxc == minc then return 0, 0, l end
    local d = maxc - minc
    local s = l > 0.5 and d / (2 - maxc - minc) or d / (maxc + minc)
    local h
    if maxc == r then
        h = (g - b) / d + (g < b and 6 or 0)
    elseif maxc == g then
        h = (b - r) / d + 2
    else
        h = (r - g) / d + 4
    end
    return h * 60, s, l
end

local function lerp_rgb(r0, g0, b0, r1, g1, b1, t)
    t = clamp(t, 0, 1)
    return lerp(r0, r1, t), lerp(g0, g1, t), lerp(b0, b1, t)
end

local function desaturate(r, g, b, amount)
    amount = clamp(amount or 1, 0, 1)
    local gray = 0.299 * r + 0.587 * g + 0.114 * b
    return lerp(r, gray, amount), lerp(g, gray, amount), lerp(b, gray, amount)
end

-- ---------------------------------------------------------------------
--  Text helpers
-- ---------------------------------------------------------------------
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
    if opts.outline and opts.outline > 0 then
        cairo_set_source_rgba(cr, 0, 0, 0, a * 0.7)
        cairo_set_line_width(cr, opts.outline)
        cairo_move_to(cr, tx, ty)
        cairo_text_path(cr, text)
        cairo_stroke_preserve(cr)
    end
    cairo_set_source_rgba(cr, r, g, b, a)
    cairo_move_to(cr, tx, ty)
    cairo_show_text(cr, text)
end

-- Returns width, height of text (ascent+descent)
local function studio_measure_text(cr, text, opts)
    opts = opts or {}
    local family = opts.family or "Sans"
    local size = opts.size or 12
    local slant = (opts.italic and CAIRO_FONT_SLANT_ITALIC) or CAIRO_FONT_SLANT_NORMAL
    local weight = (opts.bold and CAIRO_FONT_WEIGHT_BOLD) or CAIRO_FONT_WEIGHT_NORMAL
    cairo_select_font_face(cr, family, slant, weight)
    cairo_set_font_size(cr, size)
    local ext = cairo_text_extents_t:create()
    tolua.takeownership(ext)
    cairo_text_extents(cr, tostring(text or ""), ext)
    local fe = cairo_font_extents_t:create()
    tolua.takeownership(fe)
    cairo_font_extents(cr, fe)
    return ext.width, fe.height
end

-- Word-wrapped multi-line text. Returns total height used.
local function studio_draw_text_wrapped(cr, text, x, y, max_width, opts)
    opts = opts or {}
    local family = opts.family or "Sans"
    local size = opts.size or 12
    local line_height = opts.line_height or (size * 1.25)
    local r, g, b, a = opts.r or 1, opts.g or 1, opts.b or 1, opts.a or 1
    local align = opts.align or "left"
    text = tostring(text or "")

    cairo_select_font_face(cr, family,
        (opts.italic and CAIRO_FONT_SLANT_ITALIC) or CAIRO_FONT_SLANT_NORMAL,
        (opts.bold and CAIRO_FONT_WEIGHT_BOLD) or CAIRO_FONT_WEIGHT_NORMAL)
    cairo_set_font_size(cr, size)

    local words = {}
    for w in text:gmatch("%S+") do words[#words + 1] = w end
    local lines = {}
    local cur = ""
    for i, w in ipairs(words) do
        local test = (cur == "") and w or (cur .. " " .. w)
        local ext = cairo_text_extents_t:create()
        tolua.takeownership(ext)
        cairo_text_extents(cr, test, ext)
        if ext.width > max_width and cur ~= "" then
            lines[#lines + 1] = cur
            cur = w
        else
            cur = test
        end
    end
    if cur ~= "" then lines[#lines + 1] = cur end

    for i, line in ipairs(lines) do
        studio_draw_text(cr, line, x, y + (i - 1) * line_height, {
            family = family, size = size, r = r, g = g, b = b, a = a,
            align = align, bold = opts.bold, italic = opts.italic, halo = opts.halo
        })
    end
    return #lines * line_height
end

-- Soft pill / badge behind text
local function studio_draw_pill(cr, text, x, y, opts)
    opts = opts or {}
    local pad_x = opts.pad_x or 10
    local pad_y = opts.pad_y or 4
    local radius = opts.radius or 999
    local tw, th = studio_measure_text(cr, text, opts)
    local bx = x - pad_x
    local by = y - th * 0.75 - pad_y
    local bw = tw + pad_x * 2
    local bh = th + pad_y * 2
    if opts.align == "center" then bx = x - bw / 2 end
    if opts.align == "right" then bx = x - bw end

    rounded_rect(cr, bx, by, bw, bh, radius)
    cairo_set_source_rgba(cr, opts.bg_r or 0.1, opts.bg_g or 0.12, opts.bg_b or 0.16, opts.bg_a or 0.85)
    cairo_fill(cr)
    studio_draw_text(cr, text, x, y, opts)
    return bw, bh
end

-- ---------------------------------------------------------------------
--  Path helpers
-- ---------------------------------------------------------------------
local function regular_polygon_path(cr, cx, cy, radius, sides, rotation_deg)
    sides = math.max(3, math.floor(sides or 6))
    local rot = math.rad(rotation_deg or -90)
    cairo_new_sub_path(cr)
    for i = 0, sides - 1 do
        local a = rot + i * (2 * math.pi / sides)
        local px = cx + math.cos(a) * radius
        local py = cy + math.sin(a) * radius
        if i == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
    end
    cairo_close_path(cr)
end

local function star_path(cr, cx, cy, outer_r, inner_r, points, rotation_deg)
    points = math.max(3, math.floor(points or 5))
    local rot = math.rad(rotation_deg or -90)
    cairo_new_sub_path(cr)
    for i = 0, points * 2 - 1 do
        local r = (i % 2 == 0) and outer_r or inner_r
        local a = rot + i * (math.pi / points)
        local px = cx + math.cos(a) * r
        local py = cy + math.sin(a) * r
        if i == 0 then cairo_move_to(cr, px, py) else cairo_line_to(cr, px, py) end
    end
    cairo_close_path(cr)
end

local function dashed_line(cr, x1, y1, x2, y2, dash, gap)
    dash = dash or 6
    gap = gap or 4
    local dx, dy = x2 - x1, y2 - y1
    local len = math.sqrt(dx * dx + dy * dy)
    if len < 1e-6 then return end
    local ux, uy = dx / len, dy / len
    local pos = 0
    local drawing = true
    while pos < len do
        local seg = drawing and dash or gap
        local next_pos = math.min(pos + seg, len)
        if drawing then
            cairo_move_to(cr, x1 + ux * pos, y1 + uy * pos)
            cairo_line_to(cr, x1 + ux * next_pos, y1 + uy * next_pos)
            cairo_stroke(cr)
        end
        pos = next_pos
        drawing = not drawing
    end
end

local function arrow_path(cr, x1, y1, x2, y2, head_len, head_angle_deg)
    head_len = head_len or 10
    head_angle_deg = head_angle_deg or 25
    local angle = math.atan2(y2 - y1, x2 - x1)
    local ha = math.rad(head_angle_deg)
    cairo_move_to(cr, x1, y1)
    cairo_line_to(cr, x2, y2)
    cairo_line_to(cr, x2 - head_len * math.cos(angle - ha), y2 - head_len * math.sin(angle - ha))
    cairo_move_to(cr, x2, y2)
    cairo_line_to(cr, x2 - head_len * math.cos(angle + ha), y2 - head_len * math.sin(angle + ha))
end

-- Soft multi-layer glow (call before filling a shape)
local function studio_glow(cr, r, g, b, a, layers)
    layers = layers or 3
    for i = layers, 1, -1 do
        local spread = i * 1.8
        cairo_set_source_rgba(cr, r, g, b, (a or 1) * (0.18 / i))
        cairo_set_line_width(cr, spread)
        cairo_stroke_preserve(cr)
    end
end

local function soft_shadow_rect(cr, x, y, w, h, radius, blur, alpha)
    blur = blur or 8
    alpha = alpha or 0.35
    for i = blur, 1, -1 do
        local o = i / blur
        rounded_rect(cr, x - i * 0.4, y + i * 0.6, w + i * 0.8, h + i * 0.4, radius + i * 0.3)
        cairo_set_source_rgba(cr, 0, 0, 0, alpha * (1 - o) * 0.4)
        cairo_fill(cr)
    end
end

-- ---------------------------------------------------------------------
--  Noise (fast value noise + fbm)
-- ---------------------------------------------------------------------
local function _hash2(x, y)
    local n = math.sin(x * 127.1 + y * 311.7) * 43758.5453
    return fract(n)
end

local function value_noise(x, y)
    local x0, y0 = math.floor(x), math.floor(y)
    local fx, fy = fract(x), fract(y)
    local ux = fx * fx * (3 - 2 * fx)
    local uy = fy * fy * (3 - 2 * fy)
    local a = _hash2(x0, y0)
    local b = _hash2(x0 + 1, y0)
    local c = _hash2(x0, y0 + 1)
    local d = _hash2(x0 + 1, y0 + 1)
    return lerp(lerp(a, b, ux), lerp(c, d, ux), uy)
end

local function fbm(x, y, octaves)
    octaves = octaves or 4
    local v, amp, freq = 0, 0.5, 1
    for i = 1, octaves do
        v = v + amp * value_noise(x * freq, y * freq)
        amp = amp * 0.5
        freq = freq * 2
    end
    return v
end

-- ---------------------------------------------------------------------
--  Transform helpers
-- ---------------------------------------------------------------------
local function with_transform(cr, fn)
    cairo_save(cr)
    local ok, err = pcall(fn)
    cairo_restore(cr)
    if not ok then error(err) end
end

local function with_clip_rect(cr, x, y, w, h, fn)
    cairo_save(cr)
    cairo_rectangle(cr, x, y, w, h)
    cairo_clip(cr)
    local ok, err = pcall(fn)
    cairo_restore(cr)
    if not ok then error(err) end
end

-- ---------------------------------------------------------------------
--  Time formatting helpers
-- ---------------------------------------------------------------------
local function format_seconds(sec)
    sec = math.floor(tonumber(sec) or 0)
    local h = math.floor(sec / 3600)
    local m = math.floor((sec % 3600) / 60)
    local s = sec % 60
    if h > 0 then
        return string.format("%d:%02d:%02d", h, m, s)
    end
    return string.format("%d:%02d", m, s)
end

local function format_bytes(n)
    n = tonumber(n) or 0
    if n < 1024 then return string.format("%.0f B", n) end
    if n < 1048576 then return string.format("%.1f KiB", n / 1024) end
    if n < 1073741824 then return string.format("%.1f MiB", n / 1048576) end
    return string.format("%.2f GiB", n / 1073741824)
end

'''.lstrip("\n")

