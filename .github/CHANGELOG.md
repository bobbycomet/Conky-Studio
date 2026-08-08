# Changelog

## 1.0.7.5 — New Detection Feature (Latest)

**Added**
- Hardware & Session now detects your Linux distro (via `/etc/os-release`, including derivatives like Mint, Pop!_OS, Manjaro, Rocky, etc., through their `ID_LIKE` parent) and checks for two optional CLI tools: `lm-sensors` and `playerctl`.
- If either is missing, the report now shows a clear warning explaining what they're used for (hardware sensors for CPU/GPU/RAM/fan sources, and audio/now-playing sources) and gives the exact install command for your detected distro, so you're not left guessing the right package manager or package name.
- New `=== Optional tools ===` section in the Hardware & Session report showing your detected distro and the install status of both tools.

**Notes**
- This is purely informational; nothing is installed automatically, and the warning explicitly says to ignore it if you're not using CPU/GPU/RAM/fan or now-playing sources.
- Falls back with a generic "check your package manager" message if the distro can't be confidently identified.

## Version number

Forgot to change the version number, so you would run into update messages. (Fixed)

## Cleanup

Removed the 7 duplicate plugins

## 1.0.7.4 — Collision fix 

### The cause

v1.0.7.3

When I imported the missing extras, Lua_gen had no defense against the collision, so it went unnoticed at first glance, as everything looked correct.

### Fixed
- **Logic plugin ID collisions** with built-ins. Seven plugins reused flat `logic.*` type ids already claimed by core nodes, which could raise on register, silently no-op (`deadzone`), or overwrite codegen templates:
  - `logic.threshold` → `logic.plugin.threshold`
  - `logic.deadzone` → `logic.plugin.deadzone`
  - `logic.smooth` → `logic.plugin.smooth`
  - `logic.round` → `logic.plugin.round`
  - `logic.boolean_and` → `logic.plugin.boolean_and`
  - `logic.boolean_or` → `logic.plugin.boolean_or`
  - `logic.pick` → `logic.plugin.pick`
- **Codegen duplicate registration** — `_LOGIC_GENERATORS` / `_VISUAL_GENERATORS` now raise `ValueError` on a second registration of the same type instead of silently overwriting (matches the registry’s intent; plugins must use unique ids such as `logic.plugin.*` / `visual.plugin.*`).
 
### Added
- **`logic_generators_extra.py`** — Lua generators for the extra logic nodes (`smooth`, `rate_of_change`, `hysteresis`, `string_join`, `enum_map`) so they compile once those modules are imported.
- Local string/literal helpers in that module so it does not circular-import `lua_gen` during startup.

### Notes / required wiring
- Projects that still reference the old plugin type strings need a one-time retarget to the `logic.plugin.*` ids (or a loader migration). Just uninstall the plugin, exit the plugin window, refetch the list, and reinstall. This will fix the collision issues.
- Visual plugins were already namespaced as `visual.plugin.*`; no change there.

# 1.0.7.3 — Fix

Fixed missing node and extension imports in `/conky-studio/nodes/__init__.py`.

This resolves an issue where some built-in node groups and extension bootstrap modules were not being loaded correctly.

Added missing imports:

```python
from . import logic_extra       # noqa: F401
from . import sources_extra     # noqa: F401
from . import visuals_extra     # noqa: F401
from . import visuals_more      # noqa: F401
import conkystudio.extensions_bootstrap  # noqa: F401
```

# 1.0.7.2

**OCS/Pling /OpenDesktop installer Fix**
* When a downloaded theme has no `start.sh`, Conky Studio now writes a minimal one automatically.
* The generated script:
  * Changes into the theme directory
  * Makes `scripts/*.sh` and `*.sh` executable
  * Prefers `conky.conf`, then falls back to the first `*.conf` / `*.conkyrc`
  * Launches Conky with that config
* Install success message notes when a `start.sh` was added (`… (added a minimal start.sh)`).
* Themes that already ship with a `start.sh` are left unchanged.

# 1.0.7.1

**Patch release** — OpenDesktop/Pling Store fixes/Theme preview in the manager

#### Fixed
- **openDesktop search failed with HTTP 410**  
The provider base URL now points at the live endpoint `https://api.opendesktop.org/ocs/v1/`.

- **Pling search always showed “No results”**  
 Pling’s OCS JSON is flat (`data` is a list of content objects). The client only handled the classic nested shape (`data.content` / `data` as a dict), so every successful response was treated as empty. Parsing now accepts both formats.

- **Status / rate-limit handling on flat responses**  
  Top-level `statuscode` / `status` / `message` (Pling-style) are checked when a nested `meta` block is missing, so rate limits and API errors surface correctly in the UI.

