# Conky Studio

2 nodes = 1 widget in 30 seconds. Start simple. Scale to anything.

<div align="center">

<img width="300" height="300" alt="conky-studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

### Design desktop HUDs visually. Ship real Conky themes.

**What you see in the live preview is exactly what gets exported; 1:1 Conky output, not a mockup.**

Public release planned for **August 1st**. Showcase video coming soon.
[Video Showcase](https://youtu.be/RbUr9pFosDc)
Machine tested on: GPU RTX 2060, CPU Ryzen 7 2700, RAM 32 GB 3600 MHz, Motherboard DS3H B450, SSD Sabrent 250 GB GEN 3
</div>


---

## Conky is cool, but hard for some to get into. Not anymore

You can have a working widget in 30 seconds.

No, I'm serious.

Grab a CPU node, grab a gauge node, wire them up, and you have a working widget.

Conky can draw almost anything on your desktop. The cost has always been the same: Lua, Cairo, shell scripts, and config files edited by hand, then restart, squint, and try again. What took days can now take hours or less. Even someone who has never coded a theme can enjoy Conky; no code is required to get into Conky.

**Conky Studio exists to remove that loop.**

It is a visual system designer for Conky HUDs: a node graph for data, logic, and drawing; a live preview driven by a **real Conky instance**; and a build step that writes a normal theme folder (`start.sh`, `conky.conf`, `render.lua`, scripts). You design in the editor. You run the same files Conky would run without the editor.

No fake canvas. No “approximate” export. **Live preview built themes are the same pipeline.**

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
- **Plugin system** — Custom nodes, generators, tools  
- **Flexible data execution** — Per source: `execi` (Conky-native) or **daemon** (background scripts + cache)  
- **Custom scripts as nodes** — Any executable script, poll interval, and mode under your control  
- **Click actions** — Visual nodes can run shell commands on click  
- **Community store (in progress)** — Import via `.zip`, `.tar.gz`, or online sources  

Themes use a standardized **`start.sh`** entry point for consistent startup, background pollers, single-instance locking, and fewer edge-case failures across distros.

---

## Wayland support

Overlay behaviour depends on the compositor:

**Supported (typical):**

- wlroots-based (Sway, Hyprland, Wayfire, etc)  
- KDE Plasma (Wayland)  
- Mir-based compositors  

**Not supported for this kind of overlay:**

- GNOME (Mutter) — no suitable overlay path  

**Also note:** some distro packages (e.g., `conky-all` on Ubuntu/Debian) are **X11-only** builds. Conky Studio detects your session and warns when the environment will not support the window type you need.

---

## Current status

**Actively in development.**

### Implemented

- Visual node editor  
- Live preview (real Conky instance) — **1:1 with generated output**  
- Theme manager  
- Code generation (`conky.conf`, `render.lua`, `start.sh`, scripts)  
- Import/export  
- Plugin framework  
- Community store backend  
- Theme wizard (starting points, not fully finished art packs)  
- README editor  
- Clickable nodes  
- Logic nodes (math, conditionals, string format)  
- External + native data sources  
- SVG → Cairo path where supported  
- Save / open project  
- Build to folder or build & install to Manager  
- Layer / undockable property workflows  
- Generate `theme.json`  
- OpenDesktop integration (opens in browser)

### Beta

- **Legacy importer** (see below)  
- Music / now-playing nodes with playerctl-style scripts  

### In progress
  
- Animation keyframes  
- Built-in performance profiler  

---

## Architecture

```text
conkystudio/
├── model/       Project structure (JSON)
├── nodes/       Node definitions
├── plugins/     Community extensions
├── importer/    Legacy theme parser
├── codegen/     Theme generator (conf, Lua, start.sh, scripts)
├── hardware/System/session detection
├── fonts/       Font installer
├── manager/     Theme management & process control
├── store/       Community index
├── preview/     Live Conky runner
└── ui/          PyQt6 interface
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

- Math (add, subtract, multiply, divide, average, min, max)  
- Conditionals (threshold → then/else)  
- String formatting (`{value}` templates)  

### Visuals

| Area | Nodes |
|------|--------|
| Text | Text Label, Text List, Wall Calendar |
| Gauges & bars | Arc/Ring Gauge, Bar (solid/segmented/trapezoid), **Reactor Gauge** |
| Graphs | History graph |
| Effects | Glow/Pulse, Spiral, **Radar Sweep**, Moon Phase, Corner Brackets, **Analog Clock** |
| Shapes | **Star**, **Triangle**, **Circle** (ellipse/arc/pie) |
| Media & icons | Image/Icon (PNG/SVG + swaps), Weather Icon, Album Art, Icon Glyph |
| Advanced | **Custom Lua** (raw Cairo in the draw path) |

**Star styles:** regular N-point star, pentagram, Star of David, Christmas tree star.  

**Dual-use tips:** bars can read as CRT strips or solid blocks; arc gauges as dots, arcs, or smile-like curves with circles; shapes stack into larger motifs.

### Plugins

- Extend with custom node types  
- Example bundle ideas: clamp, temperature conversion, status indicators  

More nodes continue to land before and after public release.

---

## Legacy importer (Beta)

**Project → Import Legacy Theme** points at a folder with a Conky conf. Import is **semantic**, not a guaranteed pixel clone, but **nothing important is dropped on purpose**.

### What it converts

| Input | Result |
|--------|--------|
| `*.conf` / `conkyrc` | Canvas size, alignment, gaps, update rate, `lua_load`, draw hooks |
| `conky.text` | `${goto}`/offset layout (best-effort), fonts, colours, text nodes |
| `${cpu}`, `${memperc}`, `${time}`, … | Native source nodes, wired into visuals where possible |
| `${image}` | Image/Icon or Album Art (`-n`); paths resolved under the theme |
| `${execi}` / `${exec}` / `${execbar}` | Known scripts → native/family sources; else **Custom Script** nodes |
| Cairo `.lua` from `lua_load` | **Custom Lua** node(s): helpers + draw-hook body; surface boilerplate stripped to use Studio’s `cr` / `W` / `H` |
| Click regions in Lua | Clickable marker nodes with commands |
| `.sh` / shebang scripts in the tree | Custom Script (or known mapping), including scripts only used from Lua |

### Limitations (honest)

- Does **not** decompile arbitrary Cairo into Arc/Bar/Star nodes  
- Heavy custom Lua stays one (or more) **Custom Lua** node(s)  
- `${if_…}` conditionals are simplified (content kept, always shown)  
- Layout from pure TEXT positioning is approximate  

Warnings list every approximation. After import, you can edit the graph, then **build** the same way as a native Studio project — live preview and export remain **1:1** for whatever is on the canvas.

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

## Vision

Conky Studio is not only a convenience UI. It is a shift from **manual config hacking** to **visual system design** — without giving up the real Conky runtime.

> Make Conky as easy to design as it is powerful to run.  
> **Preview what you ship. Ship what you preview.**

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

*(Red lines redact location info.)*

<img width="1920" height="1080" alt="Screenshot_20260724_083124" src="https://github.com/user-attachments/assets/06c87d09-2b5a-466a-956b-00e8b84876f1" />

<img width="1920" height="1080" alt="Screenshot_20260724_181643" src="https://github.com/user-attachments/assets/118ba01f-0a36-4127-9577-2fe80bac97aa" />

<img width="1920" height="1080" alt="Screenshot_20260719_220545" src="https://github.com/user-attachments/assets/981eaf50-5f37-4c21-8644-e39901bf60ce" />
```
