"""
The static portion of every generated render.lua. This is plain text,
not a Jinja/format template -- it never varies between projects, so it's
just spliced in verbatim by lua_gen.build_render_lua(). Only the
generated sections below it (constants, refresh_sources, per-node draw
functions, main_draw_impl) differ per project.

Where a pattern below traces back to one of your existing themes, the
comment says so -- this is meant to read as "the validated parts of your
own code, generalized," not a rewrite from scratch.
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

-- Safe wrappers around conky_parse for native ${...} variables (CPU%,
-- RAM%, net speed, uptime, ...). Verbatim pattern from batcomputer.lua's
-- safe_parse/safe_number: a bad or momentarily-unavailable expression
-- returns the previous value instead of crashing the draw call.
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

-- Reads a flat `key=value` cache file written by a daemon-mode polling
-- script (sensors.sh / weather.sh's atomic tmp-file-then-mv pattern).
-- Missing file (script hasn't run yet, or daemon mode not in use for
-- this project) just yields an empty table rather than an error.
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

-- Runtime network-interface auto-detection -- the first "up" interface
-- found under /sys/class/net, falling back to the first non-loopback
-- one if none report "up" yet. Same approach as batcomputer.lua's
-- resolve_net_iface(), run once and cached for the life of the process
-- so switching Wi-Fi/Ethernet later doesn't require a rebuild.
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
--  Drawing surface. conky_surface() is the current, backend-agnostic
--  accessor (works on both X11 and Wayland-with-layer-shell builds) and
--  is a surface Conky owns -- it must NOT be destroyed here. Older Conky
--  builds don't have conky_surface() yet and only expose the deprecated
--  conky_window.display/drawable/visual triplet, which this falls back
--  to; that surface WAS created by us, so it must be destroyed. Getting
--  the ownership direction wrong in either branch is exactly what caused
--  a segfault in an earlier version of this pattern.
-- ---------------------------------------------------------------------
local function get_draw_surface()
    if conky_window == nil then return nil end
    local ww, wh = conky_window.width, conky_window.height
    if ww == nil or wh == nil or ww == 0 or wh == 0 then return nil end

    if conky_surface ~= nil then
        local cs = conky_surface()
        if cs == nil then return nil end
        return cs, ww, wh, false  -- false = conky owns this surface, don't destroy it
    end

    if conky_window.display == nil then return nil end
    local cs = cairo_xlib_surface_create(conky_window.display, conky_window.drawable, conky_window.visual, ww, wh)
    return cs, ww, wh, true  -- true = we created it, we must destroy it
end

local function rounded_rect(cr, x, y, w, h, r)
    r = math.min(r, w / 2, h / 2)
    cairo_new_sub_path(cr)
    cairo_arc(cr, x + w - r, y + r,     r, -math.pi / 2, 0)
    cairo_arc(cr, x + w - r, y + h - r, r, 0, math.pi / 2)
    cairo_arc(cr, x + r,     y + h - r, r, math.pi / 2, math.pi)
    cairo_arc(cr, x + r,     y + r,     r, math.pi, 3 * math.pi / 2)
    cairo_close_path(cr)
end

-- ---------------------------------------------------------------------
--  Image loading -- PNG via Cairo directly, SVG via the RSVG binding
--  (see BunsenLabs/conky-wiki draw_svg_file pattern), unified behind one
--  cached loader so Image/Icon draw code doesn't care which it got.
--  Cache uses `false` as an explicit "known missing, don't retry" marker
--  (batcomputer.lua's load_image_cached pattern) so a bad path only
--  prints its warning once instead of every frame.
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

-- Draws an already-loaded image (see load_image_cached) fit inside a
-- size x size box, aspect-correct, centered, with optional rotation
-- (degrees, clockwise) and opacity.
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

-- The slanted-trapezoid bar skin, geometry lifted directly from the
-- Skyrim theme's bar_shape_path() (measured from Tiny_Bar_2.png: full
-- width at the top edge, tapering inward toward the bottom).
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

-- ---------------------------------------------------------------------
--  Battery presence check -- swept under one helper so a source node
--  bound to a desktop with no battery just reads as "unavailable"
--  rather than a fake 0%/100%.
-- ---------------------------------------------------------------------
local function battery_exists(device)
    local f = io.open('/sys/class/power_supply/' .. (device or 'BAT0') .. '/capacity', 'r')
    if f then f:close(); return true end
    return false
end

-- Hour-of-day greeting, computed natively instead of a bash lookup table
-- like greeting.sh's -- same four buckets, no external process per frame.
local function greeting_for_hour(h)
    if h == nil then return 'Hello' end
    if h >= 5 and h < 12 then return 'Good Morning' end
    if h >= 12 and h < 17 then return 'Good Afternoon' end
    if h >= 17 and h < 22 then return 'Good Evening' end
    return 'Good Night'
end

-- Conky's bundled Lua is 5.1, which has no utf8 library (that's a 5.3+
-- addition) -- this is a minimal, standard UTF-8 encoder for turning an
-- icon font's codepoint (e.g. 0xE922) into the actual character bytes.
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

-- Album Art (and anything else backed by a background-fetched file at a
-- FIXED path whose CONTENT changes) needs different caching than
-- load_image_cached: that one caches forever by path, which is correct
-- for a static build-time asset but wrong here, since the same path gets
-- new bytes every track change. This reloads at most once per call, and
-- callers gate calls to the stats-refresh cadence rather than every
-- frame -- see the generated draw_node_* for visual.album_art.
local _PERIODIC_IMAGE_STATE = {}
local function load_image_periodic(path, state_key)
    local prev = _PERIODIC_IMAGE_STATE[state_key]
    local mtime = nil
    local f = io.open(path, 'rb')
    if f then f:close() end
    -- Reuse the cached surface unless the file's mtime moved on --
    -- cheaper than decoding the PNG again every refresh tick when the
    -- track (and therefore the art) hasn't actually changed.
    local stat = io.popen and io.popen("stat -c %Y '" .. path .. "' 2>/dev/null")
    if stat then
        mtime = stat:read('*l')
        stat:close()
    end
    if prev and prev.mtime == mtime and prev.entry then
        return prev.entry
    end
    if IMAGE_CACHE[path] ~= nil then
        IMAGE_CACHE[path] = nil  -- force load_image_cached to actually re-read this time
    end
    local entry = load_image_cached(path)
    _PERIODIC_IMAGE_STATE[state_key] = { mtime = mtime, entry = entry }
    return entry
end

'''.lstrip("\n")