- **Theme preview**
Fixed an issue that caused the theme preview to not show up because it searched *.png in all files, so if you had assets, it confused the manager which image to target. It now points directly to a preview.png.

#### Technical
- Updated `DEFAULT_PROVIDERS["opendesktop"]` in `store/ocs_client.py`
- Hardened `_data_list()` and `_parse_contents()` for list-shaped `data` payloads
- `categories()` relies on the shared status validation path instead of a separate empty-meta check

#### Notes
- Community Store (static `index.json`) is unchanged
- Install / `ocs://` handling is unchanged
- Verified live against Pling and `api.opendesktop.org` with search query `conky`

# 1.0.7

## Highlights

Conky Studio 1.0.7 improves compatibility with existing third-party Conky themes and adds new animated HUD components.

### Main improvements:
- Better ZIP/TAR theme importing
- Automatic launcher generation for compatible themes
- Improved Manager compatibility
- 7 new visual nodes
- More reliable third-party theme handling
- Theme compatibility and node reference wiki pages updated to reflect these changes

## Theme install & Manager compatibility

Archive drop in the Manager tab is more reliable for real-world third-party packs (zip and tar.gz), and missing launchers are handled without pretending a broken theme is fixed.

### Archive install (`installer.py`)

- **Auto-generate `start.sh`** when a dropped archive has a Conky config but no launcher. The generated script uses the same `setsid` + PID-file lock pattern as Studio-built themes, so Manager Start/Stop works.
- **Config detection** is no longer limited to `conky.conf`. Prefers `conky.conf`, then `<folder-name>.conf` (and common shortened names), then any top-level `*.conf`. Nested leftover packs can still resolve a conf one level down.
- **Nested archive layouts** (e.g., in my tests, `RidgeV2/RidgeV2/*.conf`) are unwrapped by peeling single-child directory chains until a real theme root is found (markers: `theme.json`, `conky.conf`, `start.sh`, or any `*.conf`).
- **`.tar.gz` / `.tgz` / `.tar`** are first-class alongside `.zip`, with case-insensitive type detection and correct theme-name stripping (`Foo.tar.gz` → folder `Foo`, not `Foo.tar`).
- **Background scripts:** generated launchers only start `scripts/*.sh`. Lua and other helpers are left for Conky (`lua_load` / `${execi}`) so files like `music-controls.lua` are never executed as shell.
- **Install feedback** always reports what happened: generated `start.sh` (and which conf), kept existing `start.sh`, or no conf found so no launcher was created.

### Manager UI (`manager_tab.py`)

- Drop area and browse dialog explicitly accept `.zip`, `.tar.gz`, `.tgz`, and `.tar`.
- Unsupported file types are reported clearly.
- Successful installs show an info dialog with the installer’s status message (including `start.sh` generation).

### Compatibility expectations (not bugs)

- A working or generated `start.sh` **only launches** the theme. It does not fix wrong paths, missing API keys, or broken configs.
- Themes still need their **system dependencies** (`jq`, `playerctl`, `xmlstarlet`, etc.) installed on the host.
- **Distro, session (X11 vs Wayland), DE, and compositor** affect window type, transparency, and layering. A theme tuned for KWin may misbehave under Cinnamon, GNOME, XFCE, or Hyprland; that is outside the installer.
- Lua is loaded by Conky via the config, not by `start.sh`.

---

## New visual nodes

| Node | Description |
|------|-------------|
| **`visual.spinning_fan`** | Drawn fan (curved Bézier blades + hub) that rotates; speed from a bound value. Pairs with the fan_sensors script family. Optional motion-blur ghost-blade pass so motion reads clearly even at slow Conky refresh rates. |
| **`visual.radar_chart`** | Polar/spider chart with up to 6 bound axes. Plots multiple series on one shape (e.g., CPU / RAM / GPU / Disk / Net/Temp as one polygon). |
| **`visual.radial_spectrum`** | Equalizer-style bars arranged in a ring. |
| **`visual.vinyl_spinner`** | Spinning record with grooves, label, spindle, and specular sheen. Freezes on a bound spin gate via STATE + delta-time (not naive `wall_clock() * rpm`), so pause does not jump angle. |
| **`visual.matrix_rain`** | Matrix-style falling code, fully procedural (time + index hashing; no per-frame random seed to manage). |
| **`visual.flip_digit`** | Split-flap/departure-board digit with fold-and-shrink animation on value change (`cairo_scale` + STATE tracking the previous value). |
| **`visual.loading_dots`** | Small bouncing-ellipsis loader. |

---

## Files touched (theme compatibility)

