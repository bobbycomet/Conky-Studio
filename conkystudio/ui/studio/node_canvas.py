"""
The Studio's central canvas: a QGraphicsScene holding one NodeItem per
Project node and one EdgeItem per Project edge, plus a QGraphicsView with
a dotted-grid background, drag-and-drop node creation from the palette,
and delete-key support. NodeCanvasScene is the single place that keeps
the Qt graphics items and the Project model in agreement -- every method
that touches self.project also updates the matching graphics items (or
vice versa), so nothing else in the app should mutate Project.nodes/edges
directly while a canvas has it open.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsPathItem, QMenu, QInputDialog
from PyQt6.QtGui import QColor, QPen, QPainterPath, QPainter, QTransform, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal

from conkystudio.theme import PALETTE
from conkystudio.model.project import Project, NodeInstance, new_id
from conkystudio.nodes import registry
from conkystudio.nodes.canvas import CANVAS_NODE_ID
from conkystudio.ui.studio.graphics_items import (
    NodeItem, EdgeItem, SocketItem, GroupItem, LabelItem, KIND_COLORS,
)
NODE_MIME_TYPE = "application/x-conkystudio-node"


def _effective_output_kind(project: Project, node: NodeInstance) -> str:
    spec = registry.get(node.type)
    if node.type == "source.custom_script":
        return node.props.get("output_kind", "text")
    return spec.output_kind or registry.KIND_NUMBER


class NodeCanvasScene(QGraphicsScene):
    graph_changed = pyqtSignal()
    node_selected = pyqtSignal(str)   # "" when nothing selected

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.node_items: dict[str, NodeItem] = {}
        self.edge_items: dict[str, EdgeItem] = {}
        self.group_items: dict[str, GroupItem] = {}
        self.label_items: dict[str, LabelItem] = {}
        self.setBackgroundBrush(QColor(PALETTE["inset"]))

        self._drag_origin: SocketItem | None = None
        self._temp_edge: QGraphicsPathItem | None = None
        self._suppress_group_move = False

        self.selectionChanged.connect(self._on_selection_changed)
        self.rebuild_from_project()

    # ------------------------------------------------------------ build
    def rebuild_from_project(self):
        self.clear()
        self.node_items.clear()
        self.edge_items.clear()
        self.group_items.clear()
        self.label_items.clear()
        for n in self.project.nodes:
            self._add_node_item(n)
        for e in self.project.edges:
            self._add_edge_item(e.id, e.src_node, e.dst_node, e.dst_prop)
        for g in self.project.groups:
            self._add_group_item(g)
        for lb in self.project.labels:
            self._add_label_item(lb)
        self._apply_collapse_state()
        self._refit_all_groups()

    def _add_node_item(self, n: NodeInstance) -> NodeItem:
        item = NodeItem(n.id, n.type, n.label)
        item.setPos(n.x, n.y)
        item.set_locked_visual(n.locked)
        item.signals.node_moved.connect(self._on_node_moved)
        item.signals.socket_drag_started.connect(self._on_drag_started)
        item.signals.socket_drag_moved.connect(self._on_drag_moved)
        item.signals.socket_drag_released.connect(self._on_drag_released)
        self.addItem(item)
        self.node_items[n.id] = item
        return item

    def apply_lock_state(self, node_id: str):
        item = self.node_items.get(node_id)
        n = self.project.node(node_id)
        if item and n:
            item.set_locked_visual(n.locked)

    def _add_edge_item(self, edge_id: str, src_id: str, dst_id: str, dst_prop: str):
        src_item = self.node_items.get(src_id)
        dst_item = self.node_items.get(dst_id)
        if not src_item or not dst_item:
            return
        edge_item = EdgeItem(src_item, dst_item, dst_prop, edge_id)
        self.addItem(edge_item)
        self.edge_items[edge_id] = edge_item

    def _add_group_item(self, g) -> GroupItem:
        item = GroupItem(g.id, g.title, g.color)
        item.set_members(g.node_ids)
        item.set_collapsed_visual(g.collapsed)
        if g.collapsed:
            item.setPos(g.x, g.y)
        item.signals.group_moved.connect(self._on_group_moved)
        item.signals.group_toggle_collapse.connect(self.toggle_group_collapsed)
        item.signals.group_double_clicked.connect(self._rename_group)
        self.addItem(item)
        self.group_items[g.id] = item
        return item

    def _add_label_item(self, lb) -> LabelItem:
        item = LabelItem(lb.id, lb.text, lb.color, lb.font_size)
        item.setPos(lb.x, lb.y)
        item.signals.label_moved.connect(self._on_label_moved)
        item.signals.label_double_clicked.connect(self._edit_label)
        self.addItem(item)
        self.label_items[lb.id] = item
        return item

    # ------------------------------------------------------------ mutation API
    def add_node(self, node_type: str, pos: QPointF, label: str = "") -> NodeInstance:
        n = NodeInstance(id=new_id("n"), type=node_type, x=pos.x(), y=pos.y(), label=label,
                          props=registry.get(node_type).defaults(), z=self.project.next_z())
        self.project.add_node(n)
        self._add_node_item(n)
        self.graph_changed.emit()
        return n

    def remove_node(self, node_id: str):
        if node_id == CANVAS_NODE_ID:
            return
        for edge_id in [eid for eid, e in list(self.edge_items.items())
                        if e.src_item.node_id == node_id or e.dst_item.node_id == node_id]:
            self._remove_edge_item(edge_id)
        item = self.node_items.pop(node_id, None)
        if item:
            self.removeItem(item)
        self.project.remove_node(node_id)
        self.graph_changed.emit()

    def _remove_edge_item(self, edge_id: str):
        item = self.edge_items.pop(edge_id, None)
        if item:
            self.removeItem(item)

    def disconnect_prop(self, dst_node_id: str, dst_prop: str):
        edge = self.project.edge_for_prop(dst_node_id, dst_prop)
        if edge is None:
            return
        self._remove_edge_item(edge.id)
        self.project.remove_edge(edge.id)
        self.graph_changed.emit()

    # ------------------------------------------------------------ node move
    def _on_node_moved(self, node_id: str):
        item = self.node_items.get(node_id)
        n = self.project.node(node_id)
        if item and n:
            n.x, n.y = item.pos().x(), item.pos().y()
        for e in self.edge_items.values():
            if e.src_item.node_id == node_id or e.dst_item.node_id == node_id:
                e.update_path()
        g = self.project.group_for_node(node_id)
        if g and not g.collapsed:
            self._refit_group(g.id)
        self.graph_changed.emit()

    def _on_selection_changed(self):
        selected = [it for it in self.selectedItems() if isinstance(it, NodeItem)]
        node_id = selected[0].node_id if selected else ""
        self.node_selected.emit(node_id)
        self.highlight_data_flow(node_id)

    def highlight_data_flow(self, node_id: str):
        related: set[str] = set()
        if node_id:
            for e in self.project.edges:
                if e.src_node == node_id or e.dst_node == node_id:
                    related.add(e.id)
            upstream = {e.src_node for e in self.project.edges if e.dst_node == node_id}
            downstream = {e.dst_node for e in self.project.edges if e.src_node == node_id}
            for e in self.project.edges:
                if e.dst_node in upstream or e.src_node in downstream:
                    related.add(e.id)
        for eid, item in self.edge_items.items():
            item.set_highlighted(bool(node_id) and eid in related)

    # ------------------------------------------------------------ groups / labels
    def group_selected_nodes(self, title: str = "Group"):
        ids = [
            it.node_id for it in self.selectedItems()
            if isinstance(it, NodeItem) and it.node_id != CANVAS_NODE_ID
        ]
        if len(ids) < 2:
            return None
        g = self.project.add_group(title, ids)
        item = self._add_group_item(g)
        self._refit_group(g.id)
        self.graph_changed.emit()
        return g

    def ungroup_selected(self):
        changed = False
        for it in list(self.selectedItems()):
            gid = None
            if isinstance(it, GroupItem):
                gid = it.group_id
            elif isinstance(it, NodeItem):
                g = self.project.group_for_node(it.node_id)
                gid = g.id if g else None
            if gid:
                self._remove_group_item(gid)
                self.project.remove_group(gid)
                changed = True
        if changed:
            self._apply_collapse_state()
            self.graph_changed.emit()

    def toggle_group_collapsed(self, group_id: str):
        g = self.project.group(group_id)
        if g is None:
            return
        g.collapsed = not g.collapsed
        self._apply_collapse_state()
        self._refit_group(group_id)
        self.graph_changed.emit()

    def _remove_group_item(self, group_id: str):
        item = self.group_items.pop(group_id, None)
        if item:
            self.removeItem(item)

    def _refit_group(self, group_id: str):
        g = self.project.group(group_id)
        item = self.group_items.get(group_id)
        if not g or not item:
            return
        item.set_members(g.node_ids)
        item.set_collapsed_visual(g.collapsed)
        self._suppress_group_move = True
        try:
            if g.collapsed:
                item.setPos(g.x, g.y)
            else:
                members = [self.node_items[nid] for nid in g.node_ids if nid in self.node_items]
                item.fit_to_members(members)
                g.x, g.y = item.pos().x(), item.pos().y()
        finally:
            self._suppress_group_move = False

    def _refit_all_groups(self):
        for gid in list(self.group_items.keys()):
            self._refit_group(gid)

    def _apply_collapse_state(self):
        """Hide members of collapsed groups; route cross-boundary edges to the chip."""
        collapsed_of: dict[str, str] = {}  # node_id -> group_id
        for g in self.project.groups:
            for nid in g.node_ids:
                if g.collapsed:
                    collapsed_of[nid] = g.id

        for nid, nitem in self.node_items.items():
            hide = nid in collapsed_of
            nitem.setVisible(not hide)

        for e in self.project.edges:
            eitem = self.edge_items.get(e.id)
            if eitem is None:
                continue
            src_g = collapsed_of.get(e.src_node)
            dst_g = collapsed_of.get(e.dst_node)
            # Fully internal to one collapsed group — hide the wire.
            if src_g and src_g == dst_g:
                eitem.setVisible(False)
                eitem.src_override = None
                eitem.dst_override = None
                continue
            eitem.setVisible(True)
            if src_g:
                gitem = self.group_items.get(src_g)
                other = eitem.dst_item.socket_scene_pos(e.dst_prop) if eitem.dst_item.isVisible() else None
                eitem.src_override = gitem.attachment_point(other) if gitem else None
            else:
                eitem.src_override = None
            if dst_g:
                gitem = self.group_items.get(dst_g)
                other = eitem.src_item.socket_scene_pos("") if eitem.src_item.isVisible() else None
                eitem.dst_override = gitem.attachment_point(other) if gitem else None
            else:
                eitem.dst_override = None
            eitem.update_path()

    def _on_group_moved(self, group_id: str):
        if self._suppress_group_move:
            return
        g = self.project.group(group_id)
        item = self.group_items.get(group_id)
        if not g or not item:
            return
        new_pos = item.pos()
        dx = new_pos.x() - g.x
        dy = new_pos.y() - g.y
        g.x, g.y = new_pos.x(), new_pos.y()
        if dx or dy:
            # Members always travel with the frame (expanded or collapsed).
            for nid in g.node_ids:
                n = self.project.node(nid)
                nitem = self.node_items.get(nid)
                if n:
                    n.x += dx
                    n.y += dy
                if nitem:
                    nitem.blockSignals(True) if hasattr(nitem, "blockSignals") else None
                    nitem.setPos(nitem.pos() + QPointF(dx, dy))
            for e in self.edge_items.values():
                if e.src_item.node_id in g.node_ids or e.dst_item.node_id in g.node_ids:
                    e.update_path()
            if g.collapsed:
                self._apply_collapse_state()
        self.graph_changed.emit()

    def _rename_group(self, group_id: str):
        g = self.project.group(group_id)
        item = self.group_items.get(group_id)
        if not g:
            return
        text, ok = QInputDialog.getText(None, "Rename group", "Title:", text=g.title)
        if ok and text.strip():
            g.title = text.strip()
            if item:
                item.set_title(g.title)
            self.graph_changed.emit()

    def add_label_at(self, pos: QPointF, text: str = "Label"):
        lb = self.project.add_label(text, pos.x(), pos.y())
        self._add_label_item(lb)
        self.graph_changed.emit()
        return lb

    def _on_label_moved(self, label_id: str):
        lb = self.project.label(label_id)
        item = self.label_items.get(label_id)
        if lb and item:
            lb.x, lb.y = item.pos().x(), item.pos().y()
            self.graph_changed.emit()

    def _edit_label(self, label_id: str):
        lb = self.project.label(label_id)
        item = self.label_items.get(label_id)
        if not lb:
            return
        text, ok = QInputDialog.getMultiLineText(None, "Edit label", "Text:", text=lb.text)
        if ok:
            lb.text = text
            if item:
                item.setPlainText(text)
            self.graph_changed.emit()

    def remove_label(self, label_id: str):
        item = self.label_items.pop(label_id, None)
        if item:
            self.removeItem(item)
        self.project.remove_label(label_id)
        self.graph_changed.emit()

    # ------------------------------------------------------------ connection dragging
    def _on_drag_started(self, socket: SocketItem):
        origin = socket
        if not socket.is_output and socket.prop_key:
            existing = self.project.edge_for_prop(socket.node_item.node_id, socket.prop_key)
            if existing is not None:
                src_item = self.node_items.get(existing.src_node)
                self._remove_edge_item(existing.id)
                self.project.remove_edge(existing.id)
                self.graph_changed.emit()
                if src_item and src_item.output_socket:
                    origin = src_item.output_socket
        self._drag_origin = origin
        pen = QPen(QColor(KIND_COLORS.get(origin.kind, PALETTE["teal"])), 2, Qt.PenStyle.DashLine)
        self._temp_edge = QGraphicsPathItem()
        self._temp_edge.setPen(pen)
        self._temp_edge.setZValue(20)
        self.addItem(self._temp_edge)

    def _on_drag_moved(self, socket: SocketItem, scene_pos: QPointF):
        if self._temp_edge is None or self._drag_origin is None:
            return
        p0 = self._drag_origin.scenePos()
        path = QPainterPath(p0)
        dx = max(40.0, abs(scene_pos.x() - p0.x()) * 0.5)
        path.cubicTo(QPointF(p0.x() + dx, p0.y()), QPointF(scene_pos.x() - dx, scene_pos.y()), scene_pos)
        self._temp_edge.setPath(path)

    def _on_drag_released(self, socket: SocketItem, scene_pos: QPointF):
        if self._temp_edge is not None:
            self.removeItem(self._temp_edge)
            self._temp_edge = None
        origin = self._drag_origin
        self._drag_origin = None
        if origin is None:
            return

        target = self._socket_at(scene_pos, exclude={origin})
        if target is None:
            return
        if target.is_output == origin.is_output:
            return  # both outputs or both inputs -- not a valid connection

        out_sock = origin if origin.is_output else target
        in_sock = target if origin.is_output else origin
        if out_sock.node_item.node_id == in_sock.node_item.node_id:
            return  # no self-loops

        pspec = registry.get(in_sock.node_item.node_type).prop(in_sock.prop_key)
        src_node = self.project.node(out_sock.node_item.node_id)
        out_kind = _effective_output_kind(self.project, src_node) if src_node else out_sock.kind
        if pspec and pspec.accepts and out_kind not in pspec.accepts:
            return  # incompatible kinds -- silently refuse, sockets are colour-coded to explain why

        self.disconnect_prop(in_sock.node_item.node_id, in_sock.prop_key)
        edge = self.project.add_edge(out_sock.node_item.node_id, in_sock.node_item.node_id, in_sock.prop_key)
        self._add_edge_item(edge.id, edge.src_node, edge.dst_node, edge.dst_prop)
        self.graph_changed.emit()

    def _socket_at(self, pos: QPointF, exclude: set) -> SocketItem | None:
        for it in self.items(pos, deviceTransform=QTransform()):
            if isinstance(it, SocketItem) and it not in exclude:
                return it
        return None

    def refresh_node_label(self, node_id: str, new_label: str):
        n = self.project.node(node_id)
        item = self.node_items.get(node_id)
        if n:
            n.label = new_label
        if item:
            item.set_title(new_label or registry.get(n.type).label)
        self.graph_changed.emit()


class NodeCanvasView(QGraphicsView):
    delete_requested = pyqtSignal(str)
    node_type_dropped = pyqtSignal(str, QPointF)

    def __init__(self, scene: NodeCanvasScene, parent=None):
        super().__init__(scene, parent)
        self._scene = scene
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        # FullViewportUpdate trades a bit of redraw efficiency for
        # correctness: the default MinimalViewportUpdate mode was leaving
        # stale pixels on screen after selecting a node or deleting one,
        # only clearing on the next event (like a zoom) that happens to
        # force a full repaint. For a canvas with dozens of nodes, not
        # thousands, that cost is not worth the visual bugs it was causing.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        # Left-click-drag on empty canvas now pans the view (this is what
        # "navigate without the scrollbars" needs); holding Shift switches
        # to rubber-band selection instead -- see mousePressEvent below.
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setAcceptDrops(True)
        self.setSceneRect(-2000, -2000, 5000, 5000)
        self.centerOn(150, 150)
        self._grid_step = 24

        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, activated=self._delete_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, activated=self._delete_selected)

    def mousePressEvent(self, event):
        # Shift+left-click = rubber-band select; plain left-click on empty
        # canvas = pan. Clicking directly on a node/socket still reaches
        # that item first regardless of drag mode, so this doesn't get in
        # the way of moving nodes or drawing connections.
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        super().mousePressEvent(event)

    def _delete_selected(self):
        for it in list(self._scene.selectedItems()):
            if isinstance(it, NodeItem) and it.node_id != CANVAS_NODE_ID:
                self._scene.remove_node(it.node_id)
            elif isinstance(it, LabelItem):
                self._scene.remove_label(it.label_id)
            elif isinstance(it, GroupItem):
                # Delete key dissolves the group frame only (keeps nodes).
                self._scene.project.remove_group(it.group_id)
                self._scene._remove_group_item(it.group_id)
                self._scene._apply_collapse_state()
                self._scene.graph_changed.emit()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        scene_pos = self.mapToScene(event.pos())
        selected_nodes = [
            it for it in self._scene.selectedItems()
            if isinstance(it, NodeItem) and it.node_id != CANVAS_NODE_ID
        ]
        selected_groups = [it for it in self._scene.selectedItems() if isinstance(it, GroupItem)]
        selected_labels = [it for it in self._scene.selectedItems() if isinstance(it, LabelItem)]

        if len(selected_nodes) >= 2:
            menu.addAction("Group selection", lambda: self._group_selection())
        if selected_groups or any(self._scene.project.group_for_node(n.node_id) for n in selected_nodes):
            menu.addAction("Ungroup", self._scene.ungroup_selected)
        for git in selected_groups:
            g = self._scene.project.group(git.group_id)
            if g:
                label = "Expand group" if g.collapsed else "Collapse group"
                menu.addAction(label, lambda gid=git.group_id: self._scene.toggle_group_collapsed(gid))
                menu.addAction("Rename group…", lambda gid=git.group_id: self._scene._rename_group(gid))
        menu.addSeparator()
        menu.addAction("Add label here", lambda: self._add_label(scene_pos))
        if selected_labels:
            menu.addAction("Edit label…", lambda: self._scene._edit_label(selected_labels[0].label_id))
            menu.addAction("Delete label", lambda: self._scene.remove_label(selected_labels[0].label_id))
        menu.addSeparator()
        menu.addAction("Delete", self._delete_selected)
        menu.exec(event.globalPos())

    def _group_selection(self):
        title, ok = QInputDialog.getText(self, "Group nodes", "Group title:", text="Group")
        if ok:
            self._scene.group_selected_nodes(title.strip() or "Group")

    def _add_label(self, scene_pos: QPointF):
        text, ok = QInputDialog.getMultiLineText(self, "Add label", "Text:", text="Note")
        if ok and text.strip():
            self._scene.add_label_at(scene_pos, text.strip())

    def drawBackground(self, painter, rect: QRectF):
        super().drawBackground(painter, rect)
        painter.fillRect(rect, QColor(PALETTE["inset"]))
        pen = QPen(QColor(PALETTE["border"]))
        pen.setWidth(0)
        painter.setPen(pen)
        step = self._grid_step
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)
        x = left
        while x < rect.right():
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
            x += step * 4
        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)
            y += step * 4

        if len(self._scene.project.nodes) <= 1:
            painter.save()
            hint_pen = QPen(QColor(PALETTE["text_muted"]))
            painter.setPen(hint_pen)
            font = painter.font()
            font.setPointSize(13)
            painter.setFont(font)
            text = ("Drag a node from the left to begin \u2014 or Project \u2192 New HUD for a starter layout "
                    "with a couple of nodes already wired up.")
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
            painter.restore()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    # ---- drag-and-drop node creation from the palette --------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(NODE_MIME_TYPE):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(NODE_MIME_TYPE):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(NODE_MIME_TYPE):
            return
        node_type = bytes(event.mimeData().data(NODE_MIME_TYPE)).decode("utf-8")
        scene_pos = self.mapToScene(event.position().toPoint())
        self.node_type_dropped.emit(node_type, scene_pos)
        event.acceptProposedAction()

    def context_menu_for(self, screen_pos):
        menu = QMenu(self)
        menu.addAction("Delete", self._delete_selected)
        menu.exec(screen_pos)

