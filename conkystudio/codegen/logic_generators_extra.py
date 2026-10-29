"""
Logic generators for logic_extra.py nodes.

Call register(logic_generator) after lua_gen defines the decorator, e.g. at
the end of lua_gen.py:

    from conkystudio.codegen.logic_generators_extra import register as _reg_logic_extra
    _reg_logic_extra(logic_generator)

Or from extensions_bootstrap after importing lua_gen.
"""
from __future__ import annotations


def register(logic_generator):
    """Register all extra logic generators onto the given decorator."""

    # Imported here so this module can load before lua_gen finishes.
    from conkystudio.codegen.lua_gen import lua_string_literal, lua_literal

    @logic_generator("logic.smooth")
    def _logic_smooth(node, ctx):
        value = ctx.resolve(node, "value")
        alpha = float(node.props.get("alpha", 0.15) or 0.15)
        alpha = max(0.01, min(1.0, alpha))
        init = bool(node.props.get("init_from_input", True))
        key = lua_string_literal(node.id)
        if init:
            return (
                f"(function() "
                f"local key = {key}; local cur = tonumber({value}) or 0; "
                f"local prev = STATE[key]; "
                f"if prev == nil then STATE[key] = cur; return cur end; "
                f"local out = prev + ({alpha}) * (cur - prev); "
                f"STATE[key] = out; return out; end)()"
            )
        return (
            f"(function() "
            f"local key = {key}; local cur = tonumber({value}) or 0; "
            f"local prev = STATE[key] or 0; "
            f"local out = prev + ({alpha}) * (cur - prev); "
            f"STATE[key] = out; return out; end)()"
        )

    @logic_generator("logic.rate_of_change")
    def _logic_rate_of_change(node, ctx):
        value = ctx.resolve(node, "value")
        samples = max(1, int(node.props.get("samples", 4) or 4))
        key = lua_string_literal(node.id)
        return (
            f"(function() "
            f"local key = {key}; local cur = tonumber({value}) or 0; "
            f"local buf = STATE[key]; "
            f"if type(buf) ~= 'table' then buf = {{}}; STATE[key] = buf end; "
            f"table.insert(buf, cur); "
            f"while #buf > ({samples} + 1) do table.remove(buf, 1) end; "
            f"if #buf <= {samples} then return 0 end; "
            f"return cur - (buf[1] or cur); end)()"
        )

    @logic_generator("logic.hysteresis")
    def _logic_hysteresis(node, ctx):
        value = ctx.resolve(node, "value")
        high = float(node.props.get("high", 85.0) or 85.0)
        low = float(node.props.get("low", 75.0) or 75.0)
        if low > high:
            low, high = high, low
        on_v = float(node.props.get("on_value", 1.0) or 1.0)
        off_v = float(node.props.get("off_value", 0.0) or 0.0)
        key = lua_string_literal(node.id)
        return (
            f"(function() "
            f"local key = {key}; local v = tonumber({value}) or 0; "
            f"local on = STATE[key]; "
            f"if on == nil then on = false end; "
            f"if on then if v < ({low}) then on = false end "
            f"else if v >= ({high}) then on = true end end; "
            f"STATE[key] = on; "
            f"return on and ({on_v}) or ({off_v}); end)()"
        )

    @logic_generator("logic.string_join")
    def _logic_string_join(node, ctx):
        a = ctx.resolve(node, "input_a")
        b = ctx.resolve(node, "input_b")
        sep = lua_string_literal(str(node.props.get("separator", " ") or " "))
        skip = bool(node.props.get("skip_empty", True))
        if skip:
            return (
                f"(function() "
                f"local a = tostring({a} or ''); local b = tostring({b} or ''); "
                f"if a == '' then return b end; if b == '' then return a end; "
                f"return a .. {sep} .. b; end)()"
            )
        return f"(tostring({a} or '') .. {sep} .. tostring({b} or ''))"

    @logic_generator("logic.enum_map")
    def _logic_enum_map(node, ctx):
        inp = ctx.resolve(node, "input")
        keys_raw = str(node.props.get("keys", "clear,cloud,rain") or "")
        vals_raw = str(node.props.get("values", "0,1,2") or "")
        default = float(node.props.get("default_value", -1.0) or -1.0)
        keys = [k.strip().lower() for k in keys_raw.split(",") if k.strip()]
        vals = []
        for v in vals_raw.split(","):
            v = v.strip()
            try:
                vals.append(float(v))
            except ValueError:
                vals.append(0.0)
        while len(vals) < len(keys):
            vals.append(0.0)
        pairs = ", ".join(
            f"[{lua_string_literal(k)}] = {lua_literal(vals[i])}"
            for i, k in enumerate(keys)
        )
        return (
            f"(function() "
            f"local map = {{{pairs}}}; "
            f"local s = string.lower(tostring({inp} or '')); "
            f"local n = map[s]; "
            f"if n ~= nil then return n end; "
            f"return {lua_literal(default)}; end)()"
        )