- `installer.py` — archive extraction, theme-root detection, conf discovery, minimal `start.sh` generation  
- `manager_tab.py` — drop/browse filters, install result dialogs  

Visual node registrations and generators ship with the Studio node registry/visual generator modules for this release.

---

# plugin.json fixes: no version change for Conky Studio

* Altimeter
* Altitude indicator
* Spinner
* Tick ring
* Hex tile
* Hex gauge
* Concentric pulse
* Value arc ticks
* Spark burst
* Soft shadow circle
* Speedometer

`cx`, `cy` (`Center x`, `Center y`) keys positioning fix

* Issue: It was defaulting to 0-100 due to an added `"` typo, likely from copy-paste when trying to do mass edits in the text editor
* Fix: Position now allows 1-4000

Rename for a typo for Altitude indicator, as a typo had it as Attitude indicator.

To get these fixes:

* Uninstall the plugins
* Reinstall them

---

## v1.0.6.2
### Fixed
- **`lua_gen.py` – `_gen_glow_pulse`**
  - Removed the entire first gating block (`if trig > 0 or {thresh} < 1000`). It was computed and then immediately discarded by the second block, making it pure dead code.
  - Removed the second block’s `edge_gated` heuristic (`math.abs(trig - 0.0) > 1e-6 or {thresh} ~= 80.0`). This incorrectly inferred whether the Trigger was wired by looking at the resolved value and how far the threshold sat from its default, so simply moving the `trigger_threshold` slider off `80.0` would silently gate an otherwise-unbound glow.
  - Replaced both with a single reliable `has_trigger` check computed in Python via `ctx.project.edge_for_prop(node.id, "trigger") is not None` (the same pattern already used by `_gen_image_icon`’s `swap_trigger` handling) and emit one straightforward Lua `if`/`else` based on that result.
- **`lua_gen.py` – `_gen_corner_brackets`**
  - Dropped the two duplicate `_bx`/`_by`/`_bw`/`_bh` lines that needlessly shadowed `x`/`y`/`w`/`h` with identical values. The fill box now uses `x, y, w, h` directly.

### Removed from plugins
- Seven logic plugins that were left behind after their functionality was integrated into the built-in node system:
  - `logic.threshold`
  - `logic.deadzone`
  - `logic.smooth`
  - `logic.round`
  - `logic.boolean_and`
  - `logic.boolean_or`
  - `logic.pick`

These were forgotten to be removed once the equivalent nodes became part of the core (`logic.py` / `logic_extra.py`). They have now been cleaned up.
Updated Plugin node reference in the wiki to match the removals.

---

## v1.0.6.1
### Navigation fix
**Plugins & palette organization**
- **Nodes palette:** Node types within each category and subcategory are listed in **alphabetical order** (A→Z by label), including installed plugins.
- **Tools → Plugins:**
  - Installed and catalogue lists are sorted **alphabetically by plugin name**.
  - **Category filter** (All/Logic/Visual/Source) on both Installed and Fetch lists so you can focus on one plugin type when installing or uninstalling.
- **Plugin loader:** `loaded_plugins()` returns entries sorted by label for consistent UI ordering.

## plugins.json
Added a total of 54 plugins; 33 are visual (Battery, Network bars, Digital clock, and more), quite a few are animated (Aurora veil, Bubbles, Embers, and more), and the rest are logic bridges.

---

## Version 1.0.6
### Added
- **Needle Gauge (`visual.needle_gauge`).**
Analog dial with ok/warn/danger zones, ticks, needle, and optional centre readout with `value_suffix` (e.g., `%`, ` RPM`, ` MHz`, `°C`). Bind any numeric source (percent, celsius, or plain number) the same way as Arc Gauge or Bar.
- **Moon Phase: blood moons and eclipse countdown.**
  Still draws synodic phase and illumination, and now also:
  - Approximates total lunar eclipses (blood moons) from a near-term JD table
  - Surfaces **BLOOD** / **Eclipse** timing when an event is close
  - Flags solar-eclipse seasons near new moon
  - Tags **N/S** on the extra line from `southern_hemisphere`
  **Eclipse schedule in the table:**
  - **2026-08-27/28** — deep partial lunar eclipse
  - **2028-12-31 / 2029-01-01** — next total (blood moon)
  - Further listed totals through **2033**
  Timings are approximate (± about a day), not a full ephemeris.
- **History Graph & Multi-Series Line Graph: bindable `title_label`.**
  Optional caption above the plot. Accepts any kind so a graph can show a live title or readout without a separate Text Label.
