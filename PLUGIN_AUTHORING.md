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
      "homepage": "",
      "license": "",
      "properties": [
        {
          "key": "value",
          "label": "Value",
          "kind": "float",
          "default": 50,
          "minimum": 0,
          "maximum": 100,
          "step": 1,
          "bindable": true,
          "accepts": ["number", "percent"],
          "group": "Input",
          "help": "Value to clamp"
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
      "lua_draw_body": "local r, g, b = {color}\nplugin_dot_fill(cr, r, g, b, 1)\ncairo_arc(cr, {x}, {y}, {radius}, 0, 2 * math.pi)\ncairo_fill(cr)\n"
    }
  ]
}
```

`api_version` `"1.1"` adds optional fields (`tags`, `lua_helpers`, `simple_mode`,
`homepage`, `license`) and stays backward-compatible with `"1.0"` manifests.

## Rules

| Rule | Detail |
|------|--------|
| **id** | Must match `^(logic\|visual)(\.[a-z][a-z0-9_]*)+$` — starts with `logic.` or `visual.`, then one or more `.segment`s; each segment starts with a letter; only `a-z`, `0-9`, `_`. Examples: `logic.clamp`, `visual.plugin.dot`. Rejected: `logic.Clamp`, `visual.dot-1`, `plugin.foo` |
| **category** | `logic` or `visual` only (no `source` / `canvas` — those need real polling or fixed window semantics) |
| **logic** | Requires `output_kind` **and** `lua_expr` (a **single expression**, not statements) |
| **visual** | Requires `lua_draw_body` (statements that draw with `cr`; `W` / `H` are in scope as bare names) |
| **output_kind** | One of: `percent`, `celsius`, `number`, `text`, `category`, `boolean` |
| **placeholders** | `{property_key}` only. Every `{name}` in `lua_expr`, `lua_draw_body`, or `lua_helpers` must be a declared property key — unknown keys are a **hard validation error**, not a warning |
| **cr / W / H** | Use as **Lua identifiers**, not placeholders. Write `cr`, `W`, `H` — never `{W}` or `{H}`. (`{cr}` is specially allowed by the validator but unnecessary; prefer bare `cr`) |
| **color kind** | Substitutes as `r, g, b` number literals for Cairo (e.g. `0.31, 0.82, 0.77`), **not** a hex string |
| **lua_helpers** | Optional shared functions; substituted then emitted **once per plugin type** in a build |
| **property keys** | Must match `^[a-z][a-z0-9_]*$`; unique within the node |
| **ids unique** | Duplicate `id` in the same manifest fails validation; colliding with a built-in or already-loaded plugin fails on register |

## Property kinds

`float` · `int` · `bool` · `color` · `string` · `enum` · `font` · `path` · `code`

| Kind notes | |
|------------|--|
| **enum** | Requires non-empty `choices` (optional `choice_labels`) |
| **float / int** | Optional `minimum`, `maximum`, `step` |
| **bindable** | Set `bindable: true` and usually `accepts: ["number", "percent", …]` so wires can feed the property |
| **help** | Optional string shown in the property panel |
| **group** | Optional UI grouping label (default `"General"`) |

## Optional node fields (1.1)

| Field | Purpose |
|-------|---------|
| `tags` | List of short strings (palette / search hints) |
| `simple_mode` | If `true`, also listed in a simpler palette view |
| `homepage` | URL for the pack or author |
| `license` | Short license label |
| `subcategory` | Palette section (default `"Plugins"`) |
| `color` | Node header tint in the graph (hex) |

## Where to put packs

1. **Remote** — PR against the project’s `plugins.json` (default fetch URL points at the main-branch manifest)
2. **Local** — drop any `*.json` under `~/.config/conky-studio/plugins/` (loaded on startup)

Remote fetches may also be cached under that directory so offline reloads still work after a successful download.

## Validate without registering

```python
from conkystudio.plugins.loader import load_manifest_file, validate_only

m = load_manifest_file("my-pack.json")
errors = validate_only(m)  # empty list = OK
print(errors)
```

`validate_only` skips the “already registered in this session” check so you can
CI-check a pack that collides with built-ins only at install time.

## Edge cases authors hit

| Situation | What happens |
|-----------|----------------|
| `{value}` in template but no property `value` | Validation error |
| `{W}` or `{H}` in `lua_draw_body` | Validation error — use bare `W` / `H` |
| Logic `lua_expr` with multiple statements | Not supported; keep a single expression |
| Color default `"#4fd1c5"` in template as `{color}` | Becomes `r, g, b` literals, e.g. suitable for `cairo_set_source_rgb(cr, {color})` or `local r,g,b = {color}` |
| Same `id` as a built-in (e.g. if core later adds `logic.clamp`) | Register fails if that type is already in the registry |
| Pack loaded twice (remote + local copy) | Second load is skipped for already-loaded ids |
| Property key `Value` or `my-value` | Rejected — must be `value` / `my_value` style |
| Empty `lua_draw_body` / `lua_expr` | Rejected for visual / logic respectively |

## Trust model

Plugin Lua is not sandboxed beyond Conky itself (`io.popen` / `os.execute` exist).
Only load packs you trust.
