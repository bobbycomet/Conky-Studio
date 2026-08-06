# Conky Studio

<div align="center">

  <img width="300" height="300" alt="Conky Studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

## **Design Conky HUDs visually. Ship real themes.**

**2 nodes = 1 widget in 30 seconds.**

No Lua editing  
No restart loops  
No fake previews

Advanced options for power users

Build simple, or build something complex
</div>

<div align="center">

Design visually → export real Conky themes.

Start simple. Scale to anything.

</div>

<p align="center">
  <img src="node.gif" alt="Conky Studio Node Demo" width="50%">
</p>

<div align="center">

**No mockups. No fake canvas. No runtime lock-in.**

Build desktop HUDs visually with a node-based workflow, then export standard Conky themes that run without Conky Studio.

[![Video Showcase](https://img.shields.io/badge/Video_Showcase-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=ys-cg211jsE)
[![Discord](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/kJZCZWg5nw)
[![YouTube](https://img.shields.io/badge/YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/@BobbyComet)
[![Wiki](https://img.shields.io/badge/Wiki-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki)
[![Download Latest Build](https://img.shields.io/badge/Download_Latest_Build-2ea44f?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/releases/download/v1.0.7.1/Conky-Studio-1.0.7.1x86_64.AppImage)
[![Conky Studio History](https://img.shields.io/badge/Conky_Studio_History-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Conky-Studio-History)
[![Features](https://img.shields.io/badge/Features-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Features)
</div>

---

## Why this exists

Conky is extremely powerful, but creating advanced HUDs traditionally means:
| Traditional workflow | Conky Studio |
| -------------------------------------------- | --------------------------------------- |
| Edit Lua → restart → repeat | Change properties and preview instantly |
| Manually position `${goto}` and drawing code | Arrange elements visually |
| Connect scripts by hand | Use sources as nodes |
| Risk breaking existing themes | Import, edit, and rebuild safely |

The goal is simple:

> Make Conky as easy to design as it is powerful to run.

---

## What makes this different

Conky Studio is a **visual authoring tool for Conky**, not a replacement runtime.
Your designs are converted into normal Conky files:

* `conky.conf`
* `render.lua`
* `start.sh`
* custom scripts
* assets and resources

Exported themes run independently using Conky's normal pipeline.

**Live preview = export.**

The preview uses the same build path as the final theme, meaning what you see is what you ship.

## How Conky Studio Compares

Conky Studio isn't just a theme launcher or a simple configuration editor—it is a **complete visual IDE and management engine** for desktop HUDs.

| Capability | Raw Lua/Text Editing | Conky Manager | **Conky Studio** |
| :--- | :---: | :---: | :---: |
| **Visual Node Authoring** | None | None | **Yes (Sources → Logic → Visuals)** |
| **Real Process Live Preview** | Manual terminal reloads | None | **Yes (~350ms instant feedback)** |
| **Procedural Animation (PAS)** | Hand-coded Cairo math | None | **Yes (Sensor refresh, Draw FPS, Smooth nodes)** |
| **Theme Lifecycle Manager** | Manual file moving |  Basic toggle | **Yes (Start/Stop, Zip, Duplicate)** |
| **No Runtime Lock-In** |  Native |  Native | **Yes (Exports standard Conky)** |
| **Plugin Ecosystem** | None | None | **Yes (`plugin.json` with a `manifest.json` store planned)** |

---

## Create your first widget in 30 seconds

1. Drop a **CPU** source
2. Drop a **gauge**, **bar**, or **text** node
3. Connect them
4. Enable live preview

That is a real Conky widget, not a mockup.

[![Creating your first widget](https://img.shields.io/badge/Creating_your_first_widget-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=BhB6O_jakxo)

From there, build complete HUDs with:

* logic chains
* gradients
* custom scripts
* click actions
* Custom Lua/Cairo rendering
* 98 built-in nodes — 43 sources, 20 logic, and 35 visuals. Install the optional 56-node plugin pack (12 logic, 37 visual) for 149 total nodes.
* Check [![Requirements](https://img.shields.io/badge/Requirements-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Requirements) and [![Compatibility](https://img.shields.io/badge/Compatibility-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Compatibility) to get started

[![Features](https://img.shields.io/badge/Features-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Features)

* **Visual node editor** — sources → logic → visuals
* **Node properties** — Resize visuals, add gradients, create CRT effects, control animation speed, move visuals, edit values, and much more.
* **Live preview** — runs a real Conky process
* **Node organization** — group, collapse, rename, and move your nodes the way you want
* **Theme manager** — manage themes in `~/.config/conky`
* **Theme wizard** — generate starter HUDs by style
* **Legacy importer (beta)** — convert existing themes into editable projects
* **Plugins** — community JSON node extensions
* **Smart system detection** — X11/Wayland, compositor, Conky build, sensors, GPU/network hints
* **Clean exports** — standard Conky theme folders
* **Custom Lua support** — full Cairo escape hatch when nodes are not enough
* **Theme preview** — on the theme manager, you will be able to see the theme via preview.png if there is one in the folder
* **Procedural Animation System (PAS)** — **Sensor refresh rate** how often values update, **Draw FPS** how often visuals redraw, and a **Smooth logic node** interpolation between states 

Combine with the [![Griffin Updater](https://img.shields.io/badge/Griffin_Updater-2ea44f?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/GriffinUpdater) for auto-updates, or force an update without going to GitHub or OpenDesktop.

---

### Screenshots

| Studio | Live Preview | Theme Manager | Starter Theme |
|:------:|:------------:|:-------------:|:-------------:|
| <img src="screenshots/studio.png" width="180"> | <img src="screenshots/live_preview.png" width="180"> | <img src="screenshots/theme_manager.png" width="180"> | <img src="screenshots/starter_theme.png" width="180"> |

| Gamer Theme | Colour | Speed | Undocking |
|:-----------:|:------:|:-----:|:---------:|
| <img src="screenshots/starter_theme_gamer.png" width="180"> | <img src="screenshots/colour.png" width="180"> | <img src="screenshots/speed.png" width="180"> | <img src="screenshots/undocking.png" width="180"> |

### Current Official Compatible Themes  
*click an image, download the zip, drop in manager*

| Skyrim Vanilla | Skyrim Parchment | CorePulse | Batman |
|:--------------:|:----------------:|:---------:|:------:|
| <a href="https://www.opendesktop.org/p/2287070/"><img src="screenshots/skyrin_vanilla_preview.png" width="180"></a> | <a href="https://www.opendesktop.org/p/2366029/"><img src="screenshots/skyrim_parchment_preview.png" width="180"></a> | <a href="https://www.opendesktop.org/p/2367501/"><img src="screenshots/preview.png" width="180"></a> | <a href="https://www.opendesktop.org/p/2366693/"><img src="screenshots/batman.png" width="180"></a> |

---

## Theme Compatibility
Conky Studio's Manager is flexible enough to run and manage any Conky theme that provides a standard `start.sh` entry script.

This includes:

* Themes created with Conky Studio
* Manually built Conky themes
* Compatible third-party themes
* Auto-generates a `start.sh` for themes without one: 1.0.7+ feature

Conky Studio does not need to build a theme in order to manage it. If a theme has its own folder and a working `start.sh`, it can be launched, stopped, and organized through the Manager. This is different from the legacy importer, as the importer is trying to make it usable and editable within the Studio and its nodes.

You can also run themes manually:
```
cd ~/.config/conky/<theme-folder>
./start.sh
```

Conky Studio acts as the manager and launcher after a theme is built; it does not need to remain open while themes are running.
See [![Theme Compatibility](https://img.shields.io/badge/Theme_Compatibility-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Theme-Compatibility) for an example of the start.sh

---

## DE Compatibility  

*Check* [![Compatibility](https://img.shields.io/badge/Compatibility-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Compatibility) *for more info*

### Likely to work (Wayland desktop overlays)

| Compositor/DE | Notes |
|-----------------|--------|
| **Sway** | Explicitly listed; wlr-layer-shell |
| **Hyprland** | Same family |
| **Wayfire, labwc, river, niri, mangowc, waybox** | Listed as layer-shell likely |
| **KDE Plasma (Wayland)** | Supported path; often uses dock-style window type |
| **Mir-based** | Listed as likely |

Requirements:

1. A **Wayland-enabled Conky** (`conky -v` should mention Wayland)

2. Session is real Wayland (`WAYLAND_DISPLAY` / `XDG_SESSION_TYPE=wayland`)

3. For overlays, prefer window type **auto** (or **desktop** / **dock** as recommended), not only for Live Preview (preview forces **normal** on purpose)

### Works, different model

| Environment | Notes |
|-------------|--------|
| **X11** (any WM: i3, openbox, XFCE, GNOME on Xorg, etc) | Most predictable; `own_window_type=normal` + undecorated/below hints |

### Unlikely/broken for desktop overlays

| Environment | Why |
|-------------|-----|
| **GNOME Wayland (Mutter)** | No wlr-layer-shell — Studio marks this as **block** |
| **Ubuntu/Unity/Budgie Wayland** (Mutter-style) | Same limitation |
| Wayland + **X11-only Conky package** | May only work poorly via XWayland 

On X11:

* normal, desktop, dock → predictable-ish

On Wayland:

* These are intent hints, not guarantees
* wlroots respects them via layer-shell
* KDE kinda maps them
* GNOME ignores half of it

Your window_type="desktop" is not a contract; it’s a best-effort strategy

Live Preview uses normal window mode intentionally.
Final exported themes may behave differently depending on your compositor.

---

## Runtime Performance
Conky Studio is an authoring tool, not a runtime interpreter.
The node graph is converted into normal Conky files during the build. The exported theme runs independently of Studio.
Node count does not directly determine runtime performance. Performance depends on the generated Lua logic, update intervals, and normal Conky execution.

---

## Built for Conky, not a replacement or fork

Conky Studio is an independent project designed to generate and manage HUDs for [![Conky](https://img.shields.io/badge/Conky-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/brndnmtthws/conky).
Conky is a free software project developed by the Conky maintainers and contributors. Conky Studio is an independent third-party tool that uses Conky as its output target.

It is not affiliated with, endorsed by, or sponsored by the official Conky project or its maintainers.
Conky is licensed under the GPL-3.0 License.

> **IMPORTANT:** If you encounter a bug with Conky Studio, please do **not** report it to the Conky developers or maintainers.
>
> The Conky team only handles issues related to the Conky project itself. Conky Studio is a separate application that generates standard Conky configuration files, Lua scripts, and related assets.
>
> Conky Studio issues should be reported to the Conky Studio project. In rare cases, Conky Studio may be affected by an upstream Conky bug, but Conky Studio does not modify or introduce bugs into the Conky codebase.
>
> If an exported theme fails when run outside Conky Studio, first verify whether the issue is with the generated files or with Conky itself. To test this, open a terminal in the exported theme directory (where `start.sh` is located) and run:
>
> ```
> ./start.sh
> ```
>
> Running the exported theme directly will provide diagnostic output that can help identify whether the problem comes from the generated files or from Conky itself.

---

## Continue exploring

The sections below cover on the wiki:

* Sharing projects
* Compatibility
* Architecture
* Nodes
* Legacy Import details
* Requirements
* Starter themes
* Built examples

For the full technical documentation, see the [![Wiki](https://img.shields.io/badge/Wiki-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki).

---

# 1.1.0 Roadmap

The 1.1.0 release focuses on expanding the Conky Studio ecosystem and scaling the core engine for complex setups.

* **Node Vault** — Community plugin distribution hub for discovering and installing custom sources, logic processors, and visual canvas nodes.
* **HUD Vault** — Integrated community sharing platform to publish, browse, and install complete Conky HUD themes in one click.
* **Source Plugins** — Author and load custom data providers via standard `manifest.json` schemas without modifying core application code.
* **Canvas Plugins** — Build custom visual extensions.
* **Native Multi-Monitor Support** — Full multi-window and multi-display layout management built into the core Studio architecture. Projects automatically migrate from single-canvas graphs into dynamic, window-based multi-scene configurations.
* **Streamlined Project Importer** — An evolution of the legacy importer. Rather than fighting edge cases in legacy code parsing, Studio imports existing Conky projects directly into your workspace, scaffolds them with helper nodes, and lets you visually wire, refine, and complete them on the canvas.