- **Text Label & Text List accept all wire kinds.**
`value` is no longer limited to a small set of source kinds; any upstream that stringifies cleanly can drive a label (logic outputs, formatted values, and so on).
- **Nodes palette starts collapsed.**
  - Category sections (Data Sources / Logic / Visuals) start collapsed
  - Subcategories start collapsed
  - Search still expands matching sections and subcats
- **Sources (3)** — `nodes/sources_extra.py`
 | Node | Behaviour |
 | --- | --- |
 | **Load Average** | `source.loadavg` (`all` / 1 / 5 / 15) |
 | **Thread Count** | `source.threads` |
 | **Running Processes** | `source.running_processes` |
- **Logic (5)** — `nodes/logic_extra.py` + generators
  | Node | Behaviour |
  | --- | --- |
  | **Smooth (EMA)** | Persistent smoothing for noisy sensors |
  | **Rate of Change** | Δ over N look-back samples |
  | **Hysteresis** | On above High, off below Low (no LED flicker) |
  | **String Join** | A + separator + B, optional skip-empty |
  | **Enum Map** | Category/token → number (weather → index, etc.) |
- **Visuals (3)** — `nodes/visuals_extra.py` + generators
  | Node | Behaviour |
  | --- | --- |
  | **Top Processes Table** | Classic `${top name/cpu/mem}` table, N rows |
  | **CPU Core Strip** | Per-core bars via `${cpu cpuN}`, optional heat-map |
  | **Orbit Field** | Decorative orbits; optional Trigger scales speed |

---

## v1.0.5 Legacy and custom scripts overhaul
### Honesty limits (unchanged by design)
- Arbitrary Cairo is not decompiled into Arc/Bar/Star nodes.
- Wiring a native Bar does not change an imported Custom Lua HUD until you edit that Lua to read `in1`…`in12`.
- TEXT layout and `${if_…}` handling remain best-effort / simplified.

### Legacy import; escape-hatch model
- Imported Cairo themes land as self-contained **Custom Lua** nodes. Internal vitals, cache reads, and draw logic stay in that text; Studio does **not** auto-rewire them onto graph sources.
- Companion shells (`sensors.sh`, `weather.sh`, …) become **Custom Script** nodes. Self-caching scripts keep their original basename and cache paths; no stdout wrapper that would break Lua `read_kv_cache` expectations.
- Unwired **daemon** Custom Scripts still run from `start.sh`, so pure-Lua HUDs keep getting fresh cache files even when nothing is wired in the graph.
- Cache/asset path rewrite toward theme-local `CACHE_DIR`, `ASSETS_DIR`, and `.runtime-cache`.
- Companion `.conf` files next to scripts are copied into `scripts/` when present.
- Clearer import warnings: Custom Lua/Custom Script are independent escape hatches; graph nodes are optional extra layers.

### Custom Lua
- Bindable inputs expanded from **1–6** to **1–12**.
- Unwired inputs inject as **`nil`** (not `0`) so authors can write `tonumber(in1) or fallback` safely.
- Works as a first-class palette node without the importer: same draw path as other visuals (`cr`, `W`, `H` + framework helpers).
- Offset X/Y still shifts the whole block without editing Lua.

### Custom Script
- **Inline script** continues to win over Script path at Build.
- Self-caching detection (patterns such as `CACHE_FILE`, `sensors.cache`, `weather.cache`) avoids the generic cache wrapper.
- Documented as a palette escape hatch for ad-hoc shell and legacy companions, not only an import artifact.

### Builder / start.sh
- Daemon family collection includes unwired `source.custom_script` nodes with `poll_mode: daemon`.
- Build copies Custom Lua `asset_paths` into both `assets/` and `images/` when present.

### Docs
- README Legacy Import section and wiki pages updated for the escape-hatch model:
  - Legacy Importer Internals
  - Theme Architecture & Codegen Pipeline
  - Node Reference — Visuals (Custom Lua)
  - Node Reference — Sources (Custom Script)

### Honesty limits (unchanged by design)
- Arbitrary Cairo is not decompiled into Arc/Bar/Star nodes.
- Wiring a native Bar does not change an imported Custom Lua HUD until you edit that Lua to read `in1`…`in12`.
- TEXT layout and `${if_…}` handling remain best-effort/simplified.

---

### v1.0.4 Small Bug Fix
**Layers dock no longer steals focus when reordering**
Clicking a row in the Layers list starts a drag on that row on mouse-down, before any drag begins. That selection fired `itemSelectionChanged` and pushed the node onto the canvas scene, which raised the tabified Properties dock and swapped Layers out from under the pointer, interrupting the drag.
Selection driven from Layers is now guarded so the property panel content still updates in the background, but Properties is not raised; a direct click on a node in the canvas still opens Properties as before. After a drop, the Layers list rebuild no longer clears the highlight on the row you just moved; it is re-selected by id so the active layer stays visibly selected.

