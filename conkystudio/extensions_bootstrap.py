"""
v1.0.6 extensions bootstrap — import once at app startup so nodes and
generators are live (not dead code).

Imported by conkystudio/nodes/__init__.py:

    import conkystudio.extensions_bootstrap  # noqa: F401

What this does:
  1. Registers NodeSpecs (logic_extra, visuals_extra, visuals_more, sources_extra)
  2. Registers Lua generators onto lua_gen's decorator tables
"""
from __future__ import annotations

# 1) Node specs (register() side effect)
try:
    import conkystudio.nodes.logic_extra  # noqa: F401
except ImportError as e:
    print(f"[conky-studio] logic_extra: {e}")
try:
    import conkystudio.nodes.visuals_extra  # noqa: F401
except ImportError as e:
    print(f"[conky-studio] visuals_extra: {e}")
try:
    import conkystudio.nodes.visuals_more  # noqa: F401  (Needle Gauge / Segmented Ring / Equalizer Bars)
except ImportError as e:
    print(f"[conky-studio] visuals_more: {e}")
try:
    import conkystudio.nodes.sources_extra  # noqa: F401
except ImportError as e:
    print(f"[conky-studio] sources_extra: {e}")

# 2) Generators (must run after lua_gen is importable)
try:
    from conkystudio.codegen import lua_gen
    from conkystudio.codegen.logic_generators_extra import register as reg_logic
    from conkystudio.codegen.visual_generators_extra import register as reg_visual
    from conkystudio.codegen.visual_generators_more import register as reg_visual_more
    reg_logic(lua_gen.logic_generator)
    reg_visual(lua_gen.visual_generator)
    reg_visual_more(lua_gen.visual_generator)
except Exception as e:
    print(f"[conky-studio] extension generators: {e}")
