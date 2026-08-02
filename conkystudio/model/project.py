"""
Project data model for Conky Studio.

A Project is the JSON-serializable "source of truth" for one HUD/theme
design edited on the Studio canvas. It intentionally knows nothing about
Qt or Cairo -- the UI (conkystudio.ui.studio) renders it, and the Builder
(conkystudio.codegen.builder) compiles it into a standalone conky.conf +
render.lua + scripts/ bundle that runs with zero runtime dependency on
Conky Studio itself. That separation is what makes projects re-editable:
opening a .cstudio.json file later reconstructs the exact node graph,
instead of having to reverse-engineer hand-written Lua.
"""
from __future__ import annotations

import dataclasses
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = 1
CANVAS_NODE_ID = "canvas"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


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
    nodes: list[NodeInstance] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    groups: list[NodeGroup] = field(default_factory=list)
    labels: list[GraphLabel] = field(default_factory=list)

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
        codegen actually reads (see codegen/conky_conf_gen.py)."""
        n = self.node(CANVAS_NODE_ID)
        if n is None:
            return
        for k, v in n.props.items():
            if hasattr(self.canvas, k):
                setattr(self.canvas, k, v)

    # ---- (de)serialization -------------------------------------------------
    def to_dict(self) -> dict:
        d = {
            "schema_version": self.schema_version,
            "name": self.name,
            "author": self.author,
            "description": self.description,
            "canvas": self.canvas.to_dict(),
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
        p.nodes = [NodeInstance.from_dict(n) for n in d.get("nodes", [])]
        p.edges = [Edge.from_dict(e) for e in d.get("edges", [])]
        p.groups = [NodeGroup.from_dict(g) for g in (d.get("groups") or []) if isinstance(g, dict) and g.get("id")]
        p.labels = [GraphLabel.from_dict(lb) for lb in (d.get("labels") or []) if isinstance(lb, dict) and lb.get("id")]
        # Drop stale member ids that no longer exist
        known = {n.id for n in p.nodes}
        for g in p.groups:
            g.node_ids = [i for i in g.node_ids if i in known]
        p.groups = [g for g in p.groups if g.node_ids]
        p.ensure_canvas_node()
        return p


    @staticmethod
    def from_json(text: str) -> "Project":
        return Project.from_dict(json.loads(text))

    @staticmethod
    def load(path: str) -> "Project":
        with open(path, "r", encoding="utf-8") as f:
            return Project.from_json(f.read())

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

