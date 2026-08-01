# Conky Studio

**2 nodes = 1 widget in 30 seconds. Start simple. Scale to anything.**

<div align="center">

<img width="300" height="300" alt="Conky Studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

**Design desktop HUDs visually. Ship real Conky themes.**

No sudo. No package installers. If your distro runs AppImages and Conky, you can run Conky Studio. Optional nodes use existing Linux tools like playerctl and lm-sensors when available [Check Requirements](https://github.com/bobbycomet/Conky-Studio/wiki/Requirements).

**Live preview = export.** Same pipeline. Not a mockup.

Public release planned for **August 1st 2026**.

[Video Showcase](https://youtu.be/RbUr9pFosDc) · [Discord](https://discord.gg/kJZCZWg5nw) · [YouTube](https://www.youtube.com/@BobbyComet) · [WIKI](https://github.com/bobbycomet/Conky-Studio/wiki)

</div>

---

## Why this exists

Conky Studio started as a personal tool for creating and managing my own Conky themes. Over time, after sharing the themes built with it and receiving positive feedback, I decided to turn it into a public project.

The goal of Conky Studio is to make creating advanced Conky HUDs more accessible while keeping the power and flexibility of Conky's existing workflow.

Conky can draw almost anything on your desktop. The cost has always been the same: Lua, Cairo, shell scripts, and config files edited by hand, then restart, squint, and try again.

**Conky Studio removes that loop.**

| The old way | With Studio |
|-------------|-------------|
| Edit Lua → restart → repeat | Change a property, see it in a **live Conky** preview |
| Hunt `${goto}` and font lines | Drag nodes; wire data into visuals |
| Glue `execi` scripts by hand | Sources as nodes (`execi` or daemon + cache) |
| Fear breaking a working theme | Build a clean folder; import legacy themes into a graph you can edit |
| Overlays only for config veterans | Same power, visual workflow, production output |

> Make Conky as easy to design as it is powerful to run.  
> **Preview what you ship. Ship what you preview.**

You design in a node graph. You run the same files Conky would run without the editor (`start.sh`, `conky.conf`, `render.lua`, scripts). No fake canvas. No “approximate” export.

---

## 30-second first widget for [Getting Started](https://github.com/bobbycomet/Conky-Studio/wiki/Getting-Started)

1. Drop a **CPU** source  
2. Drop a **gauge** (or bar / text)  
3. Wire them  
4. Hit live preview  

That’s a real Conky widget, not a demo screen.

From there, you add logic, layers, gradients, click actions, custom scripts, or full Custom Lua when the palette isn’t enough.

## Acknowledgments & Disclaimer

This project is an independent tool designed to generate and manage HUDs for [Conky](https://github.com/brndnmtthws/conky). 

>**Please note:** This project is not affiliated with, endorsed by, or sponsored by the official Conky project or its maintainers. Conky is licensed under the GPL-3.0 License.

---

## [Features](https://github.com/bobbycomet/Conky-Studio/wiki/Features) you get

- **Visual node editor** — sources → logic → visuals; drag, connect, iterate  
- **Live preview** — real Conky process; **1:1 with build output**  
- **Theme manager** — themes under `~/.config/conky` (and `~/.conky`); start/stop, README & `theme.json` editing  
- **Theme wizard** — starter HUDs by style (Minimal, Gaming, Sci-Fi, Cyberpunk, Terminal, Fantasy, Batman, etc) and panels (CPU, GPU, Weather, Music, …)  
- **Legacy importer (beta)** — conf + TEXT + Lua + scripts → editable graph (~70–90% there; finish in Studio)  
- **Plugins** — JSON packs for community logic/visual nodes  
- **Smart system detection** — X11/Wayland, compositor, Conky build, sensors, GPU/net/disk hints  
- **Clean exports** — `start.sh`, conf, Lua, scripts, images, fonts  
- **Gradients, click actions, Custom Lua** — solid → full Cairo escape hatch  

| Task | Traditional | Studio |
|------|-------------|--------|
| Adjust layout | Edit → restart → repeat | Tweak and see instantly |
| Add a widget | Write Lua + config | Drop and connect nodes |
| Debug a script | Logs + guesswork | Live preview + logs |
| Complex gauge | Tens of minutes of Lua | Wire a gauge in seconds |

---

## [Runtime Performance](https://github.com/bobbycomet/Conky-Studio/wiki/Runtime-Performance)

Conky Studio is an authoring tool, not a runtime interpreter.

Your node graph is converted into standard Conky files (`conky.conf`, `render.lua`, and scripts) during build. Exported themes run independently of Studio using Conky's normal pipeline.

The number of nodes in your project does not directly affect runtime performance. Runtime cost depends on the generated Lua logic, update intervals, and normal Conky execution.

---

## [Sharing](https://github.com/bobbycomet/Conky-Studio/wiki/Sharing-Projects) & [Compatibility](https://github.com/bobbycomet/Conky-Studio/wiki/Compatibility)

| Goal | What to share |
|------|----------------|
| **Run the HUD only** | Built theme folder (`start.sh`, `conky.conf`, `render.lua`, `images/`, `scripts/`), no Studio required |
| **Edit / remix the graph** | Project JSON **+** images/scripts **+** matching plugins |
| **Public / store release** | Exported theme package; optionally attach the JSON for remixers |

**Project JSON is for collaboration inside Studio**, not a standalone portable theme. Absolute paths, missing plugins, and local scripts are the usual pitfalls; send assets with the JSON, or ship the **built** folder when people only need to run it.

All Studio builds use a standardized **`start.sh`** (session + lock file) so themes keep running after you quit the editor.

---

## Wayland & system fit

Studio detects your session and adapts where it can:

- **Display server** — X11 vs Wayland  
- **Compositor** — KDE, wlroots (Sway, Hyprland, etc), Mir-style; **GNOME/Mutter** is a poor fit for this kind of overlay (Conky + GNOME limitation, not a Studio choice)  
- **Conky build** — installed or missing, version, Wayland support (some distro packages are X11-only)  
- **Hardware** — lm-sensors, GPU hints, network iface, disks  

Use **Tools → Hardware & Session** when a preview looks empty or misplaced.

Check [Compatibility Here](https://github.com/bobbycomet/Conky-Studio/wiki/Compatibility)

---

## Architecture (short)

```text
conkystudio/
├── model/      Project JSON
├── nodes/      Sources, logic, visuals
├── plugins/    Community JSON packs
├── importer/   Legacy theme parser
├── codegen/    conf + Lua + start.sh + scripts
├── hardware/   Session & hardware detection
├── manager/    Install, start/stop themes
├── preview/    Live Conky runner
└── ui/         PyQt6 (Manager · Studio · Store)
```

**Built theme layout**

```text
<ThemeName>/
├── theme.json · start.sh · conky.conf · render.lua
├── images/ · fonts/ · scripts/
├── .runtime-cache/   # at runtime
├── preview.png       # when available
└── README.md
```

---

## Nodes (overview)

**Sources** — CPU, RAM, disk, network, uptime, battery, clock, GPU/temps, weather, music (playerctl), **Custom Script** (`execi` or daemon). Unused sources are not polled in the export.

**Logic** — math, scale/offset, invert %, conditionals, thresholds, AND/OR, map range, clamp, lerp, deadzone, string format, and more. Plugins can add smoothers, peak hold, unit convert, multi-stage chains.

**Visuals** — text, calendars, arc/ring gauges, bars, history graphs, glow/pulse, radar, moon, shapes, images/icons, weather icons, album art, **Custom Lua**.

Fill-capable nodes support **solid, linear, and radial gradients**.

---

## [Legacy Import](https://github.com/bobbycomet/Conky-Studio/wiki/Legacy-Import) (honest)

**Project → Import Legacy Theme** is semantic, not a pixel-perfect clone:

- Converts conf settings (including colour palette/default font when present), TEXT layout (best-effort), common `${…}` sources (CPU, RAM, disk, battery, net, time, …), bars/graphs/`${hr}` when recognized, images, known scripts, and Cairo Lua into **Custom Lua** nodes
- Deduplicates identical sources and lays out the graph so sources sit in a left column and visuals near their draw positions
- Does **not** reverse-engineer arbitrary Cairo into Arc/Bar nodes
- `${if_…}` is simplified; layout from pure TEXT is approximate
- Warnings are summarized (not one line per unknown token)
- Images cannot currently be reconstructed from legacy theme references. Re-add assets through Studio after import.

>**Custom scripts & Lua:**
Custom Script nodes are text-editable and can be paired with Custom Lua nodes for advanced integrations. This allows complex or non-standard logic from legacy themes to remain usable inside Studio, though behavior depends on the original script design. 
>
>Then you edit and build like any native project; preview and export stay 1:1 for what’s on the canvas.
>
>This importer will improve over time, but some limitations are inherent to how Conky themes are written. Think of it as a migration and remixing tool: it gets existing themes into Studio quickly, while preserving complex sections through Custom Lua when automatic conversion isn’t possible.

---

## Status

**Actively developed.** Core editor, live preview, manager, codegen, wizard, plugins, importer, gradients, studio tour, and support links are in place.

**Community-driven (maybe):** animation keyframes, built-in profiler; depends on feedback.

---


### After installing

```bash
conky -v          # confirm Conky; look for Wayland if you use a Wayland session
which playerctl   # music nodes
sensors           # temperatures (after sensors-detect where applicable)
```

In Conky Studio: Tools → Hardware & Session to verify display server, Conky build, sensors, and GPU/net hints.

AppImage host notes

A working desktop session (not a bare TTY)
Ability to run AppImages (FUSE / libfuse or extract-and-run, per your distro’s AppImage docs)
No sudo required for Studio itself; the commands above are only for system dependencies

---

## Support development

- [GitHub Sponsors](https://github.com/sponsors/bobbycomet)  
- [Ko-fi](https://ko-fi.com/bobby60908)  

Goes toward development time, features, docs, and stability.

---

## Screenshots

<img width="1920" height="1080" alt="Manager" src="https://github.com/user-attachments/assets/e5ad19c9-b4ab-4eee-90df-f2dc5184966b" />

<img width="1920" height="1080" alt="Node editor" src="https://github.com/user-attachments/assets/6f5ae7f5-aa81-4cec-95e5-47d84b40bade" />

<img width="1920" height="1080" alt="Undocking panels" src="https://github.com/user-attachments/assets/d0bb0a7b-6559-4519-99b9-3bd648548275" />

<img width="1920" height="1080" alt="Studio" src="https://github.com/user-attachments/assets/80dc01ed-28cf-4f4a-9ee4-b2673584b0f5" />

<img width="1920" height="1080" alt="Properties" src="https://github.com/user-attachments/assets/ad03e7a1-cede-4b61-b07b-51d81366fc5a" />

<img width="1920" height="1080" alt="Preview" src="https://github.com/user-attachments/assets/a2975d15-ae83-4eda-b73d-5591c5020837" />

### Starter themes (a few clicks, then edit)

These are purposefully unfinished, they are to help you learn and explore, while also giving you a headstart on a clean looking HUD.

<img width="1920" height="1080" alt="Screenshot_20260731_150901" src="https://github.com/user-attachments/assets/c00d10ef-eb56-40f7-9c81-bba90cd90946" />

<img width="1920" height="1080" alt="Screenshot_20260731_150823" src="https://github.com/user-attachments/assets/5f1bc21e-79c0-4aea-9662-1233eb589253" />

<img width="1920" height="1080" alt="Screenshot_20260731_150757" src="https://github.com/user-attachments/assets/581d7a53-75ae-4dfb-ad04-c8b99babb0ec" />

<img width="1920" height="1080" alt="Screenshot_20260731_150719" src="https://github.com/user-attachments/assets/84b6c6c0-266b-4204-afea-40df40980eaf" />

<img width="1920" height="1080" alt="Screenshot_20260731_150648" src="https://github.com/user-attachments/assets/d746a798-4fba-414c-b171-6c50b4eeeb76" />

<img width="1920" height="1080" alt="Screenshot_20260731_150619" src="https://github.com/user-attachments/assets/1ddd8e17-68bf-4fe1-80b2-54ddc7de9e1c" />

<img width="1920" height="1080" alt="Screenshot_20260731_004434" src="https://github.com/user-attachments/assets/85a92bbf-6e8e-455e-8370-340811eea48d" />

<img width="1920" height="1080" alt="Starter theme B" src="https://github.com/user-attachments/assets/03cc075f-5add-44d2-a444-de7b1604b045" />

### Themes built with this tool

*(Red lines are only to redact my location info.)*

<img width="1920" height="1080" alt="Built theme 1" src="https://github.com/user-attachments/assets/f5f6287b-b852-47b7-b895-d5caefea5c19" />

<img width="1920" height="1080" alt="Built theme 2" src="https://github.com/user-attachments/assets/118ba01f-0a36-4127-9577-2fe80bac97aa" />

<img width="1920" height="1080" alt="Built theme 3" src="https://github.com/user-attachments/assets/981eaf50-5f37-4c21-8644-e39901bf60ce" />
