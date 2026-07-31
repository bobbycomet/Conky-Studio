# Conky Studio

**2 nodes = 1 widget in 30 seconds. Start simple. Scale to anything.**

<div align="center">

<img width="300" height="300" alt="Conky Studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

**Design desktop HUDs visually. Ship real Conky themes.**

No sudo. No package installers. If your distro runs AppImages and Conky, you can run Conky Studio. Optional nodes use existing Linux tools like playerctl and lm-sensors when available.

**Live preview = export.** Same pipeline. Not a mockup.

## Acknowledgments & Disclaimer

This project is an independent tool designed to generate and manage HUDs for [Conky](https://github.com/brndnmtthws/conky). 

>**Please note:** This project is not affiliated with, endorsed by, or sponsored by the official Conky project or its maintainers. Conky is licensed under the GPL-3.0 License.

Public release planned for **August 1st 2026**.

[Video Showcase](https://youtu.be/RbUr9pFosDc) · [Discord](https://discord.gg/kJZCZWg5nw) · [YouTube](https://www.youtube.com/@BobbyComet) · [WIKI](https://github.com/bobbycomet/Conky-Studio/wiki)

</div>

---

## Why this exists

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

- Converts conf settings, TEXT layout (best-effort), common `${…}` sources, images, known scripts, and Cairo Lua into **Custom Lua** nodes  
- Does **not** reverse-engineer arbitrary Cairo into Arc/Bar nodes  
- `${if_…}` is simplified; layout from pure TEXT is approximate  

Warnings list every compromise. Then you edit and **build** like any native project; preview and export stay **1:1** for what’s on the canvas.

---

## Status

**Actively developed.** Core editor, live preview, manager, codegen, wizard, plugins, importer, gradients, studio tour, and support links are in place.

**Community-driven (maybe):** animation keyframes, built-in profiler; depends on feedback.

---

## Requirements

**Conky Studio** (AppImage) does not need sudo or a package manager.  
**Conky** (and a few optional tools) come from your system.

### Required

| Component | Why |
|-----------|-----|
| **Conky** | Live Preview and every built theme run `conky` |
| **Graphical session** | X11, or Wayland on a supported compositor (see Compatibility wiki) |

Check Conky:

```
conky -v
```

On Wayland, prefer a build that lists Wayland in that output. Some distro packages are X11-only.

- lm-sensorsCPU/board temperature sources 
- playerctlMusic/now-playing nodes 
- curl Weather and some scripted sourcesfonts you use in themes
- Avoid fallback typefaces on other machines

## Debian/Ubuntu/Linux Mint/Pop!_OS (apt)

### Required
```
sudo apt update
sudo apt install conky-all
```
### Optional
```
sudo apt install lm-sensors playerctl curl
sudo sensors-detect   # once; follow prompts for hardware sensors
```
## Fedora (dnf)

### Required
```
sudo dnf install conky
```
### Optional
```
sudo dnf install lm_sensors playerctl curl
sudo sensors-detect
```

## RHEL/CentOS Stream/Alma/Rocky (dnf)

### Required (EPEL often needed for conky)
```
sudo dnf install epel-release
sudo dnf install conky
```
### Optional
```
sudo dnf install lm_sensors playerctl curl
sudo sensors-detect
```

## openSUSE Leap/Tumbleweed (zypper)

### Required
```
sudo zypper install conky
```
### Optional
```
sudo zypper install sensors playerctl curl
sudo sensors-detect
```

## Arch Linux / Manjaro / EndeavourOS (pacman)

### Required
```
sudo pacman -S conky
```
### Optional
```
sudo pacman -S lm_sensors playerctl curl
sudo sensors-detect
```

## Void Linux (xbps)

### Required
```
sudo xbps-install -S conky
```
### Optional
```
sudo xbps-install -S lm_sensors playerctl curl
```

## Gentoo (emerge)

### Required. Enable the USE flags you need (e.g. wayland, X, lua)
```
sudo emerge --ask app-admin/conky
```
### Optional
```
sudo emerge --ask sys-apps/lm-sensors media-sound/playerctl net-misc/curl
sudo sensors-detect
```

## Alpine (apk)

### Required
```
sudo apk add conky
```

### Optional
```
sudo apk add lm-sensors playerctl curl
```

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

<img width="1920" height="1080" alt="Starter theme A" src="https://github.com/user-attachments/assets/355aba42-f244-4225-9fa4-ae8d6817c003" />

<img width="1920" height="1080" alt="Starter theme B" src="https://github.com/user-attachments/assets/03cc075f-5add-44d2-a444-de7b1604b045" />

### Themes built with this tool

*(Red lines are only to redact my location info.)*

<img width="1920" height="1080" alt="Built theme 1" src="https://github.com/user-attachments/assets/f5f6287b-b852-47b7-b895-d5caefea5c19" />

<img width="1920" height="1080" alt="Built theme 2" src="https://github.com/user-attachments/assets/118ba01f-0a36-4127-9577-2fe80bac97aa" />

<img width="1920" height="1080" alt="Built theme 3" src="https://github.com/user-attachments/assets/981eaf50-5f37-4c21-8644-e39901bf60ce" />