---

**v1.0.3 AppImage / AppRun improvements**
### 1. Flat layout with PyInstaller 6+
Added `--contents-directory .` to the PyInstaller call.
PyInstaller 6+ nests support files (including Qt plugins) under `_internal/` by default. This flag restores the previous flat layout next to the executable so paths inside AppRun remain predictable.

### 2. Reliable Wayland with X11 fallback
- `QT_QPA_PLATFORM` is now set to `wayland;xcb` when `$WAYLAND_DISPLAY` is present. Qt tries Wayland first and silently falls back to XCB if needed.
- Plain X11 sessions still receive `xcb`.
- Existing user-set `QT_QPA_PLATFORM` is respected.
- Explicitly pin `QT_PLUGIN_PATH` and `QT_QPA_PLATFORM_PLUGIN_PATH` to avoid distro-level system Qt plugins that conflict with the bundled PyQt6.
Also added a build-time warning if `libqwayland.so` was not bundled by PyInstaller (without the plugin the Wayland path is effectively a no-op).

### 3. Self-installing desktop entry + icon (no appimaged required)
On every launch AppRun now:
- Checks whether `~/.local/share/applications/conky-studio.desktop` already points at the current AppImage.
- If not, installs a corrected `.desktop` file and the 256×256 icon into the appropriate XDG locations.
- Refreshes desktop/icon caches when the tools are available.
The process is idempotent and non-fatal; any failure still lets the application launch normally.
**Installation behaviour change**
Instead of writing `Exec="$APPIMAGE"` (a transient path), the first run now:
- Copies the AppImage to `~/Applications/conky-studio.AppImage`.
- Points the desktop entry’s `Exec=` at that permanent location.
Details:
- Re-copies automatically when a newer AppImage is run (so shipping an update only requires launching the new file once).
- Detects when it is already running from the installed copy (`readlink -f` comparison) and skips the copy step to avoid loops.
- To fix an existing broken `.desktop` entry that points at a dead path: delete it once (`rm ~/.local/share/applications/conky-studio.desktop`) or simply launch the AppImage directly; the install logic will recreate a correct entry.

---

## 1.0.2
### Added
- **Update checker.** Conky Studio now checks GitHub for newer releases
  instead of you having to remember to look.
  - **Silent on startup** — runs automatically when the app launches, on
    a background thread so a slow or unreachable network never delays
    opening the window. It only ever says anything if a newer version
    actually exists; if you're already up to date, it stays quiet.
  - **On demand** — new **Help → Check for Updates…** menu action runs
    the same check manually and always reports a result (up to date,
    update found, or a network error), so it doubles as a connectivity
    sanity check.
  - When a newer version is found, a dialog shows the current vs.
    latest version and an **Open GitHub Release** button, along with:
    "Go to GitHub to get the new release, or if it is installed, use
    Griffin Updater to update to the new version."
  - Checks the GitHub Releases API (`/releases/latest`) rather than
    polling a fixed versioned download URL, so it always compares
    against whatever the newest published release actually is.
### New file
- `conkystudio/update_checker.py` — version comparison, the GitHub API
  call, and the background `QThread` worker. No UI code lives here;
  `main_window.py` owns the dialog and menu wiring.
_No other visual nodes were affected; every other gauge/readout
generator (Arc Gauge, Segmented Gauge, Bar, Text, etc.)
was audited and already displays the real bound value correctly. The
Reactor Gauge's `value` input already accepted any numeric source
(percent, celsius, or plain number); the bug was purely in how that
value was rendered, not in what sources it could bind to.

---

## Version 1.0.1
### Fixed
- **Reactor Gauge (`visual.reactor_gauge`); incorrect value readout for non-percent sources.**
  The centre number always displayed the gauge's internal 0–100 fill
  percentage instead of the actual bound value. This was invisible for
  CPU/GPU percent sources (where the two happen to be nearly the same),
  but made the node look "locked" to CPU/GPU: binding it to Fan RPM,
  GPU Clock (MHz), Disk Temp, or any other non-percent numeric source
  produced a meaningless 0–100 number instead of the real reading.
  The readout now shows the raw bound value.
### Added
- **Reactor Gauge: new `value_suffix` property.**
  Lets the centre readout be labeled to match whatever source it's
  bound to (e.g. `%`, ` RPM`, ` MHz`, `°C`), the same way Arc Gauge and
  Segmented Gauge already work. Defaults to `%` to match prior behavior
  for existing projects.
