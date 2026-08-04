-- ---------------------------------------------------------------------
--  Studio extensions: state helpers, text block, heat colour
--  (splice into FRAMEWORK_LUA in lua_framework.py)
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
