"""
Project -> standalone theme directory.

This is the one function the rest of the app (Studio's Build & Run,
Live Preview, and the Manager's "Export" action) all call through. Its
output is deliberately just files on disk in the standard layout -- once
BuildResult.output_dir exists, Conky Studio's job is done; `start.sh` in
that folder runs the HUD with no Conky-Studio process involved at all.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field

from conkystudio.model.project import Project
from conkystudio.model.theme_meta import ThemeMeta
from conkystudio.nodes import registry
from conkystudio.codegen import lua_gen, conky_conf_gen, shell_gen, start_sh_gen
from conkystudio.hardware import discovery
from conkystudio.plugins import loader as plugin_loader

_FAMILY_GENERATORS = {
    "cpu_sensors": shell_gen.gen_cpu_sensors_script,
    "gpu_stats": shell_gen.gen_gpu_stats_script,
    "disk_sensors": shell_gen.gen_disk_sensors_script,
    "fan_sensors": shell_gen.gen_fan_sensors_script,
    "public_ip": shell_gen.gen_public_ip_script,
    "weather": shell_gen.gen_weather_script,
    "nowplaying": shell_gen.gen_nowplaying_script,
}


@dataclass
class BuildResult:
    output_dir: str
    warnings: list = field(default_factory=list)
    conky_conf_path: str = ""
    render_lua_path: str = ""
    start_sh_path: str = ""


def _used_source_nodes(project: Project) -> list:
    used_ids = {e.src_node for e in project.edges}
    return [n for n in project.nodes if n.id in used_ids and registry.get(n.type).category == "source"]


def _families_needed(project: Project) -> dict:
    """family_key -> {'daemon': bool, 'execi': bool} -- a family can be
    needed in both modes at once if two different node instances in it
    picked different polling modes; the builder just writes what each
    mode needs rather than picking one."""
    out: dict[str, dict] = {}
    for n in _used_source_nodes(project):
        spec = registry.get(n.type)
        if spec.script_family is None:
            continue  # native sources need no script; custom_script handled separately
        mode = n.props.get("poll_mode", "execi")
        entry = out.setdefault(spec.script_family, {"daemon": False, "execi": False})
        entry[mode] = True
    return out


def build_project(
    project: Project,
    output_dir: str,
    source_search_dirs: list | None = None,
    *,
    for_preview: bool = False,
) -> BuildResult:
    """source_search_dirs: extra directories to look in when a PATH
    property (image/custom script) is a bare filename rather than an
    absolute path already resolved by the UI -- the Studio always passes
    absolute paths, this is mainly a convenience for headless/test use.

    for_preview=True (Live Preview only): force own_window_type=normal and
    never emit xinerama_head. Desktop/dock types and mismatched xinerama
    indices are a common source of X BadWindow (error_code 3) / exit 6 when
    Conky is launched as a short-lived preview process next to the Studio.
    """
    lua_gen.assert_full_coverage()
    warnings: list = []
    search_dirs = list(source_search_dirs or [])
    # .cstudio packages store assets under package_root with relative paths
    # in the graph — always search that tree when present.
    pkg_dirs = []
    try:
        pkg_dirs = list(project.search_dirs() or [])
    except Exception:
        pkg_dirs = []
    for d in pkg_dirs:
        if d and d not in search_dirs:
            search_dirs.append(d)

    scripts_dir = os.path.join(output_dir, "scripts")
    images_dir = os.path.join(output_dir, "images")
    assets_dir = os.path.join(output_dir, "assets")
    fonts_dir = os.path.join(output_dir, "fonts")
    for d in (output_dir, scripts_dir, images_dir, assets_dir, fonts_dir):
        os.makedirs(d, exist_ok=True)

    script_filenames: dict = {}

    # ---- family scripts (cpu/gpu/disk/weather), whichever modes are used
    for family_key, modes in _families_needed(project).items():
        gen_fn = _FAMILY_GENERATORS.get(family_key)
        if gen_fn is None:
            warnings.append(f"No script generator registered for family '{family_key}' -- skipped.")
            continue
        content = gen_fn(project)
        filename = f"{family_key}.sh"
        _write_executable(os.path.join(scripts_dir, filename), content)
        script_filenames[family_key] = filename

    # ---- custom script nodes (one per instance, not shared)
    # Include EVERY custom_script node, not only ones with an outgoing
    # edge. Legacy imports leave sensors.sh / weather.sh unwired: the
    # Custom Lua reads their cache files directly, so the script must
    # still be copied and (in daemon mode) polled by start.sh even
    # though nothing in the graph "listens" to SRC[id].
    custom_nodes = [n for n in project.nodes if n.type == "source.custom_script"]
    for n in custom_nodes:
        src_path = _resolve_path(n.props.get("script_path", ""), search_dirs)
        body = (n.props.get("script_body") or "").strip()
        # Self-caching scripts (sensors.sh / weather.sh from Batman, Skyrim,
        # etc.) write their own CACHE_FILE under .runtime-cache and are read
        # directly by Custom Lua. Run them under their original basename with
        # no stdout-capture wrapper so the cache name the Lua expects stays
        # intact (sensors.cache, weather.cache, …).
        is_self_caching = bool(n.props.get("self_caching"))
        if not is_self_caching and (body or (src_path and os.path.isfile(src_path))):
            probe = body
            if not probe and src_path and os.path.isfile(src_path):
                try:
                    with open(src_path, "r", encoding="utf-8", errors="replace") as fh:
                        probe = fh.read(8000)
                except OSError:
                    probe = ""
            if re.search(r'CACHE_FILE\s*=|sensors\.cache|weather\.cache', probe or ""):
                is_self_caching = True

        preferred_name = (
            n.props.get("script_basename")
            or (os.path.basename(src_path) if src_path else "")
            or f"custom_{n.id}.sh"
        )
        if not preferred_name.endswith((".sh", ".bash")):
            preferred_name = f"{preferred_name}.sh"

        if body:
            # Inline body wins over path (Properties-panel edit of a legacy import).
            dest_name = preferred_name if is_self_caching else f"custom_{n.id}_inner.sh"
            _write_executable(os.path.join(scripts_dir, dest_name), body if body.startswith("#!") else "#!/usr/bin/env bash\n" + body)
            inner_filename = dest_name
            # Copy companion .conf next to it when the importer recorded one.
            for conf_key in ("companion_conf", "conf_path"):
                conf_src = n.props.get(conf_key)
                if conf_src and os.path.isfile(str(conf_src)):
                    conf_dest = os.path.join(scripts_dir, os.path.basename(conf_src))
                    try:
                        shutil.copy2(conf_src, conf_dest)
                    except OSError:
                        pass
        elif not src_path or not os.path.isfile(src_path):
            warnings.append(f"Custom Script node '{n.label or n.id}' points at a missing file "
                             f"({n.props.get('script_path', '(none)')!r}) -- it will read blank until fixed.")
            inner_filename = f"custom_{n.id}_inner.sh"
            _write_executable(os.path.join(scripts_dir, inner_filename), "#!/usr/bin/env bash\necho ''\n")
        else:
            if is_self_caching:
                inner_filename = preferred_name
                shutil.copy2(src_path, os.path.join(scripts_dir, inner_filename))
                os.chmod(os.path.join(scripts_dir, inner_filename), 0o755)
                # Companion conf (sensors.conf / weather.conf) sits beside the script.
                src_dir = os.path.dirname(src_path)
                for conf_name in (preferred_name.replace(".sh", ".conf"), "sensors.conf", "weather.conf"):
                    conf_src = os.path.join(src_dir, conf_name)
                    if os.path.isfile(conf_src):
                        try:
                            shutil.copy2(conf_src, os.path.join(scripts_dir, conf_name))
                        except OSError:
                            pass
                # Also honour an explicit path recorded by the importer.
                for conf_key in ("companion_conf", "conf_path"):
                    conf_src = n.props.get(conf_key)
                    if conf_src and os.path.isfile(str(conf_src)):
                        try:
                            shutil.copy2(conf_src, os.path.join(scripts_dir, os.path.basename(conf_src)))
                        except OSError:
                            pass
            else:
                inner_filename = f"custom_{n.id}_inner{os.path.splitext(src_path)[1] or '.sh'}"
                shutil.copy2(src_path, os.path.join(scripts_dir, inner_filename))
                os.chmod(os.path.join(scripts_dir, inner_filename), 0o755)

        if is_self_caching:
            # Run the real script directly; it manages its own cache file.
            script_filenames[n.id] = inner_filename
        elif n.props.get("poll_mode", "execi") == "daemon":
            wrapper = shell_gen.gen_custom_script_wrapper(n.id, inner_filename)
            wrapper_filename = f"custom_{n.id}.sh"
            _write_executable(os.path.join(scripts_dir, wrapper_filename), wrapper)
            script_filenames[n.id] = wrapper_filename
        else:
            script_filenames[n.id] = inner_filename

    # ---- source-plugin nodes (one script per instance, same execi/daemon
    # wiring as source.custom_script above -- see NodeSpec.scripted and
    # plugins/loader.render_plugin_source_script)
    #
    # registry.has() first: unlike a built-in node type, a source plugin's
    # type can vanish out from under a saved project if its plugin gets
    # uninstalled (registry.unregister() drops the NodeSpec entirely) --
    # registry.get() on a missing type raises KeyError, which would abort
    # the whole build over one orphaned node instead of just warning about
    # it the way render_plugin_source_script()'s own "not loaded" check
    # already does a few lines below.
    plugin_source_nodes = []
    for n in project.nodes:
        if not registry.has(n.type):
            warnings.append(
                f"Node '{n.label or n.id}' ({n.type}) isn't a known node type -- "
                f"its plugin may have been uninstalled. Skipped."
            )
            continue
        spec = registry.get(n.type)
        if spec.category == "source" and getattr(spec, "scripted", False) and n.type != "source.custom_script":
            plugin_source_nodes.append(n)
    for n in plugin_source_nodes:
        body = plugin_loader.render_plugin_source_script(n)
        if body is None:
            warnings.append(
                f"Source plugin node '{n.label or n.id}' ({n.type}) isn't loaded -- "
                f"it will read blank until its plugin is installed again."
            )
            continue
        inner_filename = f"custom_{n.id}_inner.sh"
        _write_executable(os.path.join(scripts_dir, inner_filename), body)
        if n.props.get("poll_mode", "execi") == "daemon":
            wrapper = shell_gen.gen_custom_script_wrapper(n.id, inner_filename)
            wrapper_filename = f"custom_{n.id}.sh"
            _write_executable(os.path.join(scripts_dir, wrapper_filename), wrapper)
            script_filenames[n.id] = wrapper_filename
        else:
            script_filenames[n.id] = inner_filename

    # ---- album art nodes (one per instance, always daemon-mode -- see
    # start_sh_gen.daemon_families_used, which also looks for these)
    for n in project.nodes:
        if n.type != "visual.album_art":
            continue
        fallback = _resolve_path(n.props.get("fallback_path", ""), search_dirs) if n.props.get("fallback_path") else ""
        if n.props.get("fallback_path") and not fallback:
            warnings.append(f"Album Art node '{n.label or n.id}' has a fallback image set that wasn't "
                             f"found ({n.props.get('fallback_path')!r}) -- ignored.")
        script = shell_gen.gen_album_art_script(n.id, n.props.get("player", "spotify"), fallback)
        filename = f"album_art_{n.id}.sh"
        _write_executable(os.path.join(scripts_dir, filename), script)
        script_filenames[n.id] = filename

    # ---- images referenced by Image/Icon / Glow / etc. + Custom Lua assets
    for n in project.nodes:
        if registry.get(n.type).category != "visual":
            continue
        # PATH props on any visual (Image/Icon, Glow silhouette, swaps, …)
        for key in ("path", "swap_above_path", "swap_below_path", "fallback_path"):
            p = n.props.get(key)
            if not p:
                continue
            resolved = _resolve_path(p, search_dirs)
            if not resolved or not os.path.isfile(resolved):
                warnings.append(f"'{n.label or n.id}' references image '{p}' which wasn't found -- "
                                 f"that element will be skipped at draw time.")
                continue
            dest = os.path.join(images_dir, os.path.basename(resolved))
            if not os.path.exists(dest):
                shutil.copy2(resolved, dest)
        # Legacy-imported Custom Lua: asset_paths is a list of absolute files.
        # Copy into assets/ (what rewritten Lua expects via ASSETS_DIR /
        # THEME_DIR .. '/assets/') AND images/ (Studio Image/Glow nodes).
        for p in (n.props.get("asset_paths") or []):
            resolved = _resolve_path(p, search_dirs)
            if not resolved or not os.path.isfile(resolved):
                warnings.append(f"Custom Lua asset '{p}' wasn't found -- that image will be missing at draw time.")
                continue
            base = os.path.basename(resolved)
            for dest_dir in (assets_dir, images_dir):
                dest = os.path.join(dest_dir, base)
                if not os.path.exists(dest):
                    shutil.copy2(resolved, dest)

    # ---- ensure windows (legacy projects → single primary window)
    windows = project.ensure_windows()
    project.sync_canvas_from_primary()
    enabled_windows = project.enabled_windows()
    primary = project.primary_window()

    # ---- render.lua (shared full graph) + optional per-window filtered scenes
    header = f"-- {project.name} -- generated by Conky Studio, do not hand-edit"
    render_lua = lua_gen.build_render_lua(project, script_filenames, header_comment=header)
    render_lua_path = os.path.join(output_dir, "render.lua")
    with open(render_lua_path, "w", encoding="utf-8") as f:
        f.write(render_lua)

    # ---- conky.conf (+ conky_<id>.conf for extra windows)
    session = discovery.detect_session()
    monitors = discovery.detect_monitors()
    conf_paths: list[str] = []
    primary_conf_path = ""
    # canvas_ext plugins are process-wide tuning knobs (see
    # plugins/schema.CANVAS_EXT_ALLOWED_KEYS) -- applied identically to
    # every window's conf, same as the fixed core settings.
    canvas_ext_directives = plugin_loader.resolve_canvas_ext_directives(project)

    for win in sorted(enabled_windows, key=lambda w: (w.z, w.id)):
        is_primary = win.id == primary.id
        if for_preview:
            # Preview must stay as a normal floating window; desktop/dock
            # attach to the root window and often throw X BadWindow when the
            # Studio is also on the same display.
            resolved_wt = "normal"
        else:
            resolved_wt = discovery.resolve_window_type(win.window_type, session)
        # xinerama_head only when the user explicitly picked a concrete output
        # AND this is not a Live Preview build. "auto" / "primary" omit it —
        # same as the pre-multi-window path. Forcing a head for auto (or using
        # xrandr order as Conky's index) caused X BadWindow / exit 6 on some
        # multi-monitor setups.
        xinerama_head = None
        monitor_note = ""
        mon_req = (getattr(win, "monitor", None) or "auto").strip()
        if not for_preview and mon_req not in ("", "auto", "primary"):
            resolved_name = discovery.resolve_monitor_name(mon_req, monitors)
            if resolved_name:
                for idx, mon in enumerate(monitors):
                    if mon.name == resolved_name and mon.name not in ("", "auto"):
                        xinerama_head = idx
                        monitor_note = f"Pinned to monitor {mon.summary()}"
                        break
            if xinerama_head is None:
                monitor_note = (
                    f"Monitor '{mon_req}' requested but not found at build time — "
                    "using alignment/gap only."
                )
                warnings.append(monitor_note)

        # Per-window scene: non-empty visible_node_ids → filtered render_<id>.lua
        vids = [str(i) for i in (getattr(win, "visible_node_ids", None) or []) if i]
        lua_basename = "render.lua"
        if vids:
            safe = "".join(ch if ch.isalnum() else "_" for ch in win.id).strip("_") or "extra"
            lua_basename = f"render_{safe}.lua"
            filtered = lua_gen.build_render_lua(
                project, script_filenames,
                header_comment=header + f" (window {win.id} scene filter)",
                visible_node_ids=vids,
            )
            with open(os.path.join(output_dir, lua_basename), "w", encoding="utf-8") as f:
                f.write(filtered)
            if monitor_note:
                monitor_note = monitor_note + f"; scene filter {len(vids)} node(s)"
            else:
                monitor_note = f"Scene filter: {len(vids)} visual node(s)"

        conf_name = conky_conf_gen.safe_conf_basename(win, is_primary=is_primary)
        conf_body = conky_conf_gen.build_conky_conf(
            project, resolved_wt,
            wayland_note=session.warning if is_primary else "",
            window=win,
            lua_basename=lua_basename,
            xinerama_head=xinerama_head,
            monitor_note=monitor_note,
            extra_directives=canvas_ext_directives,
        )
        conf_path = os.path.join(output_dir, conf_name)
        with open(conf_path, "w", encoding="utf-8") as f:
            f.write(conf_body)
        conf_paths.append(conf_path)
        if is_primary:
            primary_conf_path = conf_path

    if not primary_conf_path and conf_paths:
        primary_conf_path = conf_paths[0]

    if session.warning:
        warnings.append(session.warning)

    if len(enabled_windows) > 1:
        warnings.append(
            f"Multi-window build: {len(enabled_windows)} Conky processes "
            f"(primary + {len(enabled_windows) - 1} extra)."
        )

    conky_conf_path = primary_conf_path

    # ---- start.sh (launches every conf under one process group)
    start_sh = start_sh_gen.build_start_sh(
        project, script_filenames,
        conf_basenames=[os.path.basename(p) for p in conf_paths],
    )
    start_sh_path = os.path.join(output_dir, "start.sh")
    _write_executable(start_sh_path, start_sh)

    # ---- theme.json (resolution = primary window; preserves single-monitor tooling)
    pw = primary
    meta = ThemeMeta(
        name=project.name, author=project.author, description=project.description,
        resolution=f"{pw.width}x{pw.height}",
        requires=["lua-cairo"] + (
            ["curl"] if _families_needed(project).get("weather") or _families_needed(project).get("public_ip")
            else []
        ),
        created_with="conky-studio",
    )
    # Optional bookkeeping for multi-window themes (ignored by older readers)
    meta_path = os.path.join(output_dir, "theme.json")
    meta.save(meta_path)
    try:
        import json as _json
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta_dict = _json.load(fh)
        meta_dict["windows"] = [
            {
                "id": w.id,
                "name": w.name,
                "monitor": w.monitor,
                "resolution": f"{w.width}x{w.height}",
                "conf": conky_conf_gen.safe_conf_basename(w, is_primary=(w.id == primary.id)),
                "enabled": w.enabled,
            }
            for w in enabled_windows
        ]
        with open(meta_path, "w", encoding="utf-8") as fh:
            _json.dump(meta_dict, fh, indent=2)
            fh.write("\n")
    except Exception:
        pass

    # ---- README
    _write_readme(output_dir, project, warnings)

    return BuildResult(
        output_dir=output_dir, warnings=warnings,
        conky_conf_path=conky_conf_path, render_lua_path=render_lua_path, start_sh_path=start_sh_path,
    )


def _write_executable(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(path, 0o755)


def _resolve_path(p: str, search_dirs: list) -> str:
    if not p:
        return ""
    if os.path.isabs(p) and os.path.isfile(p):
        return p
    for d in search_dirs:
        cand = os.path.join(d, p)
        if os.path.isfile(cand):
            return cand
    return p if os.path.isfile(p) else ""


def _write_readme(output_dir: str, project: Project, warnings: list) -> None:
    lines = [
        f"# {project.name}",
        "",
        project.description or "_No description._",
        "",
        "Built with Conky Studio. To run without the app:",
        "",
        "```",
        "./start.sh",
        "```",
        "",
        "To install permanently, drop this whole folder into `~/.config/conky/` and launch",
        "`start.sh` from there (or use Conky Studio's Manager tab, which does this for you).",
    ]
    if warnings:
        lines += ["", "## Build warnings", ""]
        lines += [f"- {w}" for w in warnings]
    with open(os.path.join(output_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

