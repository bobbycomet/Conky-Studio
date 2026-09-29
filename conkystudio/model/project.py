"""
Project data model for Conky Studio.

A Project is the JSON-serializable "source of truth" for one HUD/theme
design edited on the Studio canvas. It intentionally knows nothing about
Qt or Cairo -- the UI (conkystudio.ui.studio) renders it, and the Builder
(conkystudio.codegen.builder) compiles it into a standalone conky.conf +
render.lua + scripts/ bundle that runs with zero runtime dependency on
Conky Studio itself. That separation is what makes projects re-editable:
opening a .cstudio package (or legacy .json / Hud.json) later reconstructs
the exact node graph, instead of having to reverse-engineer hand-written Lua.

Portable projects use the .cstudio zip format:
  project.json + manifest.json + assets/{images,fonts,scripts}/
All external media/fonts/scripts the user added are copied into the package
and referenced by package-relative paths. Legacy bare .json files still open;
the next Save always writes a .cstudio package.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 1
# Projects that persist an explicit windows[] list use schema_version >= 2.
# Loading always migrates older files (canvas-only) into a single window.
SCHEMA_VERSION_WITH_WINDOWS = 2
# Packages that ship assets/ + relative paths use schema_version >= 3.
SCHEMA_VERSION_PACKAGE = 3
CANVAS_NODE_ID = "canvas"

PACKAGE_EXTENSION = ".cstudio"
PROJECT_JSON_NAME = "project.json"
MANIFEST_NAME = "manifest.json"

# Node prop keys that point at files we should bundle (not system paths like
# mount_path="/" or device="/dev/sda").
_IMAGE_PATH_KEYS = ("path", "swap_above_path", "swap_below_path", "fallback_path")
_SCRIPT_PATH_KEYS = ("script_path",)
_ASSET_LIST_KEYS = ("asset_paths",)

# Font families that are assumed present on most desktops — not prompted for
# when packaging.
_COMMON_FONT_FAMILIES = {
    "sans", "sans-serif", "serif", "monospace", "mono",
    "dejavu sans", "dejavu sans mono", "dejavu serif",
    "liberation sans", "liberation mono", "liberation serif",
    "noto sans", "noto serif", "noto sans mono",
    "free sans", "free serif", "free mono",
    "ubuntu", "ubuntu mono", "cantarell", "roboto",
}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def is_package_path(path: str) -> bool:
    return bool(path) and path.lower().endswith(PACKAGE_EXTENSION)


def is_legacy_json_path(path: str) -> bool:
    if not path:
        return False
    lower = path.lower()
    return lower.endswith(".json") and not lower.endswith(PACKAGE_EXTENSION)


def _package_cache_root() -> str:
    return os.path.join(os.path.expanduser("~/.cache/conky-studio/packages"))


def _work_dir_for_package(package_path: str) -> str:
    abspath = os.path.abspath(package_path)
    digest = hashlib.sha1(abspath.encode("utf-8")).hexdigest()[:16]
    return os.path.join(_package_cache_root(), digest)


def _unique_dest_name(dest_dir: str, basename: str) -> str:
    """Avoid collisions when two different source files share a basename."""
    name = basename or "asset"
    stem, ext = os.path.splitext(name)
    candidate = name
    n = 1
    while os.path.exists(os.path.join(dest_dir, candidate)):
        candidate = f"{stem}_{n}{ext}"
        n += 1
    return candidate


def _classify_asset(path: str, prop_key: str) -> str:
    """Return assets/ subfolder name for a file being packaged."""
    if prop_key in _SCRIPT_PATH_KEYS:
        return "scripts"
    lower = path.lower()
    if lower.endswith((".ttf", ".otf", ".ttc", ".woff", ".woff2")):
        return "fonts"
    if prop_key in _ASSET_LIST_KEYS:
        return "scripts" if lower.endswith((".sh", ".bash", ".py", ".lua")) else "images"
    return "images"


# ---------------------------------------------------------------------------
# Multi-window / multi-monitor
# ---------------------------------------------------------------------------

@dataclass
class WindowSettings:
    """One Conky own_window, optionally pinned to a monitor output.

    Legacy single-canvas projects become windows=[WindowSettings(...from canvas)].
    theme.json resolution continues to summarise the primary window so older
    Manager tooling and single-monitor paths stay valid.
    """
    id: str = "window_0"
    name: str = "Main"
    # "auto" | "primary" | concrete output name from xrandr / compositor
    # e.g. "DP-1", "HDMI-A-1", "eDP-1"
    monitor: str = "auto"
    width: int = 460
    height: int = 640
    alignment: str = "top_left"
    gap_x: int = 24
    gap_y: int = 24
    fps: int = 30
    stats_hz: float = 2.0
    window_type: str = "auto"  # auto | normal | desktop | dock
    window_class: str = "conky-studio"
    transparent: bool = True
    # Empty = draw full shared graph. Non-empty = only these visual node ids
    # (optional per-window scene override; default preserves single-HUD path).
    visible_node_ids: list[str] = field(default_factory=list)
    z: int = 0
    enabled: bool = True

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "WindowSettings":
        w = WindowSettings()
        for k, v in (d or {}).items():
            if not hasattr(w, k):
                continue
            if k == "visible_node_ids":
                setattr(w, k, list(v or []))
            else:
                setattr(w, k, v)
        if not w.id:
            w.id = new_id("window")
        return w

    def to_canvas_dict(self) -> dict:
        """Legacy CanvasSettings field subset (for canvas.root / theme.json)."""
        return {
            "width": self.width,
            "height": self.height,
            "alignment": self.alignment,
            "gap_x": self.gap_x,
            "gap_y": self.gap_y,
            "fps": self.fps,
            "stats_hz": self.stats_hz,
            "window_type": self.window_type,
            "window_class": self.window_class,
            "transparent": self.transparent,
        }


def window_from_canvas(canvas: "CanvasSettings") -> WindowSettings:
    return WindowSettings(
        id="window_0",
        name="Main",
        monitor="auto",
        width=int(canvas.width),
        height=int(canvas.height),
        alignment=str(canvas.alignment),
        gap_x=int(canvas.gap_x),
        gap_y=int(canvas.gap_y),
        fps=int(canvas.fps),
        stats_hz=float(canvas.stats_hz),
        window_type=str(canvas.window_type),
        window_class=str(canvas.window_class),
        transparent=bool(canvas.transparent),
    )


@dataclass
class NodeInstance:
    id: str
    type: str  # dotted registry key, e.g. "visual.arc_gauge" or "source.cpu_temp"
    x: float = 0.0
    y: float = 0.0
    label: str = ""  # optional user-given display name shown on the node header
    props: dict[str, Any] = field(default_factory=dict)  # constant property values
    z: int = 0  # draw order for visual nodes; higher draws on top
    visible: bool = True   # Layers dock eye toggle -- hidden nodes are skipped by codegen entirely
    locked: bool = False    # Layers dock lock toggle -- blocks canvas selection/move, not codegen
    # Optional clickable region (validated by real usage: music-controls.lua's
    # play/pause/prev/next/app-launcher hotspots are exactly explicit x/y/w/h
    # boxes mapped to a shell command). Kept as an explicit region rather than
    # auto-derived from each node type's drawing geometry -- simpler, and
    # matches how the real theme this pattern came from actually authors them.
    on_click_command: str = ""
    click_x: float = 0.0
    click_y: float = 0.0
    click_w: float = 0.0
    click_h: float = 0.0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "NodeInstance":
        return NodeInstance(
            id=d["id"],
            type=d["type"],
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
            label=d.get("label", ""),
            props=dict(d.get("props", {}) or {}),
            z=int(d.get("z", 0)),
            visible=bool(d.get("visible", True)),
            locked=bool(d.get("locked", False)),
            on_click_command=d.get("on_click_command", ""),
            click_x=float(d.get("click_x", 0.0)),
            click_y=float(d.get("click_y", 0.0)),
            click_w=float(d.get("click_w", 0.0)),
            click_h=float(d.get("click_h", 0.0)),
        )


@dataclass
class Edge:
    id: str
    src_node: str  # id of the data-source node providing the value
    dst_node: str  # id of the node consuming it
    dst_prop: str  # which bindable property on dst_node this feeds

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Edge":
        return Edge(id=d["id"], src_node=d["src_node"], dst_node=d["dst_node"], dst_prop=d["dst_prop"])


@dataclass
class NodeGroup:
    """Editor-only grouping for graph readability. Does not affect codegen.

    Members keep their own positions; the group is a frame around them.
    When collapsed, the UI hides member nodes and shows a compact chip.
    """
    id: str
    title: str = "Group"
    node_ids: list[str] = field(default_factory=list)
    collapsed: bool = False
    color: str = "#3a4048"  # frame / header tint
    # Anchor used when collapsed (centre of the compact chip). When expanded,
    # the frame is derived from member bounding boxes instead.
    x: float = 0.0
    y: float = 0.0

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "NodeGroup":
        return NodeGroup(
            id=d["id"],
            title=d.get("title", "Group"),
            node_ids=list(d.get("node_ids") or []),
            collapsed=bool(d.get("collapsed", False)),
            color=d.get("color", "#3a4048"),
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
        )


@dataclass
class GraphLabel:
    """Free-form text annotation on the node canvas (not drawn by Conky)."""
    id: str
    text: str = "Label"
    x: float = 0.0
    y: float = 0.0
    color: str = "#9aa2ad"
    font_size: int = 12

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "GraphLabel":
        return GraphLabel(
            id=d["id"],
            text=d.get("text", "Label"),
            x=float(d.get("x", 0.0)),
            y=float(d.get("y", 0.0)),
            color=d.get("color", "#9aa2ad"),
            font_size=int(d.get("font_size", 12)),
        )


@dataclass
class CanvasSettings:
    width: int = 460
    height: int = 640
    alignment: str = "top_left"  # conky "alignment" values, e.g. top_right, bottom_left, ...
    gap_x: int = 24
    gap_y: int = 24
    fps: int = 30  # draw hook rate; independent of how often data sources are polled
    stats_hz: float = 2.0  # how many times/sec native + cached sources are re-read
    window_type: str = "auto"  # auto | normal | desktop | dock  (see hardware/discovery.py)
    window_class: str = "conky-studio"
    transparent: bool = True

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "CanvasSettings":
        c = CanvasSettings()
        for k, v in (d or {}).items():
            if hasattr(c, k):
                setattr(c, k, v)
        return c


@dataclass
class Project:
    schema_version: int = SCHEMA_VERSION
    name: str = "Untitled HUD"
    author: str = ""
    description: str = ""
    canvas: CanvasSettings = field(default_factory=CanvasSettings)
    # Multi-monitor: one entry per Conky process. Empty on disk for legacy
    # projects — ensure_windows() synthesises windows[0] from canvas.
    windows: list[WindowSettings] = field(default_factory=list)
    nodes: list[NodeInstance] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    groups: list[NodeGroup] = field(default_factory=list)
    labels: list[GraphLabel] = field(default_factory=list)
    # Runtime-only (not serialized). Set when this project was opened from a
    # .cstudio package: extracted working tree root used to resolve relative
    # asset paths and to re-pack on Save.
    package_root: Optional[str] = field(default=None, repr=False, compare=False)
    # Runtime-only path of the file the user last opened/saved
    # (.cstudio or legacy .json).
    source_path: Optional[str] = field(default=None, repr=False, compare=False)

    # ---- graph helpers ---------------------------------------------------
    def node(self, node_id: str) -> Optional[NodeInstance]:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def group(self, group_id: str) -> Optional[NodeGroup]:
        for g in self.groups:
            if g.id == group_id:
                return g
        return None

    def group_for_node(self, node_id: str) -> Optional[NodeGroup]:
        for g in self.groups:
            if node_id in g.node_ids:
                return g
        return None

    def label(self, label_id: str) -> Optional[GraphLabel]:
        for lb in self.labels:
            if lb.id == label_id:
                return lb
        return None

    def add_group(self, title: str, node_ids: list[str], color: str = "#3a4048") -> NodeGroup:
        # A node may only belong to one group — pull it out of any previous group first.
        for nid in node_ids:
            self.remove_node_from_groups(nid)
        xs = [n.x for n in self.nodes if n.id in node_ids]
        ys = [n.y for n in self.nodes if n.id in node_ids]
        cx = sum(xs) / len(xs) if xs else 0.0
        cy = sum(ys) / len(ys) if ys else 0.0
        g = NodeGroup(
            id=new_id("grp"), title=title or "Group",
            node_ids=list(node_ids), color=color, x=cx, y=cy,
        )
        self.groups.append(g)
        return g

    def remove_group(self, group_id: str, *, dissolve: bool = True) -> None:
        """Remove the group frame. Members stay on the canvas either way."""
        self.groups = [g for g in self.groups if g.id != group_id]

    def remove_node_from_groups(self, node_id: str) -> None:
        for g in self.groups:
            if node_id in g.node_ids:
                g.node_ids = [i for i in g.node_ids if i != node_id]
        self.groups = [g for g in self.groups if g.node_ids]

    def set_group_collapsed(self, group_id: str, collapsed: bool) -> None:
        g = self.group(group_id)
        if g is not None:
            g.collapsed = collapsed

    def add_label(self, text: str, x: float, y: float) -> GraphLabel:
        lb = GraphLabel(id=new_id("lbl"), text=text or "Label", x=x, y=y)
        self.labels.append(lb)
        return lb

    def remove_label(self, label_id: str) -> None:
        self.labels = [lb for lb in self.labels if lb.id != label_id]


    def nodes_of_category(self, registry_lookup) -> list[NodeInstance]:
        """registry_lookup: callable(type_str) -> NodeSpec. Kept as an injected
        callable rather than importing nodes.registry directly, so this module
        stays free of any import-order coupling to the node library."""
        return list(self.nodes)

    def edges_into(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.dst_node == node_id]

    def edge_for_prop(self, node_id: str, prop: str) -> Optional[Edge]:
        for e in self.edges:
            if e.dst_node == node_id and e.dst_prop == prop:
                return e
        return None

    def add_node(self, node: NodeInstance) -> NodeInstance:
        self.nodes.append(node)
        return node

    def remove_node(self, node_id: str) -> None:
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.edges = [e for e in self.edges if e.src_node != node_id and e.dst_node != node_id]
        self.remove_node_from_groups(node_id)

    def add_edge(self, src_node: str, dst_node: str, dst_prop: str) -> Edge:
        # A bindable property can only have one incoming wire -- adding a new
        # one silently replaces any existing binding for that slot, mirroring
        # how a plug can only go into one socket at a time.
        self.edges = [e for e in self.edges if not (e.dst_node == dst_node and e.dst_prop == dst_prop)]
        e = Edge(id=new_id("edge"), src_node=src_node, dst_node=dst_node, dst_prop=dst_prop)
        self.edges.append(e)
        return e

    def remove_edge(self, edge_id: str) -> None:
        self.edges = [e for e in self.edges if e.id != edge_id]

    def next_z(self) -> int:
        return (max((n.z for n in self.nodes), default=-1)) + 1

    def reorder_nodes(self, ordered_ids: list[str]) -> None:
        """Layers dock drag-reorder: ordered_ids is top-to-bottom as shown in
        the dock (top = drawn last = on top of the stack), so it's reversed
        here since codegen draws in ASCENDING z -- the bottom of the visual
        stack needs the lowest z value."""
        for new_z, node_id in enumerate(reversed(ordered_ids)):
            n = self.node(node_id)
            if n is not None:
                n.z = new_z

    def set_visible(self, node_id: str, visible: bool) -> None:
        n = self.node(node_id)
        if n is not None:
            n.visible = visible

    def set_locked(self, node_id: str, locked: bool) -> None:
        n = self.node(node_id)
        if n is not None:
            n.locked = locked

    def ensure_canvas_node(self) -> NodeInstance:
        """The Canvas settings pseudo-node is edited through the same
        property-panel mechanism as everything else, so it needs to exist
        as a real NodeInstance -- this creates it (from the current
        CanvasSettings) if a loaded/older project doesn't have one yet.
        Idempotent: safe to call on every project load."""
        existing = self.node(CANVAS_NODE_ID)
        if existing is not None:
            return existing
        n = NodeInstance(id=CANVAS_NODE_ID, type="canvas.root", x=-260, y=0, props=dict(self.canvas.to_dict()))
        self.nodes.insert(0, n)
        return n

    def sync_canvas_from_node(self) -> None:
        """Call after the Canvas node's props are edited in the property
        panel -- copies them into the authoritative CanvasSettings that
        codegen actually reads (see codegen/conky_conf_gen.py), and mirrors
        them onto the primary window so multi-window builds stay in sync."""
        n = self.node(CANVAS_NODE_ID)
        if n is None:
            return
        for k, v in n.props.items():
            if hasattr(self.canvas, k):
                setattr(self.canvas, k, v)
        self.sync_primary_from_canvas()


    # ---- multi-window helpers ---------------------------------------------
    def ensure_windows(self) -> list[WindowSettings]:
        """Guarantee a non-empty windows list (migrate canvas → window_0)."""
        if self.windows:
            cleaned = [w for w in self.windows if isinstance(w, WindowSettings)]
            if cleaned:
                self.windows = cleaned
                return cleaned
        primary = window_from_canvas(self.canvas)
        self.windows = [primary]
        return self.windows

    def primary_window(self) -> WindowSettings:
        wins = self.ensure_windows()
        enabled = [w for w in wins if w.enabled]
        pool = enabled or wins
        return min(pool, key=lambda w: (w.z, w.id))

    def enabled_windows(self) -> list[WindowSettings]:
        wins = self.ensure_windows()
        out = [w for w in wins if w.enabled]
        return out or [wins[0]]

    def add_window(self, *, name: str = "", monitor: str = "auto",
                   copy_from_primary: bool = True) -> WindowSettings:
        primary = self.primary_window()
        if copy_from_primary:
            w = WindowSettings.from_dict(primary.to_dict())
            w.id = new_id("window")
            w.name = name or f"Window {len(self.windows) + 1}"
            w.monitor = monitor
            w.z = (max((x.z for x in self.windows), default=-1) + 1)
            w.visible_node_ids = list(primary.visible_node_ids)
        else:
            w = WindowSettings(
                id=new_id("window"),
                name=name or f"Window {len(self.windows) + 1}",
                monitor=monitor,
                z=(max((x.z for x in self.windows), default=-1) + 1),
            )
        self.windows.append(w)
        self.schema_version = max(self.schema_version, SCHEMA_VERSION_WITH_WINDOWS)
        return w

    def remove_window(self, window_id: str) -> bool:
        if len(self.ensure_windows()) <= 1:
            return False  # always keep at least one window
        before = len(self.windows)
        self.windows = [w for w in self.windows if w.id != window_id]
        if len(self.windows) == before:
            return False
        self.sync_canvas_from_primary()
        return True

    def window(self, window_id: str) -> Optional[WindowSettings]:
        for w in self.windows:
            if w.id == window_id:
                return w
        return None

    def sync_canvas_from_primary(self) -> None:
        """Mirror primary window → canvas (theme.json / canvas.root readers)."""
        w = self.primary_window()
        c = self.canvas
        c.width = w.width
        c.height = w.height
        c.alignment = w.alignment
        c.gap_x = w.gap_x
        c.gap_y = w.gap_y
        c.fps = w.fps
        c.stats_hz = w.stats_hz
        c.window_type = w.window_type
        c.window_class = w.window_class
        c.transparent = w.transparent

    def sync_primary_from_canvas(self) -> None:
        """After canvas.root property edits, push values into the primary window."""
        w = self.primary_window()
        c = self.canvas
        w.width = c.width
        w.height = c.height
        w.alignment = c.alignment
        w.gap_x = c.gap_x
        w.gap_y = c.gap_y
        w.fps = c.fps
        w.stats_hz = c.stats_hz
        w.window_type = c.window_type
        w.window_class = c.window_class
        w.transparent = c.transparent


    # ---- (de)serialization -------------------------------------------------
    def to_dict(self) -> dict:
        # Always persist windows (at least the migrated primary) so re-open
        # is lossless and multi-monitor layouts survive round-trips.
        self.ensure_windows()
        self.sync_canvas_from_primary()
        if len(self.windows) > 1:
            self.schema_version = max(self.schema_version, SCHEMA_VERSION_WITH_WINDOWS)
        d = {
            "schema_version": self.schema_version,
            "name": self.name,
            "author": self.author,
            "description": self.description,
            "canvas": self.canvas.to_dict(),
            "windows": [w.to_dict() for w in self.windows],
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }
        if self.groups:
            d["groups"] = [g.to_dict() for g in self.groups]
        if self.labels:
            d["labels"] = [lb.to_dict() for lb in self.labels]
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @staticmethod
    def from_dict(d: dict) -> "Project":
        p = Project(
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            name=d.get("name", "Untitled HUD"),
            author=d.get("author", ""),
            description=d.get("description", ""),
            canvas=CanvasSettings.from_dict(d.get("canvas", {})),
        )
        raw_windows = d.get("windows") or []
        p.windows = [
            WindowSettings.from_dict(w)
            for w in raw_windows
            if isinstance(w, dict)
        ]
        # Legacy / single-monitor: no windows key → synthesise from canvas.
        # theme.json + old .json projects open unchanged.
        p.ensure_windows()
        p.sync_canvas_from_primary()
        p.nodes = [NodeInstance.from_dict(n) for n in d.get("nodes", [])]
        p.edges = [Edge.from_dict(e) for e in d.get("edges", [])]
        p.groups = [NodeGroup.from_dict(g) for g in (d.get("groups") or []) if isinstance(g, dict) and g.get("id")]
        p.labels = [GraphLabel.from_dict(lb) for lb in (d.get("labels") or []) if isinstance(lb, dict) and lb.get("id")]
        # Drop stale member ids that no longer exist
        known = {n.id for n in p.nodes}
        for g in p.groups:
            g.node_ids = [i for i in g.node_ids if i in known]
        p.groups = [g for g in p.groups if g.node_ids]
        # Drop visible_node_ids that no longer exist
        for w in p.windows:
            w.visible_node_ids = [i for i in w.visible_node_ids if i in known]
        p.ensure_canvas_node()
        return p

    @staticmethod
    def from_json(text: str) -> "Project":
        return Project.from_dict(json.loads(text))

    # ---- asset / package helpers ------------------------------------------
    def search_dirs(self) -> list[str]:
        """Directories the Builder / UI should search for relative asset paths."""
        dirs: list[str] = []
        if self.package_root and os.path.isdir(self.package_root):
            root = self.package_root
            dirs.append(root)
            for sub in ("assets", "assets/images", "assets/fonts", "assets/scripts",
                        "images", "fonts", "scripts"):
                p = os.path.join(root, sub)
                if os.path.isdir(p):
                    dirs.append(p)
        return dirs

    def resolve_asset_path(self, path: str) -> str:
        """Resolve a package-relative or absolute path to an existing file."""
        if not path:
            return ""
        if os.path.isabs(path) and os.path.isfile(path):
            return path
        for d in self.search_dirs():
            cand = os.path.join(d, path)
            if os.path.isfile(cand):
                return cand
        if os.path.isfile(path):
            return path
        return ""

    def iter_bundled_path_props(self):
        """Yield (node, prop_key, value) for file paths that belong in a package.

        Skips system-ish PATH props (mount_path, device) by only yielding the
        known image/script keys plus asset_paths list entries.
        """
        for n in self.nodes:
            for key in _IMAGE_PATH_KEYS + _SCRIPT_PATH_KEYS:
                val = n.props.get(key)
                if isinstance(val, str) and val.strip():
                    yield n, key, val.strip()
            for key in _ASSET_LIST_KEYS:
                raw = n.props.get(key) or []
                if isinstance(raw, list):
                    for item in raw:
                        if isinstance(item, str) and item.strip():
                            yield n, key, item.strip()

    def collect_font_families(self) -> list[str]:
        """Unique non-empty font_family values used by nodes."""
        seen: set[str] = set()
        out: list[str] = []
        for n in self.nodes:
            fam = (n.props.get("font_family") or "").strip()
            if not fam:
                continue
            key = fam.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(fam)
        return out

    def collect_uncommon_font_families(self) -> list[str]:
        return [
            f for f in self.collect_font_families()
            if f.lower() not in _COMMON_FONT_FAMILIES
        ]

    def import_asset_file(self, source_path: str, *, kind: str = "images") -> str:
        """Copy an external file into the open package (or stage under a temp
        package root) and return the package-relative path to store in props.

        kind: 'images' | 'fonts' | 'scripts'
        """
        if not source_path or not os.path.isfile(source_path):
            raise FileNotFoundError(f"Asset not found: {source_path}")
        if not self.package_root:
            # First import on an unpackaged project: create a staging tree.
            staging = tempfile.mkdtemp(prefix="cstudio-staging-")
            self.package_root = staging
        sub = kind if kind in ("images", "fonts", "scripts") else "images"
        dest_dir = os.path.join(self.package_root, "assets", sub)
        os.makedirs(dest_dir, exist_ok=True)
        basename = _unique_dest_name(dest_dir, os.path.basename(source_path))
        dest = os.path.join(dest_dir, basename)
        # Same file already in place (re-pick) — keep existing relative path.
        try:
            if os.path.isfile(dest) and os.path.samefile(source_path, dest):
                return f"assets/{sub}/{basename}"
        except OSError:
            pass
        shutil.copy2(source_path, dest)
        return f"assets/{sub}/{basename}"

    def _rewrite_paths_into_package(
        self,
        staging_root: str,
        extra_font_files: Optional[list[str]] = None,
    ) -> list[str]:
        """Copy every external asset into staging_root/assets/... and rewrite
        node props to package-relative paths. Returns list of warning strings.
        """
        warnings: list[str] = []
        # Map absolute/old path -> new relative path (dedupe copies).
        mapped: dict[str, str] = {}

        def _ingest(src: str, prop_key: str) -> str:
            if not src:
                return src
            # Already package-relative and present in staging or package_root.
            for root in (staging_root, self.package_root or ""):
                if not root:
                    continue
                cand = os.path.join(root, src)
                if os.path.isfile(cand):
                    # Ensure it's also under staging.
                    rel = src if not os.path.isabs(src) else None
                    if rel and rel.startswith("assets/"):
                        dest = os.path.join(staging_root, rel)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        if os.path.abspath(cand) != os.path.abspath(dest):
                            shutil.copy2(cand, dest)
                        return rel
            resolved = self.resolve_asset_path(src)
            if not resolved or not os.path.isfile(resolved):
                if os.path.isfile(src):
                    resolved = src
                else:
                    warnings.append(f"Missing asset (not packaged): {src}")
                    return src
            if resolved in mapped:
                return mapped[resolved]
            sub = _classify_asset(resolved, prop_key)
            dest_dir = os.path.join(staging_root, "assets", sub)
            os.makedirs(dest_dir, exist_ok=True)
            basename = _unique_dest_name(dest_dir, os.path.basename(resolved))
            dest = os.path.join(dest_dir, basename)
            shutil.copy2(resolved, dest)
            rel = f"assets/{sub}/{basename}"
            mapped[resolved] = rel
            return rel

        for n in self.nodes:
            for key in _IMAGE_PATH_KEYS + _SCRIPT_PATH_KEYS:
                val = n.props.get(key)
                if isinstance(val, str) and val.strip():
                    n.props[key] = _ingest(val.strip(), key)
            for key in _ASSET_LIST_KEYS:
                raw = n.props.get(key)
                if isinstance(raw, list) and raw:
                    n.props[key] = [
                        _ingest(item.strip(), key) if isinstance(item, str) and item.strip() else item
                        for item in raw
                    ]

        for font_path in (extra_font_files or []):
            if not font_path or not os.path.isfile(font_path):
                warnings.append(f"Font file not found (skipped): {font_path}")
                continue
            _ingest(font_path, "font_file")

        return warnings

    def save_package(
        self,
        path: str,
        *,
        extra_font_files: Optional[list[str]] = None,
        manifest_extra: Optional[dict] = None,
        generic_manifest: bool = False,
    ) -> list[str]:
        """Write a self-contained .cstudio zip at path.

        Copies images/scripts/fonts into assets/, rewrites props to relative
        paths, embeds project.json + manifest.json. Returns warnings.

        manifest_extra: optional fields merged into manifest.json (name, author,
        description, notes, …). Ignored when generic_manifest=True.
        generic_manifest: write a minimal default manifest only.
        """
        if not path.lower().endswith(PACKAGE_EXTENSION):
            path = path + PACKAGE_EXTENSION
        path = os.path.abspath(path)

        staging = tempfile.mkdtemp(prefix="cstudio-pack-")
        warnings: list[str] = []
        try:
            # Preserve assets already in an open package tree.
            if self.package_root and os.path.isdir(self.package_root):
                assets_src = os.path.join(self.package_root, "assets")
                if os.path.isdir(assets_src):
                    shutil.copytree(
                        assets_src,
                        os.path.join(staging, "assets"),
                        dirs_exist_ok=True,
                    )

            # Skip path: still pack images/scripts; omit extra user font files
            # unless they were already under assets/fonts from a prior save.
            fonts_to_pack = None if generic_manifest else extra_font_files
            warnings.extend(self._rewrite_paths_into_package(staging, fonts_to_pack))

            self.schema_version = max(int(self.schema_version or 1), SCHEMA_VERSION_PACKAGE)
            project_json_path = os.path.join(staging, PROJECT_JSON_NAME)
            with open(project_json_path, "w", encoding="utf-8") as f:
                f.write(self.to_json())

            if generic_manifest:
                manifest = {
                    "format": "conky-studio-package",
                    "format_version": 1,
                    "schema_version": self.schema_version,
                    "name": self.name or "Untitled HUD",
                    "author": "",
                    "description": "",
                    "notes": "",
                    "generic": True,
                }
            else:
                manifest = {
                    "format": "conky-studio-package",
                    "format_version": 1,
                    "schema_version": self.schema_version,
                    "name": self.name,
                    "author": self.author,
                    "description": self.description,
                    "notes": "",
                }
                if isinstance(manifest_extra, dict):
                    for k, v in manifest_extra.items():
                        if k in ("format", "format_version", "schema_version"):
                            continue
                        manifest[k] = v
                    # Keep project identity in sync with manifest when provided.
                    if "name" in manifest_extra and manifest_extra["name"]:
                        self.name = str(manifest_extra["name"])
                        manifest["name"] = self.name
                    if "author" in manifest_extra:
                        self.author = str(manifest_extra.get("author") or "")
                        manifest["author"] = self.author
                    if "description" in manifest_extra:
                        self.description = str(manifest_extra.get("description") or "")
                        manifest["description"] = self.description
                # Re-write project.json after possible name/author sync.
                with open(project_json_path, "w", encoding="utf-8") as f:
                    f.write(self.to_json())

            with open(os.path.join(staging, MANIFEST_NAME), "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)

            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            # Write zip atomically via temp then replace.
            fd, tmp_zip = tempfile.mkstemp(suffix=PACKAGE_EXTENSION)
            os.close(fd)
            try:
                with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for root, _dirs, files in os.walk(staging):
                        for name in files:
                            full = os.path.join(root, name)
                            arc = os.path.relpath(full, staging)
                            zf.write(full, arcname=arc)
                shutil.move(tmp_zip, path)
            finally:
                if os.path.exists(tmp_zip):
                    try:
                        os.remove(tmp_zip)
                    except OSError:
                        pass

            # Extracted work dir for continued relative-path editing.
            work = _work_dir_for_package(path)
            if os.path.isdir(work):
                shutil.rmtree(work, ignore_errors=True)
            shutil.copytree(staging, work)
            self.package_root = work
            self.source_path = path
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return warnings

    def save_legacy_json(self, path: str) -> None:
        """Write bare project JSON (no assets). Kept for explicit export only."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())
        self.source_path = path

    def save(
        self,
        path: str,
        *,
        extra_font_files: Optional[list[str]] = None,
        manifest_extra: Optional[dict] = None,
        generic_manifest: bool = False,
    ) -> list[str]:
        """Save project. Paths ending in .cstudio become full packages;
        anything else writes legacy JSON for backwards compatibility.

        Returns a list of packaging warnings (always empty for legacy JSON).
        """
        if is_package_path(path):
            return self.save_package(
                path,
                extra_font_files=extra_font_files,
                manifest_extra=manifest_extra,
                generic_manifest=generic_manifest,
            )
        self.save_legacy_json(path)
        return []

    @staticmethod
    def load(path: str) -> "Project":
        """Open a .cstudio package or a legacy .json / Hud.json project.

        Plain .zip files that contain project.json are also accepted so a
        package renamed to .zip (or shared that way) still opens.
        """
        path = os.path.abspath(path)
        lower = path.lower()
        if is_package_path(path) or (
            lower.endswith(".zip") and zipfile.is_zipfile(path)
        ):
            return Project._load_package(path)
        with open(path, "r", encoding="utf-8") as f:
            project = Project.from_json(f.read())
        project.source_path = path
        project.package_root = None
        return project

    @staticmethod
    def load_package_from_zip(path: str) -> "Project":
        """Explicit import entry for a .cstudio or .zip package archive."""
        path = os.path.abspath(path)
        if not zipfile.is_zipfile(path):
            raise ValueError(f"Not a zip archive: {path}")
        return Project._load_package(path)

    @staticmethod
    def _load_package(path: str) -> "Project":
        if not zipfile.is_zipfile(path):
            raise ValueError(f"Not a valid .cstudio package (not a zip): {path}")
        work = _work_dir_for_package(path)
        if os.path.isdir(work):
            shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work, exist_ok=True)
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(work)

        json_path = os.path.join(work, PROJECT_JSON_NAME)
        if not os.path.isfile(json_path):
            # Older / alternate layouts: any single .json at the root.
            candidates = [
                os.path.join(work, name)
                for name in os.listdir(work)
                if name.lower().endswith(".json") and os.path.isfile(os.path.join(work, name))
            ]
            if not candidates:
                raise ValueError(
                    f".cstudio package is missing {PROJECT_JSON_NAME}: {path}"
                )
            json_path = candidates[0]

        with open(json_path, "r", encoding="utf-8") as f:
            project = Project.from_json(f.read())
        project.package_root = work
        project.source_path = path
        return project



