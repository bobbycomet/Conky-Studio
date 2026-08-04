# Conky Studio

<div align="center">

<img width="300" height="300" alt="Conky Studio" src="https://github.com/user-attachments/assets/d6f92f00-e4f5-4b0a-a715-138f20a46458" />

## **Design Conky HUDs visually. Ship real themes.**

**2 nodes = 1 widget in 30 seconds.**
Start simple. Scale to anything.

</div>

<p align="center">
  <img src="node.gif" alt="Conky Studio Node Demo" width="50%">
</p>

<div align="center">

**No mockups. No fake canvas. No runtime lock-in.**

Build desktop HUDs visually with a node-based workflow, then export standard Conky themes that run without Conky Studio.

[Video Showcase](https://www.youtube.com/watch?v=ys-cg211jsE) · [Discord](https://discord.gg/kJZCZWg5nw) · [YouTube](https://www.youtube.com/@BobbyComet) · [Wiki](https://github.com/bobbycomet/Conky-Studio/wiki) · [Latest Build](https://github.com/bobbycomet/Conky-Studio/releases/download/v1.0.3/Conky-Studio-1.0.3_x86_64.AppImage) · [Conky Studio History](Conky-Studio-History)

</div>

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

---

## Why this exists

Conky is extremely powerful, but creating advanced HUDs traditionally means:

| Traditional workflow                         | Conky Studio                            |
| -------------------------------------------- | --------------------------------------- |
| Edit Lua → restart → repeat                  | Change properties and preview instantly |
| Manually position `${goto}` and drawing code | Arrange elements visually               |
| Connect scripts by hand                      | Use sources as nodes                    |
| Risk breaking existing themes                | Import, edit, and rebuild safely        |

The goal is simple:

> Make Conky as easy to design as it is powerful to run.

---

## Create your first widget in 30 seconds

1. Drop a **CPU** source
2. Drop a **gauge**, **bar**, or **text** node
3. Connect them
4. Enable live preview

That is a real Conky widget, not a mockup.

[Creating your first widget](https://www.youtube.com/watch?v=BhB6O_jakxo)

From there, build complete HUDs with:

* logic chains
* gradients
* custom scripts
* click actions
* Custom Lua/Cairo rendering
* 98 built-in nodes — 43 sources, 20 logic, and 35 visuals. Install the optional 56-node plugin pack (12 logic, 37 visual) for 149 total nodes.
* Check [Requirements](https://github.com/bobbycomet/Conky-Studio/wiki/Requirements) and [Compatibility](https://github.com/bobbycomet/Conky-Studio/wiki/Compatibility) to get started

Combine with the [Griffin Updater](https://github.com/bobbycomet/GriffinUpdater) for auto-updates, or force an update without going to GitHub or OpenDesktop.

---

## Features

* **Visual node editor** — sources → logic → visuals
* **Live preview** — runs a real Conky process
* **Theme manager** — manage themes in `~/.config/conky`
* **Theme wizard** — generate starter HUDs by style
* **Legacy importer (beta)** — convert existing themes into editable projects
* **Plugins** — community JSON node extensions
* **Smart system detection** — X11/Wayland, compositor, Conky build, sensors, GPU/network hints; see [Compatibility](https://github.com/bobbycomet/Conky-Studio/wiki/Compatibility) for details
* **Clean exports** — standard Conky theme folders
* **Custom Lua support** — full Cairo escape hatch when nodes are not enough


## Theme Compatibility

Conky Studio's Manager is flexible enough to run and manage any Conky theme that provides a standard `start.sh` entry script.

This includes:

* Themes created with Conky Studio
* Manually built Conky themes
* Compatible third-party themes

Conky Studio does not need to build a theme in order to manage it. If a theme has its own folder and a working `start.sh`, it can be launched, stopped, and organized through the Manager.

You can also run themes manually:

```
cd ~/.config/conky/<theme-folder>
./start.sh
```

Conky Studio acts as the manager and launcher after a theme is built; it does not need to remain open while themes are running.

See [Theme Compatibility](https://github.com/bobbycomet/Conky-Studio/wiki/Theme-Compatibility) for an example of the start.sh

---

## Runtime Performance

Conky Studio is an authoring tool, not a runtime interpreter.

The node graph is converted into normal Conky files during build. The exported theme runs independently of Studio.

Node count does not directly determine runtime performance. Performance depends on the generated Lua logic, update intervals, and normal Conky execution.

---

## Built for Conky

Conky Studio is an independent project designed to generate and manage HUDs for [Conky](https://github.com/brndnmtthws/conky).

It is not affiliated with, endorsed by, or sponsored by the official Conky project or its maintainers.

Conky is licensed under the GPL-3.0 License.

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

For the full technical documentation, see the [Wiki](https://github.com/bobbycomet/Conky-Studio/wiki).
