# Conky Studio

<div align="center">
  <img width="300" height="300" alt="Conky Studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

## **Design Conky HUDs visually. Ship real themes.**

**2 nodes = 1 widget in 30 seconds.**
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
[![Download Latest Build](https://img.shields.io/badge/Download_Latest_Build-2ea44f?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/releases)
[![Conky Studio History](https://img.shields.io/badge/Conky_Studio_History-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Conky-Studio-History)
[![Features](https://img.shields.io/badge/Features-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Features)
[![KOFI](https://img.shields.io/badge/KO-FI-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://ko-fi.com/bobby60908)

</div>

### **1.1.0 — Architectural Release**

**1.1.0 isn't Conky Studio becoming a different application. It's Conky Studio becoming the application it was designed to be.**

This release completes the original Studio architecture rather than replacing it. The node graph is still the foundation; 1.1.0 builds the surrounding UX needed to make that architecture practical from creation through preview, packaging, export, installation, and reuse.

The result is a more complete authoring environment without abandoning the design that has powered Studio from the beginning.

**1.1.0 highlights**
- Multi-window / multi-monitor projects with shared data and per-window scenes
- Portable `.cstudio` source packages with bundled project assets
- Position Stage built directly on Studio's existing X/Y property system
- Scale % for uniform visual scaling
- Expanded Cairo visuals and effects
- Theme Vault + Node Vault
- Simple / Full / Showcase Theme Wizard
- 1.0.x-compatible project migration
- Guided learning tours
- Plugin Creation: promote Custom Nodes into validated, portable plugins
- A complete theme lifecycle from authoring → preview → build → install → manage
- Use Studio as the editor, use any manager, even if it is not Studio's

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
**Make Conky as easy to design as it is powerful to run.**

- No Lua editing (unless you want to)
- No restart loops
- No fake previews (real Conky process refreshes as you edit)
- Advanced options for power users
- Build simple, or build something complex

[![Getting Started](https://img.shields.io/badge/Getting-Started-2ea44f?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Getting-Started)

---

## What makes this different

Conky Studio is a **visual authoring tool for Conky**, not a replacement runtime.

Your designs are converted into normal Conky files:

- `conky.conf`
- `render.lua`
- `start.sh`
- custom scripts
- assets and resources

Exported themes run independently using Conky’s normal pipeline.

**Live preview = export.**  
The preview uses the same build path as the final theme — what you see is what you ship.

### How Conky Studio Compares

| Capability | Raw Lua/Text Editing | Conky Manager | **Conky Studio** |
| :--- | :---: | :---: | :---: |
| **Visual Node Authoring** | None | None | **Yes (Sources → Logic → Visuals)** |
| **Real Process Live Preview** | Manual terminal reloads | None | **Yes (~350 ms feedback)** |
| **Multi-monitor / Multi-window** | Manual | Limited | **Yes (separate processes + scene filters)** |
| **Portable Projects** | None | None | **Yes (`.cstudio` packages)** |
| **Procedural Animation (PAS)** | Hand-coded Cairo | None | **Yes (Sensor rate, Draw FPS, Smooth nodes)** |
| **Theme Lifecycle Manager** | Manual | Basic toggle | **Yes (Start/Stop, Zip, Duplicate, monitor pin)** |
| **No Runtime Lock-In** | Native | Native | **Yes (standard Conky output)** |
| **Plugin Ecosystem** | None | None | **Yes (Node Vault + local creation)** |
| **Theme Wizard** | None | None | **Yes (learning + starter graphs)** |
| **Community Stores** | None | Limited | **Yes (Theme Vault + Node Vault)** |

---

## Create your first widget in 30 seconds

1. Drop a **CPU** source  
2. Drop a **gauge**, **bar**, or **text** node  
3. Connect them  
4. Enable live preview  

That is a real Conky widget, not a mockup.

[![Creating your first widget](https://img.shields.io/badge/Creating_your_first_widget-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=BhB6O_jakxo)

From there you can build complete HUDs with:

- Logic chains and smoothing
- Gradients and Scale %
- Multi-window layouts
- Custom scripts and Custom Lua
- 98+ built-in nodes + community plugins
- Newest decorative nodes: holographic globe, holographic DNA strand, morphing neon geometry

Check [![Requirements](https://img.shields.io/badge/Requirements-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Requirements) and [![Compatibility](https://img.shields.io/badge/Compatibility-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Compatibility) to get started.

### Core Features (1.1.0)

- **Visual node editor** — Sources → Logic → Visuals  
- **Position Stage** — drag visual proxies on a true window-sized plane  
- **Scale %** — uniform scaling of geometry, text, strokes, and images  
- **Live Preview** — real Conky process  
- **Multi-window / multi-monitor** — each window is an independent Conky process with optional scene filters  
- **`.cstudio` projects** — portable packages containing the graph, assets, and fonts  
- **Theme Wizard** — Simple / Full / Showcase complexity tiers  
- **Theme Manager** — Start/Stop, install, duplicate, export, monitor pinning  
- **Theme Vault** — community theme catalog  
- **Node Vault** — community plugin catalog  
- **Plugin Creation tool** — turn Custom Lua / Custom Script into distributable plugins  
- **Legacy importer** — convert existing themes into editable graphs  
- **Guided tours** — Learn Studio, Theme Wizard, and Full Tour  
- **Clean exports** — standard Conky theme folders that run without Studio  

Combine with the [![Griffin Updater](https://img.shields.io/badge/Griffin_Updater-2ea44f?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/GriffinUpdater) for auto-updates.

---

## Community Stores

| Store | Purpose | Link |
|-------|---------|------|
| **Theme Vault** | Browse and install community themes | [Theme Community Store](https://bobbycomet.github.io/Conky-Studio-Theme-Community-Store/#/) |
| **Node Vault** | Browse and install community plugins | [Community Plugins](https://bobbycomet.github.io/Conky-Studio-Community-Plugins/#/) |

Both stores are also available inside Conky Studio (Store tab and Tools → Plugins).

---

## How to install

[![Download Latest Build](https://img.shields.io/badge/Download_Latest_Build-2ea44f?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/releases)

### Installation & Running

Full guide and dependencies:  
[![Installation](https://img.shields.io/badge/Installation-5865F2?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Getting-Started)

Before running the AppImage, make it executable:

#### Option 1: Terminal (Recommended)
```bash
chmod +x Conky-Studio-*.AppImage
./Conky-Studio-*.AppImage
```

#### Option 2: GUI
- Right-click the AppImage → Properties  
- Permissions tab → “Allow executing file as program”  
- Double-click to run  

Source releases include the full tree. Place the `packaging` folder inside the `conkystudio` directory when building from source.

---

### Screenshots

| Studio | Live Preview | Theme Manager | Starter Theme |
|:------:|:------------:|:-------------:|:-------------:|
| <img src="screenshots/studio.png" width="180"> | <img src="screenshots/live_preview.png" width="180"> | <img src="screenshots/theme_manager.png" width="180"> | <img src="screenshots/starter_theme.png" width="180"> |
| Gamer Theme | Colour | Speed | Undocking |
|:-----------:|:------:|:-----:|:---------:|
| <img src="screenshots/starter_theme_gamer.png" width="180"> | <img src="screenshots/colour.png" width="180"> | <img src="screenshots/speed.png" width="180"> | <img src="screenshots/undocking.png" width="180"> |

### Current Official Compatible Themes
*Click an image, download the zip, drop into Manager*

| Skyrim Vanilla | Skyrim Parchment | CorePulse | Batman |
|:--------------:|:----------------:|:---------:|:------:|
| <a href="https://www.opendesktop.org/p/2287070/"><img src="screenshots/skyrin_vanilla_preview.png" width="180"></a> | <a href="https://www.opendesktop.org/p/2366029/"><img src="screenshots/skyrim_parchment_preview.png" width="180"></a> | <a href="https://www.opendesktop.org/p/2367501/"><img src="screenshots/preview.png" width="180"></a> | <a href="https://www.opendesktop.org/p/2366693/"><img src="screenshots/batman.png" width="180"></a> |

---

## Theme Compatibility

The Manager runs any Conky theme that provides a working `start.sh` (or lets Studio generate a minimal one). This includes:

- Themes created with Conky Studio  
- Manually written Conky themes  
- Third-party themes from Pling / openDesktop / GitHub  

Studio does **not** need to stay open after you Start a theme.  
You can also launch manually:

```bash
cd ~/.config/conky/<theme-folder>
./start.sh
```

See [![Theme Compatibility](https://img.shields.io/badge/Theme_Compatibility-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Theme-Compatibility).

---

## DE Compatibility

Full details: [![Compatibility](https://img.shields.io/badge/Compatibility-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki/Compatibility)

**GLIBC 2.38+** is required for the AppImage.

| Environment | Notes |
|-------------|--------|
| **X11** (any WM) | Most predictable |
| **Sway / Hyprland / other wlroots** | Layer-shell supported |
| **KDE Plasma (Wayland)** | Supported path |
| **GNOME Wayland (Mutter)** | Limited — no reliable desktop overlays |

Live Preview intentionally uses `normal` window type. Final exported themes follow the window type you set (auto / desktop / dock).

---

## Runtime Performance

Conky Studio is an authoring tool. The node graph is converted into ordinary Conky files at build time. The exported theme runs independently of Studio. Performance is determined by the generated Lua, update intervals, and normal Conky execution — not by the number of nodes in the editor.

---

## Built for Conky, not a replacement or fork

Conky Studio is an independent project that generates and manages HUDs for [Conky](https://github.com/brndnmtthws/conky). It is not affiliated with, endorsed by, or sponsored by the official Conky project.

> **IMPORTANT:** Report Conky Studio bugs to the Conky Studio project, **not** to the Conky maintainers.

If an exported theme fails outside Studio, test it directly:

```bash
./start.sh
```

---

## Continue exploring

- [Sharing Projects & JSON](https://github.com/bobbycomet/Conky-Studio/wiki/Sharing-Projects-&-JSON)  
- [Position Stage](https://github.com/bobbycomet/Conky-Studio/wiki/Position-Stage)  
- [Scale Percent](https://github.com/bobbycomet/Conky-Studio/wiki/Scale-Percent)  
- Architecture, Nodes, Legacy Import, Requirements, Starter Themes  

Full technical documentation: [![Wiki](https://img.shields.io/badge/Wiki-1f6feb?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bobbycomet/Conky-Studio/wiki)
