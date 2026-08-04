"""
Loading a plugin means running Lua text someone else wrote, inside
Conky's own process, the moment you Build & Run or Live Preview a
project that uses it. That's the same trust level as installing any
theme or script from the internet -- Conky's Lua environment already has
io.popen/os.execute available (sensors.sh-style scripts rely on exactly
that), so nothing here is sandboxed beyond what Conky itself sandboxes
(which is: not much). Only add a plugin source you trust, same as a
theme. What this loader deliberately does NOT do is eval/exec any Python
from plugins.json -- a plugin entry is metadata plus a Lua text template,
substituted via plain string replacement (see _substitute below), never
interpreted as a Python format string or executed as Python code.

Improvements over the original loader:
  - Local plugin packs: ~/.config/conky-studio/plugins/*.json
  - Multi-source load (remote manifest + every local file)
  - Stricter validation (id shape, kind whitelist, placeholder coverage)
  - Optional lua_helpers block emitted once into the theme
  - Reload / list status for a Plugins settings panel
  - Explicit install (persist to installed-plugins.json) and uninstall
    (session + disk); installed plugins survive Fetch and restarts
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

from conkystudio.plugins.schema import (
    ALLOWED_CATEGORIES,
    ALLOWED_KINDS,
    ALLOWED_OUTPUT_KINDS,
    PluginManifest,
    PluginNode,
    PluginProperty,
)
from conkystudio.nodes import registry
from conkystudio.codegen import lua_gen
from conkystudio.codegen.color import lua_rgb_literal

DEFAULT_PLUGINS_URL = "https://raw.githubusercontent.com/bobbycomet/Conky-Studio/main/plugins.json"
REQUEST_TIMEOUT = 10

# User-writable packs (one JSON file = one manifest, same shape as remote)
LOCAL_PLUGINS_DIR = os.path.expanduser("~/.config/conky-studio/plugins")
# Last successful remote fetch is written here so plugins survive app restarts
# without requiring another network round-trip on every launch.
REMOTE_CACHE_FILENAME = "remote-cache.json"

# id must look like category.something or category.plugin.something
_ID_RE = re.compile(r"^(logic|visual)(\.[a-z][a-z0-9_]*)+$")

_loaded: dict[str, dict] = {}   # id -> {plugin, source}
_helpers_emitted: set[str] = set()  # plugin ids whose lua_helpers were registered
# Ids registered as plugins this session. Survives uninstall so re-install works
# even when the node registry has no unregister API (has() stays True).
_known_plugin_ids: set[str] = set()
# User-uninstalled ids (persisted). load_all / load_manifest skip these so an
# uninstall survives app restart even when the remote manifest still lists them.
_uninstalled_ids: set[str] = set()
_uninstalled_loaded: bool = False


class PluginError(Exception):
    pass


# id must look like category.something or category.plugin.something
_ICON_URL_RE = re.compile(r"^https?://\S+\.png(\?\S*)?$", re.IGNORECASE)
_ICON_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*\.png$")


def resolve_icon(plugin: PluginNode, source: str = "") -> Optional[str]:
    """Turn a plugin's ``icon`` field into something a UI can actually load.

    - "" -> None (caller falls back to a per-category default icon)
    - "https://.../icon.png" -> returned as-is; a store view fetches it
      directly the same way it would any other catalog artwork
    - bare "icon.png" -> resolved next to the manifest it came from (the
      local pack's own JSON file, so an author can ship "myplugin.json" +
      "myplugin_icon.png" side by side), falling back to
      ``LOCAL_PLUGINS_DIR``. Returns None if that file isn't actually there,
      so a missing icon degrades to the default rather than a broken image.
    """
    icon = (getattr(plugin, "icon", "") or "").strip()
    if not icon:
        return None
    if icon.startswith(("http://", "https://")):
        return icon
    base = Path(source).parent if source and os.path.isfile(source) else Path(LOCAL_PLUGINS_DIR)
    candidate = base / icon
    return str(candidate) if candidate.is_file() else None


# ---------------------------------------------------------------------------
# Fetch / discover
# ---------------------------------------------------------------------------

def fetch_manifest(url: str = DEFAULT_PLUGINS_URL) -> PluginManifest:
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise PluginError(f"Couldn't reach the plugin manifest: {e}") from e
    except json.JSONDecodeError as e:
        raise PluginError(f"Plugin manifest wasn't valid JSON: {e}") from e
    return PluginManifest.from_dict(data, source=url)


def load_manifest_file(path: str | Path) -> PluginManifest:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise PluginError(f"Couldn't read {path}: {e}") from e
    except json.JSONDecodeError as e:
        raise PluginError(f"{path} wasn't valid JSON: {e}") from e
    return PluginManifest.from_dict(data, source=str(path))


def remote_cache_path(directory: str = LOCAL_PLUGINS_DIR) -> Path:
    return Path(directory) / REMOTE_CACHE_FILENAME


def save_remote_cache(manifest: PluginManifest, directory: str = LOCAL_PLUGINS_DIR) -> Path:
    """Persist a remote manifest so the next launch can load it offline."""
    ensure_local_plugins_dir(directory)
    path = remote_cache_path(directory)
    payload = {
        "api_version": manifest.api_version,
        "updated_at": manifest.updated_at,
        "source": manifest.source,
        "cached_from": manifest.source,
        "plugins": [],
    }
    # Reconstruct JSON-serializable plugin dicts from dataclasses
    for p in manifest.plugins:
        entry = {
            "id": p.id,
            "category": p.category,
            "label": p.label,
            "author": p.author,
            "version": p.version,
            "description": p.description,
            "color": p.color,
            "subcategory": p.subcategory,
            "output_kind": p.output_kind,
            "tags": list(p.tags or []),
            "lua_expr": p.lua_expr,
            "lua_draw_body": p.lua_draw_body,
            "lua_helpers": p.lua_helpers,
            "simple_mode": bool(p.simple_mode),
            "homepage": p.homepage,
            "license": p.license,
            "icon": getattr(p, "icon", "") or "",
            "properties": [],
        }
        for prop in p.properties:
            entry["properties"].append({
                "key": prop.key,
                "label": prop.label,
                "kind": prop.kind,
                "default": prop.default,
                "minimum": prop.minimum,
                "maximum": prop.maximum,
                "step": prop.step,
                "choices": prop.choices,
                "choice_labels": prop.choice_labels,
                "bindable": prop.bindable,
                "accepts": prop.accepts,
                "help": prop.help,
                "group": prop.group,
            })
        payload["plugins"].append(entry)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path



INSTALLED_PACK_FILENAME = "installed-plugins.json"
UNINSTALLED_IDS_FILENAME = "uninstalled-ids.json"


def uninstalled_ids_path(directory: str = LOCAL_PLUGINS_DIR) -> Path:
    return Path(directory) / UNINSTALLED_IDS_FILENAME


def load_uninstalled_ids(directory: str = LOCAL_PLUGINS_DIR) -> set[str]:
    """Load the persisted uninstall blacklist into the process-wide set."""
    global _uninstalled_ids, _uninstalled_loaded
    path = uninstalled_ids_path(directory)
    ids: set[str] = set()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("ids") if isinstance(data, dict) else data
            if isinstance(raw, list):
                ids = {str(x) for x in raw if x}
        except (OSError, json.JSONDecodeError, TypeError):
            ids = set()
    _uninstalled_ids = ids
    _uninstalled_loaded = True
    return set(_uninstalled_ids)


def save_uninstalled_ids(directory: str = LOCAL_PLUGINS_DIR) -> Path:
    ensure_local_plugins_dir(directory)
    path = uninstalled_ids_path(directory)
    payload = {"ids": sorted(_uninstalled_ids)}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def mark_uninstalled(plugin_ids: Iterable[str], *, directory: str = LOCAL_PLUGINS_DIR) -> None:
    global _uninstalled_ids
    if not _uninstalled_loaded:
        load_uninstalled_ids(directory)
    _uninstalled_ids |= set(plugin_ids)
    save_uninstalled_ids(directory)


def clear_uninstalled(plugin_ids: Iterable[str], *, directory: str = LOCAL_PLUGINS_DIR) -> None:
    """Remove ids from the uninstall blacklist (explicit install)."""
    global _uninstalled_ids
    if not _uninstalled_loaded:
        load_uninstalled_ids(directory)
    _uninstalled_ids -= set(plugin_ids)
    save_uninstalled_ids(directory)


def is_uninstalled(plugin_id: str, *, directory: str = LOCAL_PLUGINS_DIR) -> bool:
    if not _uninstalled_loaded:
        load_uninstalled_ids(directory)
    return plugin_id in _uninstalled_ids


def _plugin_to_dict(p) -> dict:
    """Serialize a PluginNode (or pass through a dict) for the installed pack."""
    if isinstance(p, dict):
        return dict(p)
    entry = {
        "id": p.id,
        "category": p.category,
        "label": p.label,
        "author": p.author,
        "version": p.version,
        "description": p.description,
        "color": p.color,
        "subcategory": p.subcategory,
        "output_kind": p.output_kind,
        "tags": list(p.tags or []),
        "lua_expr": p.lua_expr,
        "lua_draw_body": p.lua_draw_body,
        "lua_helpers": p.lua_helpers,
        "simple_mode": bool(p.simple_mode),
        "homepage": getattr(p, "homepage", "") or "",
        "license": getattr(p, "license", "") or "",
        "icon": getattr(p, "icon", "") or "",
        "properties": [],
    }
    for prop in p.properties:
        entry["properties"].append({
            "key": prop.key,
            "label": prop.label,
            "kind": prop.kind,
            "default": prop.default,
            "minimum": prop.minimum,
            "maximum": prop.maximum,
            "step": prop.step,
            "choices": prop.choices,
            "choice_labels": prop.choice_labels,
            "bindable": prop.bindable,
            "accepts": prop.accepts,
            "help": prop.help,
            "group": prop.group,
        })
    return entry


def installed_pack_path(directory: str = LOCAL_PLUGINS_DIR) -> Path:
    return Path(directory) / INSTALLED_PACK_FILENAME


def persist_plugins(
    plugins: list,
    *,
    source: str = "plugins-dialog",
    directory: str = LOCAL_PLUGINS_DIR,
    filename: str = INSTALLED_PACK_FILENAME,
) -> Path:
    """Merge *plugins* into a local pack file so load_all() restores them
    on the next application start. Existing entries with the same id are
    replaced; other installed plugins are kept. Fetching a remote manifest
    never clears this file — only explicit uninstall does.
    """
    ensure_local_plugins_dir(directory)
    path = Path(directory) / filename
    existing: list = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            existing = list(data.get("plugins") or [])
        except (OSError, json.JSONDecodeError):
            existing = []

    by_id = {}
    for entry in existing:
        if isinstance(entry, dict) and entry.get("id"):
            by_id[entry["id"]] = entry

    for p in plugins:
        entry = _plugin_to_dict(p)
        by_id[entry["id"]] = entry

    payload = {
        "api_version": "1.1",
        "updated_at": "",
        "source": source,
        "plugins": list(by_id.values()),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def remove_from_installed(
    plugin_ids: Iterable[str],
    *,
    directory: str = LOCAL_PLUGINS_DIR,
    filename: str = INSTALLED_PACK_FILENAME,
) -> Path:
    """Remove the given plugin ids from the installed pack file.
    Other installed plugins are left untouched.
    """
    ensure_local_plugins_dir(directory)
    path = Path(directory) / filename
    existing: list = []
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            existing = list(data.get("plugins") or [])
        except (OSError, json.JSONDecodeError):
            existing = []

    remove = set(plugin_ids)
    remaining = [
        e for e in existing
        if isinstance(e, dict) and e.get("id") and e["id"] not in remove
    ]
    payload = {
        "api_version": "1.1",
        "updated_at": "",
        "source": "plugins-dialog",
        "plugins": remaining,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def iter_local_manifest_paths(
    directory: str = LOCAL_PLUGINS_DIR,
    *,
    skip_remote_cache: bool = False,
) -> list[Path]:
    root = Path(directory)
    if not root.is_dir():
        return []
    out = []
    skip_names = {UNINSTALLED_IDS_FILENAME}
    if skip_remote_cache:
        skip_names.add(REMOTE_CACHE_FILENAME)
    for p in sorted(root.glob("*.json")):
        if not p.is_file():
            continue
        if p.name in skip_names:
            continue
        out.append(p)
    return out


def ensure_local_plugins_dir(directory: str = LOCAL_PLUGINS_DIR) -> Path:
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    readme = path / "README.txt"
    if not readme.exists():
        readme.write_text(
            "Drop plugin manifest JSON files here (same shape as plugins.json).\n"
            "Each file is loaded on startup. Only add packs you trust, their Lua\n"
            "runs inside Conky with the same privileges as any theme script.\n",
            encoding="utf-8",
        )
    return path


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate(plugin: PluginNode) -> None:
    if not plugin.id:
        raise PluginError("plugin entry missing id")
    if not _ID_RE.match(plugin.id):
        raise PluginError(
            f"{plugin.id}: id must match logic.* or visual.* "
            f"(lowercase letters, digits, underscores; e.g. logic.clamp, visual.plugin.ring)"
        )
    if plugin.category not in ALLOWED_CATEGORIES:
        raise PluginError(
            f"{plugin.id}: category must be 'logic' or 'visual' (got {plugin.category!r}) — "
            f"source/canvas plugins aren't supported since they need real polling scripts "
            f"or fixed window semantics, not just a Lua expression."
        )
    if plugin.category == "logic":
        if not plugin.output_kind:
            raise PluginError(f"{plugin.id}: logic plugins need output_kind "
                              f"(percent/celsius/number/text/category/boolean)")
        if plugin.output_kind not in ALLOWED_OUTPUT_KINDS:
            raise PluginError(
                f"{plugin.id}: unknown output_kind {plugin.output_kind!r}; "
                f"expected one of {sorted(ALLOWED_OUTPUT_KINDS)}"
            )
        if not (plugin.lua_expr or "").strip():
            raise PluginError(f"{plugin.id}: logic plugins need lua_expr")
    if plugin.category == "visual" and not (plugin.lua_draw_body or "").strip():
        raise PluginError(f"{plugin.id}: visual plugins need lua_draw_body")

    keys = set()
    for p in plugin.properties:
        if not p.key or not re.match(r"^[a-z][a-z0-9_]*$", p.key):
            raise PluginError(f"{plugin.id}: bad property key {p.key!r}")
        if p.key in keys:
            raise PluginError(f"{plugin.id}: duplicate property key {p.key!r}")
        keys.add(p.key)
        if p.kind not in ALLOWED_KINDS:
            raise PluginError(
                f"{plugin.id}.{p.key}: unknown kind {p.kind!r}; "
                f"expected one of {sorted(ALLOWED_KINDS)}"
            )
        if p.kind == "enum" and not p.choices:
            raise PluginError(f"{plugin.id}.{p.key}: enum kind needs non-empty choices")

    # Warn-level: placeholders in templates that don't match any property
    template = (plugin.lua_expr or "") + "\n" + (plugin.lua_draw_body or "") + "\n" + (plugin.lua_helpers or "")
    for match in re.findall(r"\{([a-z][a-z0-9_]*)\}", template):
        if match not in keys and match not in ("cr",):  # cr is the cairo context, not a prop
            # Allow unknown placeholders only if they look accidental; still error —
            # authors almost always meant a property.
            raise PluginError(
                f"{plugin.id}: template references {{{match}}} but no property "
                f"with that key is declared"
            )

    # Allow re-install of a plugin we previously loaded and then uninstalled
    # (registry often has no unregister, so has() stays True). Block only when
    # the id belongs to a built-in / non-plugin registration.
    if (
        registry.has(plugin.id)
        and plugin.id not in _loaded
        and plugin.id not in _known_plugin_ids
    ):
        raise PluginError(
            f"{plugin.id}: a node type with this id is already registered "
            f"(built-in, or loaded from another plugin)"
        )


# ---------------------------------------------------------------------------
# Substitution + registration
# ---------------------------------------------------------------------------

def _property_spec(p: PluginProperty) -> registry.PropertySpec:
    return registry.PropertySpec(
        key=p.key, label=p.label, kind=p.kind, default=p.default,
        minimum=p.minimum, maximum=p.maximum, step=p.step,
        choices=p.choices, choice_labels=p.choice_labels,
        bindable=p.bindable,
        accepts=tuple(p.accepts) if p.accepts else None,
        help=p.help, group=p.group,
    )


def _substitute(template: str, plugin: PluginNode, node, ctx) -> str:
    """Replace every {property.key} with its resolved Lua expression via
    plain string replacement, NOT str.format()."""
    out = template
    for prop in plugin.properties:
        placeholder = "{" + prop.key + "}"
        if prop.kind == "color":
            hex_value = node.props.get(prop.key, prop.default)
            replacement = lua_rgb_literal(str(hex_value))
        else:
            replacement = str(ctx.resolve(node, prop.key))
        out = out.replace(placeholder, replacement)
    return out


def register_plugin(plugin: PluginNode, *, source: str = "") -> None:
    # Already registered this session (e.g. remote + cache, or double Fetch)
    if plugin.id in _loaded:
        return
    # Explicit install clears any prior uninstall so the plugin is allowed again.
    if is_uninstalled(plugin.id):
        clear_uninstalled([plugin.id])
    _validate(plugin)
    spec = registry.NodeSpec(
        type=plugin.id,
        category=plugin.category,
        label=plugin.label,
        description=(
            plugin.description
            + (f" (plugin by {plugin.author})" if plugin.author else " (plugin)")
        ),
        color=plugin.color,
        output_kind=plugin.output_kind,
        properties=[_property_spec(p) for p in plugin.properties],
        simple_mode=bool(plugin.simple_mode),
        subcategory=plugin.subcategory or "Plugins",
    )
    # Re-install: drop any prior registration so registry.register does not
    # raise Duplicate (plugins previously loaded in this process).
    try:
        if hasattr(registry, "unregister") and registry.has(plugin.id):
            registry.unregister(plugin.id)
        if hasattr(registry, "register"):
            # Prefer replace= when available (newer registry API).
            try:
                registry.register(spec, replace=True)
            except TypeError:
                registry.register(spec)
    except Exception as e:
        raise PluginError(f"{plugin.id}: could not register node type: {e}") from e

    try:
        if plugin.category == "logic":
            def _gen(node, ctx, _plugin=plugin):
                return _substitute(_plugin.lua_expr, _plugin, node, ctx)
            lua_gen.logic_generator(plugin.id)(_gen)
        else:
            def _gen(node, ctx, _plugin=plugin):
                fn_name = f"draw_node_{lua_gen.lua_safe_id(node.id)}"
                helpers = ""
                if _plugin.lua_helpers and _plugin.id not in _helpers_emitted:
                    # Helpers are pure template text (may still contain {props}
                    # for the *first* node that needs them — rare; usually constants).
                    helpers = _substitute(_plugin.lua_helpers, _plugin, node, ctx).rstrip() + "\n\n"
                    _helpers_emitted.add(_plugin.id)
                body = _substitute(_plugin.lua_draw_body, _plugin, node, ctx)
                return f"{helpers}local function {fn_name}(cr, W, H)\n{body}\nend"
            lua_gen.visual_generator(plugin.id)(_gen)
    except Exception as e:
        raise PluginError(f"{plugin.id}: could not register lua generator: {e}") from e

    _loaded[plugin.id] = {"plugin": plugin, "source": source}
    _known_plugin_ids.add(plugin.id)


# ---------------------------------------------------------------------------
# Bulk load
# ---------------------------------------------------------------------------

def load_manifest(
    manifest: PluginManifest,
    *,
    persist_if_remote: bool = True,
    local_dir: str = LOCAL_PLUGINS_DIR,
) -> tuple[list[str], list[str]]:
    """Register every plugin in *manifest*.

    If the manifest came from a URL (source starts with http) and
    *persist_if_remote* is true, the full manifest is written to
    ``<local_dir>/remote-cache.json`` so the next application start can
    load the same plugins without another Fetch click.
    """
    loaded, errors = [], []
    for plugin in manifest.plugins:
        if is_uninstalled(plugin.id):
            continue
        try:
            register_plugin(plugin, source=manifest.source)
            loaded.append(plugin.id)
        except PluginError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"{plugin.id}: {e}")

    if (
        persist_if_remote
        and loaded
        and isinstance(manifest.source, str)
        and manifest.source.startswith(("http://", "https://"))
    ):
        try:
            save_remote_cache(manifest, local_dir)
        except OSError as e:
            errors.append(f"Could not cache remote plugins: {e}")

    return loaded, errors


def fetch_and_load(
    url: str = DEFAULT_PLUGINS_URL,
    *,
    local_dir: str = LOCAL_PLUGINS_DIR,
) -> tuple[list[str], list[str]]:
    """Fetch button path: download, register, and persist to remote-cache.json."""
    manifest = fetch_manifest(url)
    return load_manifest(manifest, persist_if_remote=True, local_dir=local_dir)


def load_all(
    url: str = DEFAULT_PLUGINS_URL,
    *,
    local_dir: str = LOCAL_PLUGINS_DIR,
    include_remote: bool = False,
    include_local: bool = True,
) -> tuple[list[str], list[str]]:
    """Load plugins the user has installed (local packs), optionally remote too.

    Default is *include_remote=False*: only ``installed-plugins.json`` and any
    other user-dropped local manifests are registered. The remote catalogue is
    for Tools → Plugins → Fetch / Install — not auto-installed on every launch.
    ``remote-cache.json`` is never auto-registered (it is an offline catalogue
    only). Ids listed in ``uninstalled-ids.json`` are always skipped.

    Returns (loaded_ids, errors). One bad entry does not block the rest.
    """
    ensure_local_plugins_dir(local_dir)
    load_uninstalled_ids(local_dir)
    loaded: list[str] = []
    errors: list[str] = []

    if include_remote and url:
        try:
            manifest = fetch_manifest(url)
            ids, errs = load_manifest(manifest)
            loaded.extend(ids)
            errors.extend(errs)
            try:
                save_remote_cache(manifest, local_dir)
            except OSError as e:
                errors.append(f"Could not cache remote plugins: {e}")
        except PluginError as e:
            errors.append(str(e))

    if include_local:
        # Always skip remote-cache: that file is a catalogue, not an install list.
        for path in iter_local_manifest_paths(local_dir, skip_remote_cache=True):
            try:
                manifest = load_manifest_file(path)
                ids, errs = load_manifest(manifest)
                loaded.extend(ids)
                errors.extend(errs)
            except PluginError as e:
                errors.append(str(e))

    return loaded, errors


def loaded_plugin_ids() -> set:
    return set(_loaded.keys())


def plugin_meta_for(type_id: str) -> dict | None:
    """Metadata for a loaded plugin node type, or None if not a loaded plugin."""
    meta = _loaded.get(type_id)
    if not meta:
        return None
    p: PluginNode = meta["plugin"]
    return {
        "id": p.id,
        "label": p.label,
        "author": p.author,
        "version": p.version,
        "category": p.category,
        "source": meta.get("source", ""),
        "homepage": getattr(p, "homepage", "") or "",
        "tags": list(p.tags),
        "description": p.description,
        "icon": resolve_icon(p, source=meta.get("source", "")),
    }


def loaded_plugins() -> list[dict]:
    """For a Plugins settings UI: [{id, label, author, version, source, category}, …].

    Returned alphabetically by label (then id) so UI lists stay sorted.
    """
    out = []
    for pid, meta in _loaded.items():
        try:
            p = meta.get("plugin") if isinstance(meta, dict) else None
            if p is None:
                continue
            out.append({
                "id": getattr(p, "id", pid),
                "label": getattr(p, "label", pid),
                "author": getattr(p, "author", "") or "",
                "version": getattr(p, "version", "") or "",
                "category": getattr(p, "category", "") or "",
                "source": meta.get("source", "") if isinstance(meta, dict) else "",
                "homepage": getattr(p, "homepage", "") or "",
                "tags": list(getattr(p, "tags", None) or []),
                "description": getattr(p, "description", "") or "",
                "icon": resolve_icon(p, source=meta.get("source", "") if isinstance(meta, dict) else ""),
            })
        except Exception:
            continue
    out.sort(key=lambda m: ((m.get("label") or m.get("id") or "").lower(),
                            (m.get("id") or "").lower()))
    return out


def _strip_ids_from_manifest_file(path: Path, plugin_ids: set[str]) -> None:
    """If *path* is a manifest JSON, drop any plugins whose id is in *plugin_ids*."""
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    plugins = data.get("plugins")
    if not isinstance(plugins, list):
        return
    filtered = [
        e for e in plugins
        if not (isinstance(e, dict) and e.get("id") in plugin_ids)
    ]
    if len(filtered) == len(plugins):
        return
    data["plugins"] = filtered
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def uninstall_plugin(
    plugin_id: str,
    *,
    directory: str = LOCAL_PLUGINS_DIR,
) -> None:
    """Remove a plugin from the current session and from local packs.

    - Drops it from ``_loaded`` so it is no longer treated as a plugin.
    - Removes it from ``installed-plugins.json`` and from ``remote-cache.json``
      (and any other local manifest that lists it) so Fetch / restart will
      not bring it back until the user installs it again.
    - Best-effort unregister from the node registry and lua generators when
      those APIs exist.

    Raises PluginError if *plugin_id* is not currently loaded as a plugin.
    """
    if plugin_id not in _loaded:
        raise PluginError(f"{plugin_id} is not a loaded plugin")

    del _loaded[plugin_id]
    _helpers_emitted.discard(plugin_id)
    # Keep id in _known_plugin_ids so a later Install can re-register.

    try:
        if hasattr(registry, "unregister"):
            registry.unregister(plugin_id)
    except Exception:
        pass
    for attr in ("unregister_logic", "unregister_visual", "unregister"):
        fn = getattr(lua_gen, attr, None)
        if callable(fn):
            try:
                fn(plugin_id)
            except Exception:
                pass

    try:
        remove_from_installed([plugin_id], directory=directory)
    except OSError as e:
        raise PluginError(f"Could not update installed plugins file: {e}") from e

    try:
        mark_uninstalled([plugin_id], directory=directory)
    except OSError as e:
        raise PluginError(f"Could not update uninstalled-ids file: {e}") from e

    ids = {plugin_id}
    root = Path(directory)
    if root.is_dir():
        for path in root.glob("*.json"):
            if path.name in (INSTALLED_PACK_FILENAME, UNINSTALLED_IDS_FILENAME):
                continue
            _strip_ids_from_manifest_file(path, ids)


def uninstall_plugins(
    plugin_ids: Iterable[str],
    *,
    directory: str = LOCAL_PLUGINS_DIR,
) -> tuple[list[str], list[str]]:
    """Uninstall several plugins. Returns (removed_ids, errors)."""
    removed: list[str] = []
    errors: list[str] = []
    for pid in plugin_ids:
        try:
            uninstall_plugin(pid, directory=directory)
            removed.append(pid)
        except PluginError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"{pid}: {e}")
    return removed, errors


def try_install_from_sources(
    type_ids: list[str],
    sources: list[str],
) -> tuple[list[str], list[str]]:
    """Attempt to load *type_ids* by fetching unique manifest *sources*.

    Returns (matched_ids_now_available, errors). URL sources are fetched;
    local paths are read as files. Default remote + local packs are also
    tried if anything is still missing. Existing defaults are unchanged.
    """
    errors: list[str] = []
    wanted = set(type_ids)
    seen_sources: set[str] = set()

    for src in sources:
        src = (src or "").strip()
        if not src or src in seen_sources:
            continue
        seen_sources.add(src)
        try:
            if src.startswith(("http://", "https://")):
                manifest = fetch_manifest(src)
            elif os.path.isfile(src):
                manifest = load_manifest_file(src)
            else:
                errors.append(f"Unknown plugin source (not a URL or file): {src}")
                continue
            _ids, errs = load_manifest(manifest, persist_if_remote=True)
            errors.extend(errs)
        except PluginError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"{src}: {e}")

    still = wanted - loaded_plugin_ids()
    still = {t for t in still if not registry.has(t)}
    if still:
        try:
            _ids, errs = load_all()
            errors.extend(errs)
        except Exception as e:
            errors.append(str(e))

    matched = [t for t in type_ids if t in loaded_plugin_ids() or registry.has(t)]
    return matched, errors


def validate_only(manifest: PluginManifest) -> list[str]:
    """Dry-run validation without registering (useful for CI / authoring)."""
    errors = []
    seen = set()
    for plugin in manifest.plugins:
        try:
            if plugin.id in seen:
                raise PluginError(f"{plugin.id}: duplicate id in the same manifest")
            seen.add(plugin.id)
            # Temporarily ignore registry.has for dry-run of new packs
            _validate_dry(plugin)
        except PluginError as e:
            errors.append(str(e))
    return errors


def _validate_dry(plugin: PluginNode) -> None:
    """Like _validate but skips the 'already registered' check."""
    if not plugin.id:
        raise PluginError("plugin entry missing id")
    if not _ID_RE.match(plugin.id):
        raise PluginError(
            f"{plugin.id}: id must match logic.* or visual.* "
            f"(e.g. logic.clamp, visual.plugin.ring)"
        )
    if plugin.category not in ALLOWED_CATEGORIES:
        raise PluginError(f"{plugin.id}: category must be 'logic' or 'visual'")
    if plugin.category == "logic":
        if not plugin.output_kind or plugin.output_kind not in ALLOWED_OUTPUT_KINDS:
            raise PluginError(f"{plugin.id}: invalid or missing output_kind")
        if not (plugin.lua_expr or "").strip():
            raise PluginError(f"{plugin.id}: logic plugins need lua_expr")
    if plugin.category == "visual" and not (plugin.lua_draw_body or "").strip():
        raise PluginError(f"{plugin.id}: visual plugins need lua_draw_body")
    icon = (getattr(plugin, "icon", "") or "").strip()
    if icon:
        if icon.startswith(("http://", "https://")):
            if not _ICON_URL_RE.match(icon):
                raise PluginError(f"{plugin.id}: icon URL must be http(s) and end in .png")
        elif "/" in icon or "\\" in icon:
            raise PluginError(f"{plugin.id}: icon must be a bare filename, not a path ({icon!r})")
        elif not _ICON_FILENAME_RE.match(icon):
            raise PluginError(f"{plugin.id}: icon filename must be a plain .png name ({icon!r})")
    keys = set()
    for p in plugin.properties:
        if not p.key or not re.match(r"^[a-z][a-z0-9_]*$", p.key):
            raise PluginError(f"{plugin.id}: bad property key {p.key!r}")
        if p.key in keys:
            raise PluginError(f"{plugin.id}: duplicate property key {p.key!r}")
        keys.add(p.key)
        if p.kind not in ALLOWED_KINDS:
            raise PluginError(f"{plugin.id}.{p.key}: unknown kind {p.kind!r}")
        if p.kind == "enum" and not p.choices:
            raise PluginError(f"{plugin.id}.{p.key}: enum needs choices")
    template = (plugin.lua_expr or "") + "\n" + (plugin.lua_draw_body or "") + "\n" + (plugin.lua_helpers or "")
    for match in re.findall(r"\{([a-z][a-z0-9_]*)\}", template):
        if match not in keys:
            raise PluginError(f"{plugin.id}: template references {{{match}}} but no such property")
