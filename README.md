## Conky Studio: a visual system designer for desktop HUDs without the pain

<div align="center">
  
<img width="300" height="300" alt="conky-studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

</div>

## Overview

Conky is extremely powerful, but building and managing themes often means manually editing Lua, Cairo, shell scripts, and Conky configs.

**Conky Studio changes that.**

It’s a visual editor that lets you design fully functional Conky themes using a node-based workflow, without sacrificing flexibility or control.

You can build real, production-ready themes today. Public release is planned for August 1st. Showcase video coming soon.

---

## Why Conky Studio?

Build and tweak Conky themes in minutes instead of hours or days.

No more:

* restarting Conky for every small change
* digging through Lua and config files
* trial-and-error positioning

With Conky Studio, you:

* design visually
* see changes instantly
* export real, production-ready themes

This is not a mockup tool.
It generates 1:1 real Conky output.

What You Get
* Visual editing instead of manual config work
* Live preview with real Conky output
* Faster iteration (seconds instead of minutes)
* Reusable components via nodes and plugins
* Clean, structured theme exports
* Ability to import and improve existing themes

---

## Key Features

* **Visual Node Editor**
* Blueprint-style node editor
* Real-time preview (actual Conky instance)
* Logs and debugging built in
* Drag, connect, test, no restart cycle

| Task | Traditional Workflow | Conky Studio |
| :--- | :--- | :--- |
| **Adjust layout** | Edit → restart → repeat | Drag and see instantly |
| **Add widget** | Write Lua + config | Connect nodes |
| **Debug script** | Logs + guesswork | Built-in preview + logs |
| **Build complex gauge** | ~10–30 minutes | Seconds to wire |

* **Live Preview & Debugging**

Build themes using a structured node system for:

* data
* logic
* rendering

* **Theme Manager**
  Automatically detects themes in `~/.conky` and `~/.config/conky` with:

  * Previews
  * Install/export
  * Duplication
  * README editing

* **Theme Wizard**
  Generate a starter HUD instantly:

  * Categories: Minimal, Gaming, RPG, Sci-Fi, Cyberpunk, Terminal, Fantasy, Batman
  * Panels: Weather, CPU, GPU, RAM, Clock, Calendar, Music

* **Legacy Theme Importer (Beta)**
  Converts existing Conky configs into node graphs using semantic parsing.

* **Plugin System**
  Extend the app with custom nodes, generators, and tools.

* **Flexible Data Execution**
  Choose per-node:

  * `execi` mode (Conky-native polling)
  * Daemon mode (background cached scripts)

* **Custom Script Generator**
  Turn scripts into reusable nodes inside the editor.

* **Click Actions**
  Any visual node can trigger shell commands.

* **Community Store (In Progress)**
  Import themes via `.zip`, `.tar.gz`, or online sources.

---

## Compatibility Note

All themes use a standardized `start.sh` entry point.

This ensures:

* Consistent startup behavior
* Background script handling
* Cross-distro compatibility
* Fewer edge-case failures

---

## Wayland Support

Conky overlay support depends on the compositor:

**Supported:**

* wlroots-based (Sway, Hyprland, Wayfire)
* KDE Plasma (Wayland)
* Mir-based compositors

**Not Supported:**

* GNOME (Mutter), no overlay support exists

Also note:

* Some distro packages (like `conky-all` on Ubuntu/Debian) are compiled **X11-only**

Conky Studio detects your environment and warns you automatically.

---

## Current Status

**Actively in development**

### Implemented

* Visual node editor
* Live preview (real Conky instance)
* Theme manager
* Code generation
* Import/export
* Plugin framework
* Community store backend
* Theme wizard (starting points, not full themes)
* README editor
* Clickable nodes
* Logic nodes (math + conditionals)
* External + native data sources
* SVG → Cairo pipeline
* Workflow polish
* Layer/timeline editor
* Generate a theme.json with a form to fill
* Undocking floating node properties and layer docks for precision work with less UI to move around
* Save a project
* Open a project
* Build system (you can build it and save for later editing, or build and export for the manager use)

## Beta
* Legacy importer (Beta) more details below
* Music nodes with playerctl

### In Progress

* OpenDesktop integration
* Animation keyframes
* Built-in performance profiler

---

## Architecture

