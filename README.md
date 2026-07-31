# Conky Studio

**2 nodes = 1 widget in 30 seconds. Start simple. Scale to anything.**

<div align="center">

<img width="300" height="300" alt="conky-studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

### Design desktop HUDs visually. Ship real Conky themes.

**No sudo, no pkexec, and no package commands (apt, pacman, dnf, rpm, and so on).** If your distro supports AppImages and Conky, you can run Conky Studio.

**Automatically adapts themes to your system (X11/Wayland, compositor, Conky build, hardware)**

**What you see in the live preview is exactly what gets exported; 1:1 Conky output, not a mockup.**

Public release planned for **August 1st**.

[Video Showcase](https://youtu.be/RbUr9pFosDc) · [Discord](https://discord.gg/kJZCZWg5nw)

</div>

---

## Conky is cool, but hard for some to get into. Not anymore

You can have a working widget in 30 seconds.

No, I'm serious.

Grab a CPU node, grab a gauge node, wire them up, and you have a working widget.

Conky can draw almost anything on your desktop. The cost has always been the same: Lua, Cairo, shell scripts, and config files edited by hand, then restart, squint, and try again. What took days can now take hours or less. Even someone who has never coded a theme can enjoy Conky; no code is required to get started.

---

## Vision

Conky Studio is not only a convenience UI. It is a shift from **manual config hacking** to **visual system design** without giving up the real Conky runtime.

> Make Conky as easy to design as it is powerful to run.  
> **Preview what you ship. Ship what you preview.**
**Conky Studio exists to remove that loop.**

It is a visual system designer for Conky HUDs: a node graph for data, logic, and drawing; a live preview driven by a **real Conky instance**; and a build step that writes a normal theme folder (`start.sh`, `conky.conf`, `render.lua`, scripts). You design in the editor. You run the same files Conky would run without the editor.

No fake canvas. No “approximate” export. **Live preview and built themes use the same pipeline.**

---

## Why Conky Studio was made

| Pain | What Studio does instead |
|------|---------------------------|
| Edit Lua → restart Conky → repeat | Change a property, see it in a live Conky preview |
| Hunt `${goto}` and font lines for layout | Drag nodes; wire data into visuals |
| Glue `execi` scripts and caches by hand | Sources with `execi` or daemon mode; scripts become nodes |
| Fear breaking a working theme | Build/export a clean, structured theme; import legacy themes into a graph you can edit |
| Powerful overlays only for people who enjoy config archaeology | Same power, visual workflow, production output |

This is not a theme pack and not a screenshot toy. It is a **tool for building production-ready Conky HUDs** faster, with the same Cairo/Lua stack Conky already uses.

---

## Overview

Conky is extremely powerful, but building and managing themes often means manually editing Lua, Cairo, shell scripts, and Conky configs.

**Conky Studio changes that.**

You can build real, shippable themes today.

### What you get

- **Visual editing** instead of pure config grinding
- **Live preview** from an actual Conky process; **1:1 with export**
- **Faster iteration** (seconds, not restart cycles)
- **Reusable structure** via nodes and plugins
- **Clean theme exports** (`start.sh`, conf, Lua, scripts, assets)
- **Import** of existing themes into an editable graph

| Task | Traditional workflow | Conky Studio |
|------|----------------------|--------------|
| Adjust layout | Edit → restart → repeat | Node/tweak and see instantly |
| Add widget | Write Lua + config | Drop and connect nodes |
| Debug script | Logs + guesswork | Live preview + logs |
| Complex gauge | Tens of minutes of Lua | Wire a gauge node in seconds |

---

## Key features

- **Visual node editor** — Blueprint-style graph; drag, connect, test without a full restart cycle
- **Live preview & debugging** — Real Conky instance; what you preview is what you build
- **Theme manager** — Detects themes in `~/.conky` and `~/.config/conky`; previews, install/export, duplicate, README editing, start/stop
- **Theme wizard** — Starter HUDs by category (Minimal, Gaming, RPG, Sci-Fi, Cyberpunk, Terminal, Fantasy, and Batman) and panels (Weather, CPU, GPU, RAM, Clock, Calendar, Music, …)
- **Legacy theme importer (Beta)** — Semantic import of existing conf + TEXT + Lua + scripts into nodes (details below)
- **Plugin system** — JSON node packs (logic expressions, visual draw bodies, helpers) for community extensions
- **Flexible data execution** — Per source: `execi` (Conky-native) or **daemon** (background scripts + cache)
- **Custom scripts as nodes** — Any executable script, poll interval, and mode under your control
- **Click actions** — Visual nodes can run shell commands on click
- **Community store (in progress)** — Import via `.zip`, `.tar.gz`, or online sources
- **Gradients** — Linear and radial fills on gauges, bars, shapes, and other fill-capable visuals
- **Custom Lua node** — Full Cairo escape hatch when the palette is not enough

## Conky Studio Sharing & Compatibility Guide

> **Bottom Line:** The Project JSON is ideal for collaboration and remixing inside Conky Studio, provided both parties have compatible Studio versions, matching plugins, and access to external assets. However, it is not a standalone portable theme; you must use the **built theme output** for a fully self-contained runtime environment.

---

### Share the project's JSON; what Breaks or Needs Care

| Issue Category | Problem / Cause | Impact & Behavior | Resolution |
| :--- | :--- | :--- | :--- |
| **Image & Script Paths** | Props like `path`, `script_path`, and `swap paths` are often stored as absolute paths on the author's machine. | Recipient opens the project with missing file/path errors until manually re-linked. | Send assets alongside the JSON or place them relative to the project folder. |
| **Plugin Node Types** | Custom nodes (e.g., `logic.smooth`, `visual.plugin.*`) require specific plugin packs. | Unknown type errors or failed builds if the recipient lacks the plugin. | Ensure both machines have identical plugin packs installed. |
| **Custom Script / Custom Lua** | Graph references external script files, but code bodies reside locally on disk. | Graph loads, but the underlying execution fails without the script files. | Package external `.lua` / shell script files together with the JSON. |
| **Hardware / OS Specifics** | Sources rely on local hardware (e.g., specific GPU stats, weather APIs, network `iface` names). | Non-fatal warnings or empty data readings on systems with different setups. | Update source configurations to match target machine interfaces/sensors. |
| **Studio Versioning** | Newer node types (e.g., `Map Range`, `Rectangle`, gradients) require updated Studio registries. | Older Studio versions will report unknown/unregistered node types. | Upgrade all Studio instances to the minimum required build version. |

---

### Practical Guidance by Goal

| Goal | Required Artifacts | Usage & Compatibility |
| :--- | :--- | :--- |
| **Edit / Remix Graph Elsewhere** | Project JSON + Images/Scripts + Required Plugin Packs | Allows full editing in Conky Studio; paths must be updated upon load. |
| **Run the HUD Only** | Built Theme Folder (`start.sh`, `conky.conf`, `render.lua`, `images/`, `scripts/`) | Self-contained for Conky runtime. No Conky Studio required. |
| **Public Share / Store Release** | Exported Theme Package (Optionally attach Project JSON for remixability) | Guarantees end-user portability while allowing developers to modify source graphs. |

Themes use a standardized **`start.sh`** entry point for consistent startup, background pollers, single-instance locking, and fewer edge-case failures across distros.

---

## Smart system detection

This tool doesn’t just generate configs; it understands your system and adapts themes accordingly.

- **Display server** — X11 vs Wayland
- **Desktop environment / compositor** — KDE, GNOME (warns on GNOME Wayland / Mutter), etc. (best-effort)
- **Wayland capabilities** — Layer-shell support and HUD compatibility checks
- **Conky installation** — Installed or missing, version, Wayland support
- **Hardware & tools** — Sensors (lm-sensors), GPU hints, network interfaces, disks

---

## Wayland support

Overlay behaviour depends on the compositor:

**Supported (typical):**

- wlroots-based (Sway, Hyprland, Wayfire, etc.)
- KDE Plasma (Wayland)
- Mir-based compositors

**Not supported for this kind of overlay:**

- GNOME (Mutter) — no suitable overlay path. This is not a Conky Studio choice; it is the state of Conky + GNOME.

**Also note:** some distro packages (e.g. `conky-all` on Ubuntu/Debian) are **X11-only** builds. Conky Studio detects your session and warns when the environment will not support the window type you need.

---

## Current status

**Actively in development.**

### Implemented

- Visual node editor
- Live preview (real Conky instance) — **1:1 with generated output**
- Theme manager
- Code generation (`conky.conf`, `render.lua`, `start.sh`, scripts)
- Import/export
- Plugin framework (logic + visual packs)
- Community store backend
- Theme wizard (starting points; art packs still expanding)
- README editor
- Clickable nodes
- Colour picker with solid + gradient fills and on-screen colour picking
- Logic nodes (math, conditionals, remap, gates, and more; see below)
- External + native data sources
- SVG → Cairo path where supported
- Save/open project
- Build to folder or build & install to Manager
- Layer/undockable property workflows
- Generate `theme.json`
- OpenDesktop integration (opens in browser)
- Share a project by sharing the JSON saved with the project
- Legacy theme import (current Conky syntax imports better; importer gets you ~70–90% there. Studio is where you finish)
- Custom editable Lua node for what this tool does not cover.

### Beta

- **Legacy importer** (see below)
- Music/now-playing nodes with playerctl-style scripts

### In progress (community-driven)

Whether these land is left open for community feedback:

- Animation keyframes
- Built-in performance profiler

---

## Architecture

```text
conkystudio/
├── model/      Project structure (JSON)
├── nodes/      Node definitions (sources, logic, visuals)
├── plugins/    Community extensions (JSON packs)
├── importer/   Legacy theme parser
├── codegen/    Theme generator (conf, Lua, start.sh, scripts)
├── hardware/   System / session detection
├── fonts/      Font installer
├── manager/    Theme management & process control
├── store/      Community index
├── preview/    Live Conky runner
└── ui/         PyQt6 interface
```

---

## Output structure

```text
<ThemeName>/
├── theme.json
├── start.sh
├── conky.conf
├── render.lua
├── images/
├── fonts/
├── scripts/
├── .runtime-cache/   # created at runtime
├── preview.png       # when available
└── README.md
```

`start.sh` detaches cleanly (session + lock file). Themes keep running after you quit Conky Studio; the Manager starts them as independent processes.

---

## Node system

### Data sources

- CPU, RAM, disk, network, uptime, hostname, kernel, processes
- Battery, date/time, greeting
- GPU stats & temps, disk sensors, weather (script + cache families)
- Now playing / music (playerctl-style)
- **Custom Script** — any executable; `execi` or daemon polling

Unused sources are not polled in the generated theme.

### Logic

Built-in logic sits between sources and visuals (chains evaluate in dependency order each refresh):

| Category | Node Name | What It Does (Plain English) | Real-World Example |
| :--- | :--- | :--- | :--- |
| **Basic Math** | **Math** | Performs standard math operations (add, subtract, multiply, divide, average, min, max). | Add two separate sensor values together |
| | **Scale / Offset** | Multiplies and shifts a number up or down. | Convert seconds to minutes (`value × 1/60`) |
| | **Invert Percent** | Flips a percentage to show remaining capacity (`100 - value`). | Convert **75% used** into **25% remaining disk space** |
| | **Absolute** | Removes minus signs so all numbers are positive. | Track distance or speed regardless of direction |
| | **Round** | Trims messy decimals to a set precision. | Round `3.14159` down to `3.14` |
| **Decisions & Rules** | **Conditional** | Evaluates an IF/THEN rule based on a target value. | **IF** temp > 90° **THEN** show red **ELSE** show green |
| | **Threshold Gate** | Outputs a simple **1 (ON)** or **0 (OFF)** switch based on a limit. | Turn a warning LED on when speed passes a threshold |
| | **AND / OR Gate** | Combines multiple signals into a single TRUE/FALSE logic check. | Trigger alert if Door Open **AND** Motion Detected |
| | **Pick A/B** | Swaps between two choices depending on a control signal. | Show Icon A by default, switch to Icon B when active |
| **Range & Smoothers** | **Map Range** | Translates a number range into a completely different range. | Translate 0–100% volume to a 0°–180° dial angle |
| | **Clamp** | Locks a value between strict minimum and maximum limits. | Stop a progress bar from overshooting past 100% |
| | **Lerp** | Smoothly blends or transitions between two values. | Glide a pointer needle smoothly instead of instant jumping |
| | **Deadzone** | Ignores minor sensor noise/jitter around a center point. | Stop a needle from flickering when resting at zero |
| **Formatting** | **String Format** | Wraps raw numbers into customized text labels. | Turn raw number `65` into `"Speed: 65 mph"` |

**Plugins** can add more (e.g., EMA smooth, rate limit, peak hold, multi-stage threshold chains, unit convert, text unit format) without changing core Studio.

### Visuals

| Area | Nodes |
|------|--------|
| **Text** | Text Label, Text List, Wall Calendar |
| **Gauges & bars** | Arc / Ring Gauge, Bar (solid/segmented/trapezoid), Reactor Gauge, Ring Track, LED Dot |
| **Graphs** | History graph |
| **Effects** | Glow / Pulse, Spiral, Radar Sweep, Moon Phase, Corner Brackets, Analog Clock |
| **Shapes** | Rectangle (rounded), Horizontal/Vertical Line, Crosshair, Star, Triangle, Circle (ellipse/arc/pie) |
| **Media & icons** | Image/Icon (PNG/SVG + threshold swaps), Weather Icon, Album Art, Icon Glyph |
| **Advanced** | **Custom Lua** — raw Cairo in the draw path (text-edit escape hatch) |

**Star styles:** regular N-point star, pentagram, Star of David, Christmas tree star.

**Fill modes:** solid, linear gradient, or radial gradient on fill-capable gauges, bars, shapes, and effects (where the generator supports it).

**Dual-use tips:** bars can read as CRT strips or solid blocks; arc gauges as dots, arcs, or smile-like curves with circles; shapes and ring tracks stack into larger motifs without Custom Lua.

### Plugins

- JSON packs (`api_version` 1.1): logic (`lua_expr` + optional `lua_helpers`) and visual (`lua_draw_body`)
- Install under the Studio plugins path; reload plugins after adding packs
- Keep unique behaviour in plugins (smooth, peak hold, multi-stage chains); prefer built-ins when they already cover the same job

More nodes continue to land before and after public release.

---

## Custom Lua (escape hatch)

When a layout or effect is too specific for the palette, drop a **Custom Lua** node: a text editor that runs your Cairo code inside the same draw path as every other visual (`cr`, `W`, `H`, and framework helpers are in scope). Offset X/Y shift the block without editing the Lua.

That is intentional: **compose with nodes when you can; open the text box when you can’t.**

---

## Legacy importer (Beta)

**Project → Import Legacy Theme** points at a folder with a Conky conf. Import is **semantic**, not a guaranteed pixel clone, but **nothing important is dropped on purpose**. Current Conky syntax imports more cleanly. Images are not imported as drawable assets in every case.

### What it converts

| Input | Result |
|--------|--------|
| `*.conf` / `conkyrc` | Canvas size, alignment, gaps, update rate, `lua_load`, draw hooks |
| `conky.text` | `${goto}` / offset layout (best-effort), fonts, colours, text nodes |
| `${cpu}`, `${memperc}`, `${time}`, … | Native source nodes, wired into visuals where possible |
| `${image}` | Image / Icon or Album Art (`-n`); paths resolved under the theme |
| `${execi}` / `${exec}` / `${execbar}` | Known scripts → native / family sources; else **Custom Script** nodes |
| Cairo `.lua` from `lua_load` | **Custom Lua** node(s): helpers + draw-hook body; surface boilerplate stripped to use Studio’s `cr` / `W` / `H` |
| Click regions in Lua | Clickable marker nodes with commands |
| `.sh` / shebang scripts in the tree | Custom Script (or known mapping), including scripts only used from Lua |

### Limitations (honest)

- Does **not** decompile arbitrary Cairo into Arc / Bar / Star nodes
- Heavy custom Lua stays one (or more) **Custom Lua** node(s)
- `${if_…}` conditionals are simplified (content kept, always shown)
- Layout from pure TEXT positioning is approximate

Warnings list every approximation. After import, edit the graph, then **build** the same way as a native Studio project — live preview and export remain **1:1** for whatever is on the canvas.

---

## Compatibility note

All Studio-built themes share a standardized **`start.sh`** so startup, daemon pollers, and single-instance behaviour stay consistent across machines and distros.

---

## Support development

If you want to help push this further:

- [GitHub Sponsors](https://github.com/sponsors/bobbycomet)
- [Ko-fi](https://ko-fi.com/bobby60908)

Support goes toward development time, features, documentation, and stability.

---

## Screenshots

<img width="1920" height="1080" alt="manager" src="https://github.com/user-attachments/assets/e5ad19c9-b4ab-4eee-90df-f2dc5184966b" />
<img width="1920" height="1080" alt="nodes" src="https://github.com/user-attachments/assets/6f5ae7f5-aa81-4cec-95e5-47d84b40bade" />
<img width="1920" height="1080" alt="undocking" src="https://github.com/user-attachments/assets/d0bb0a7b-6559-4519-99b9-3bd648548275" />
<img width="1920" height="1080" alt="Screenshot_20260730_013306" src="https://github.com/user-attachments/assets/355aba42-f244-4225-9fa4-ae8d6817c003" />
<img width="1920" height="1080" alt="Screenshot_20260730_013223" src="https://github.com/user-attachments/assets/80dc01ed-28cf-4f4a-9ee4-b2673584b0f5" />
<img width="1920" height="1080" alt="Screenshot_20260730_013153" src="https://github.com/user-attachments/assets/ad03e7a1-cede-4b61-b07b-51d81366fc5a" />
<img width="1920" height="1080" alt="Screenshot_20260730_013126" src="https://github.com/user-attachments/assets/a2975d15-ae83-4eda-b73d-5591c5020837" />

## Themes built with this tool

*(Red lines was me redacting my location info.)*

<img width="1920" height="1080" alt="Screenshot_20260724_083124" src="https://github.com/user-attachments/assets/06c87f00-2b5a-466a-956b-00e8b84876f1" />
<img width="1920" height="1080" alt="Screenshot_20260724_181643" src="https://github.com/user-attachments/assets/118ba01f-0a36-4127-9577-2fe80bac97aa" />
<img width="1920" height="1080" alt="Screenshot_20260719_220545" src="https://github.com/user-attachments/assets/981eaf50-5f37-4c21-8644-e39901bf60ce" />
