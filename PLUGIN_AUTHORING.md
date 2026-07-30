# Authoring Conky Studio plugins

Plugins are **data only**: JSON metadata + Lua templates. No Python is executed
from a plugin pack. Lua runs inside Conky at preview/build time — treat packs
like any theme you download.

## Manifest shape

```json
{
  "api_version": "1.1",
  "updated_at": "2026-07-30",
  "plugins": [
    {
      "id": "logic.clamp",
      "category": "logic",
      "label": "Clamp",
      "author": "you",
      "version": "1.0.0",
      "description": "Clamp a number between min and max",
      "color": "#5f8fd6",
      "subcategory": "Plugins",
      "output_kind": "number",
      "tags": ["math"],
      "simple_mode": false,
      "properties": [
        {
          "key": "value",
          "label": "Value",
          "kind": "float",
          "default": 50,
          "minimum": 0,
          "maximum": 100,
          "bindable": true,
          "accepts": ["number", "percent"],
          "group": "Input"
        },
        {
          "key": "lo",
          "label": "Min",
          "kind": "float",
          "default": 0,
          "group": "Range"
        },
        {
          "key": "hi",
          "label": "Max",
          "kind": "float",
          "default": 100,
          "group": "Range"
        }
      ],
      "lua_expr": "math.min({hi}, math.max({lo}, {value}))"
    },
    {
      "id": "visual.plugin.dot",
      "category": "visual",
      "label": "Dot",
      "author": "you",
      "lua_helpers": "local function plugin_dot_fill(cr, r, g, b, a)\n  cairo_set_source_rgba(cr, r, g, b, a)\nend\n",
      "properties": [
        { "key": "x", "label": "X", "kind": "float", "default": 40 },
        { "key": "y", "label": "Y", "kind": "float", "default": 40 },
        { "key": "radius", "label": "Radius", "kind": "float", "default": 8, "minimum": 1, "maximum": 200 },
        { "key": "color", "label": "Colour", "kind": "color", "default": "#4fd1c5" }
      ],
      "lua_draw_body": "  local r, g, b = {color}\n  plugin_dot_fill(cr, r, g, b, 1)\n  cairo_arc(cr, {x}, {y}, {radius}, 0, 2 * math.pi)\n  cairo_fill(cr)\n"
    }
  ]
}
```

## Rules

| Rule | Detail |
|------|--------|
| **id** | `logic.*` or `visual.*`, lowercase, digits, underscores |
| **category** | `logic` or `visual` only (no source/canvas) |
| **logic** | needs `output_kind` + `lua_expr` (single expression) |
| **visual** | needs `lua_draw_body` (statements using `cr`, `W`, `H`) |
| **placeholders** | `{property_key}` only — every `{name}` in templates must be a declared property |
| **color kind** | substitutes as `r, g, b` numbers for Cairo, not a hex string |
| **lua_helpers** | optional shared functions; emitted once per plugin type in a build |

## Property kinds

`float` · `int` · `bool` · `color` · `string` · `enum` · `font` · `path` · `code`

`enum` requires `choices` (and optional `choice_labels`).

## Where to put packs

1. **Remote** — PR against the project’s `plugins.json`
2. **Local** — `~/.config/conky-studio/plugins/my-pack.json` (loaded on startup)

## Validate without registering

```python
from conkystudio.plugins.loader import load_manifest_file, validate_only
m = load_manifest_file("my-pack.json")
print(validate_only(m))  # empty list = OK
```

## Trust model

Plugin Lua is not sandboxed beyond Conky itself (`io.popen` / `os.execute` exist).
Only load packs you trust.