```
conkystudio/
├── model/        Project structure (JSON)
├── nodes/        Node definitions
├── plugins/      Community extensions
├── importer/     Legacy theme parser
├── codegen/      Theme generator
├── hardware/     System detection
├── fonts/        Font installer
├── manager/      Theme management
├── store/        Community index
├── preview/      Live Conky runner
└── ui/           PyQt6 interface
```

---

## Output Structure

```
<ThemeName>/
├── theme.json
├── start.sh
├── conky.conf
├── render.lua
├── images/
├── fonts/
├── scripts/
├── .runtime-cache/
├── preview.png
└── README.md
```

---

## Node System

### Data Sources

* CPU, RAM, Disk, Network, Uptime, System Info
* GPU stats, temps, weather, music, Custom scripts

### Logic

* Math operations
* Conditional flows
* String formatting

### Visual

* Text, gauges, bars
* Rings, spirals, glow effects,
* brackets, moon phases
* Graphs, icons, album art

### Custom scripts

* Any executable script like a weather.sh file and edit polling

More nodes are coming

### Plugins

* Extend with custom node types
* Ships with: Clamp, Temp conversion, Status indicators

---

## Legacy Importer (Beta)

Imports existing themes into node graphs by:

* Automated Node Conversion: Instantly maps variables (like ${cpu} and 
  ${mem}) into native nodes and translates ${execi} into dedicated Script nodes
* Smart Asset & Region Detection: Automatically identifies images, extracts album art, 
  and translates Lua click regions into interactive elements
* Cairo Support: Ready out-of-the-box for .conf and .lua files utilizing Cairo rendering (may need expanding for full support)

**Limitations:**

* Does NOT decompile arbitrary Cairo drawing
* Complex Lua is wrapped as a Custom Lua node
* Some conditionals are simplified

Nothing is silently dropped—everything is preserved or wrapped.

---

## Support Development

If you want to help push this further:

[GitHub Sponsors](https://github.com/sponsors/bobbycomet)
Or
[Ko-fi](https://ko-fi.com/bobby60908)

Support goes toward:

* Development time
* Features
* Documentation
* Stability improvements


---

## Vision

Conky Studio isn’t just a tool; it’s a shift from manual config hacking to **visual system design**.

The goal is simple:

> Make Conky as easy to design as it is powerful to run.

---

<img width="1920" height="1080" alt="manager" src="https://github.com/user-attachments/assets/e5ad19c9-b4ab-4eee-90df-f2dc5184966b" />
<img width="1920" height="1080" alt="nodes" src="https://github.com/user-attachments/assets/6f5ae7f5-aa81-4cec-95e5-47d84b40bade" />
<img width="1920" height="1080" alt="undocking" src="https://github.com/user-attachments/assets/3a490229-9e1b-4d62-a4cb-6f37fa93d8d1" />
<img width="1920" height="1080" alt="undocking" src="https://github.com/user-attachments/assets/d0bb0a7b-6559-4519-99b9-3bd648548275" />
<img width="1920" height="1080" alt="Screenshot_20260730_013306" src="https://github.com/user-attachments/assets/355aba42-f244-4225-9fa4-ae8d6817c003" />
<img width="1920" height="1080" alt="Screenshot_20260730_013223" src="https://github.com/user-attachments/assets/80dc01ed-28cf-4f4a-9ee4-b2673584b0f5" />
<img width="1920" height="1080" alt="Screenshot_20260730_013153" src="https://github.com/user-attachments/assets/ad03e7a1-cede-4b61-b07b-51d81366fc5a" />
<img width="1920" height="1080" alt="Screenshot_20260730_013126" src="https://github.com/user-attachments/assets/a2975d15-ae83-4eda-b73d-5591c5020837" />



## Themes I have made with this tool. If there is a red line, I was just redacting my location info.

<img width="1920" height="1080" alt="Screenshot_20260724_083124" src="https://github.com/user-attachments/assets/06c87d09-2b5a-466a-956b-00e8b84876f1" />
<img width="1920" height="1080" alt="Screenshot_20260724_181643" src="https://github.com/user-attachments/assets/118ba01f-0a36-4127-9577-2fe80bac97aa" />
<img width="1920" height="1080" alt="Screenshot_20260719_220545" src="https://github.com/user-attachments/assets/981eaf50-5f37-4c21-8644-e39901bf60ce" />
