"""
QGraphicsItem-level pieces of the node canvas: NodeItem (a draggable
box with a coloured header and one row per bindable property), SocketItem
(the small circle you drag a wire from/to), and EdgeItem (the bezier
connecting two sockets). node_canvas.py owns the QGraphicsScene/View that
composes these and keeps them in sync with model.project.Project -- this
module has no knowledge of Project itself, only of drawing and dragging.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsRectItem,
    QGraphicsTextItem,
)
from PyQt6.QtGui import QBrush, QColor, QPen, QPainterPath, QFont
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QObject

from conkystudio.theme import PALETTE
from conkystudio.nodes import registry

NODE_WIDTH = 176
HEADER_H = 26
ROW_H = 22
SOCKET_R = 5

KIND_COLORS = {
    registry.KIND_PERCENT: "#4fd1c5",
    registry.KIND_CELSIUS: "#e08a4f",
    registry.KIND_NUMBER: "#8ab4f8",
    registry.KIND_TEXT: "#d7b8f0",
    registry.KIND_CATEGORY: "#f0c96a",
}


class _Signals(QObject):
    node_moved = pyqtSignal(str)
    node_double_clicked = pyqtSignal(str)
    socket_drag_started = pyqtSignal(object)   # SocketItem
    socket_drag_moved = pyqtSignal(object, QPointF)     # SocketItem, scene pos
    socket_drag_released = pyqtSignal(object, QPointF)  # SocketItem, scene pos
    group_moved = pyqtSignal(str)              # group_id
    group_toggle_collapse = pyqtSignal(str)    # group_id
    group_double_clicked = pyqtSignal(str)     # group_id — rename
    label_moved = pyqtSignal(str)
    label_double_clicked = pyqtSignal(str)


class SocketItem(QGraphicsEllipseItem):
    def __init__(self, node_item: "NodeItem", is_output: bool, prop_key: str, kind: str, parent=None):
        super().__init__(-SOCKET_R, -SOCKET_R, SOCKET_R * 2, SOCKET_R * 2, parent)
        self.node_item = node_item
        self.is_output = is_output
        self.prop_key = prop_key   # "" for a source node's single output
        self.kind = kind
        color = QColor(KIND_COLORS.get(kind, "#9aa2ad"))
        self.setBrush(QBrush(color))
        self.setPen(QPen(QColor(PALETTE["void"]), 1.5))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setZValue(10)
        self._signals = node_item.signals

    def hoverEnterEvent(self, event):
        self.setRect(-SOCKET_R - 2, -SOCKET_R - 2, (SOCKET_R + 2) * 2, (SOCKET_R + 2) * 2)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setRect(-SOCKET_R, -SOCKET_R, SOCKET_R * 2, SOCKET_R * 2)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        self._signals.socket_drag_started.emit(self)
        event.accept()

    def mouseMoveEvent(self, event):
        # Dragging is driven by the scene (it owns the temp rubber-band
        # edge), not by the socket itself -- swallow so the node
        # underneath doesn't also start moving, but forward the position
        # on so the scene can redraw the temp wire to follow the cursor.
        self._signals.socket_drag_moved.emit(self, event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event):
        self._signals.socket_drag_released.emit(self, event.scenePos())
        event.accept()


class NodeItem(QGraphicsRectItem):
    def __init__(self, node_id: str, node_type: str, label: str = "", parent=None):
        self.spec = registry.get(node_type)
        bindable = self.spec.bindable_properties() if self.spec.category in ("visual", "logic") else []
        n_rows = max(1, len(bindable)) if self.spec.category in ("visual", "logic") else 1
        height = HEADER_H + n_rows * ROW_H + 10

        super().__init__(0, 0, NODE_WIDTH, height, parent)
        self.node_id = node_id
        self.node_type = node_type
        self.signals = _Signals()
        self.input_sockets: dict[str, SocketItem] = {}
        self.output_socket: SocketItem | None = None

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )
        self.setBrush(QBrush(QColor(PALETTE["raised"])))
        self.setPen(QPen(QColor(PALETTE["border_strong"]), 1))
        self.setZValue(5)
        # Deliberately no QGraphicsDropShadowEffect here: a per-item graphics
        # effect's painted extent (blur + offset) can outgrow the bounding
        # rect Qt uses to compute the "dirty" region to repaint, which -
        # combined with the view's default MinimalViewportUpdate mode - is
        # exactly the kind of mismatch that leaves stale pixels behind after
        # a selection change or a delete until something forces a full
        # repaint (e.g. zooming). See NodeCanvasView.__init__'s
        # setViewportUpdateMode for the other half of that fix.

        header = QGraphicsRectItem(0, 0, NODE_WIDTH, HEADER_H, self)
        header.setBrush(QBrush(QColor(self.spec.color)))
        header.setPen(QPen(Qt.PenStyle.NoPen))

        title = QGraphicsTextItem(label or self.spec.label, self)
        title.setDefaultTextColor(QColor("#0b0d10"))
        f = QFont(); f.setBold(True); f.setPointSize(9)
        title.setFont(f)
        title.setPos(8, 4)
        title.setTextWidth(NODE_WIDTH - 16)
        self._title = title

        y = HEADER_H + 6
        if self.spec.category == "source":
            desc = QGraphicsTextItem(self._short(self.spec.description, 30), self)
            desc.setDefaultTextColor(QColor(PALETTE["text_muted"]))
            f2 = QFont(); f2.setPointSize(8)
            desc.setFont(f2)
            desc.setPos(8, y)
            desc.setTextWidth(NODE_WIDTH - 16)

            sock = SocketItem(self, True, "", self.spec.output_kind or registry.KIND_NUMBER, self)
            sock.setPos(NODE_WIDTH, HEADER_H + (height - HEADER_H) / 2)
            self.output_socket = sock
        elif self.spec.category in ("visual", "logic"):
            if bindable:
                for prop in bindable:
                    row = QGraphicsTextItem(prop.label, self)
                    row.setDefaultTextColor(QColor(PALETTE["text_secondary"]))
                    f2 = QFont(); f2.setPointSize(8)
                    row.setFont(f2)
                    row.setPos(12, y - 2)
                    sock = SocketItem(self, False, prop.key, (prop.accepts or (registry.KIND_NUMBER,))[0], self)
                    sock.setPos(2, y + 7)
                    self.input_sockets[prop.key] = sock
                    y += ROW_H
            else:
                desc = QGraphicsTextItem(self._short(self.spec.description, 30), self)
                desc.setDefaultTextColor(QColor(PALETTE["text_muted"]))
                f2 = QFont(); f2.setPointSize(8)
                desc.setFont(f2)
                desc.setPos(8, y)
                desc.setTextWidth(NODE_WIDTH - 16)

            # Logic nodes ALSO get an output socket on the right edge (like a
            # source) since their whole purpose is to feed a computed value
            # into something else -- a visual node only ever consumes, so it
            # doesn't get one.
            if self.spec.category == "logic":
                sock = SocketItem(self, True, "", self.spec.output_kind or registry.KIND_NUMBER, self)
                sock.setPos(NODE_WIDTH, HEADER_H + (height - HEADER_H) / 2)
                self.output_socket = sock
        # canvas.root: header only, no sockets, no body text -- settings
        # live entirely in the property panel.

    @staticmethod
    def _short(text: str, n: int) -> str:
        text = text or ""
        return text if len(text) <= n else text[: n - 1] + "\u2026"

    def set_title(self, text: str):
        self._title.setPlainText(text)

    def set_locked_visual(self, locked: bool):
        flags = QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        if not locked:
            flags |= QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        self.setFlags(flags)
        self.setOpacity(0.55 if locked else 1.0)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.signals.node_moved.emit(self.node_id)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        self.signals.node_double_clicked.emit(self.node_id)
        super().mouseDoubleClickEvent(event)

    def socket_scene_pos(self, prop_key: str = "") -> QPointF:
        sock = self.output_socket if prop_key == "" and self.output_socket else self.input_sockets.get(prop_key)
        if sock is None:
            return self.sceneBoundingRect().center()
        return sock.scenePos()


class EdgeItem(QGraphicsPathItem):
    def __init__(self, src_item: NodeItem, dst_item: NodeItem, dst_prop: str, edge_id: str, parent=None):
        super().__init__(parent)
        self.src_item = src_item
        self.dst_item = dst_item
        self.dst_prop = dst_prop
        self.edge_id = edge_id
        # Optional overrides when an endpoint lives inside a collapsed group.
        self.src_override: QPointF | None = None
        self.dst_override: QPointF | None = None
        kind = src_item.output_socket.kind if src_item.output_socket else registry.KIND_NUMBER
        self._color = QColor(KIND_COLORS.get(kind, PALETTE["teal"]))
        pen = QPen(self._color, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.setZValue(1)
        self.update_path()

    def update_path(self):
        p0 = self.src_override if self.src_override is not None else self.src_item.socket_scene_pos("")
        p1 = self.dst_override if self.dst_override is not None else self.dst_item.socket_scene_pos(self.dst_prop)
        dx = max(40.0, abs(p1.x() - p0.x()) * 0.5)
        c1 = QPointF(p0.x() + dx, p0.y())
        c2 = QPointF(p1.x() - dx, p1.y())
        path = QPainterPath(p0)
        path.cubicTo(c1, c2, p1)
        self.setPath(path)

    def set_highlighted(self, on: bool):
        pen = self.pen()
        pen.setWidth(3 if on else 2)
        pen.setColor(self._color.lighter(140) if on else self._color)
        self.setPen(pen)


GROUP_PAD = 18
GROUP_HEADER_H = 28
GROUP_COLLAPSED_W = 160
GROUP_COLLAPSED_H = 44


class GroupItem(QGraphicsRectItem):
    """Frame around a set of nodes. Double-click header to rename;
    click the ▸/▾ affordance (or use the context menu) to collapse."""

    def __init__(self, group_id: str, title: str, color: str = "#3a4048", parent=None):
        super().__init__(0, 0, 200, 120, parent)
        self.group_id = group_id
        self.collapsed = False
        self.signals = _Signals()
        self._member_ids: list[str] = []
        self._title = title

        self.setZValue(0)  # behind nodes (nodes are z=5)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )
        self._apply_style(color)

        self._header_text = QGraphicsTextItem(title, self)
        self._header_text.setDefaultTextColor(QColor(PALETTE["text"]))
        f = QFont(); f.setBold(True); f.setPointSize(9)
        self._header_text.setFont(f)
        self._header_text.setPos(28, 4)

        self._toggle_text = QGraphicsTextItem("\u25be", self)  # ▾
        self._toggle_text.setDefaultTextColor(QColor(PALETTE["text_muted"]))
        self._toggle_text.setFont(f)
        self._toggle_text.setPos(6, 4)

        self._count_text = QGraphicsTextItem("", self)
        self._count_text.setDefaultTextColor(QColor(PALETTE["text_muted"]))
        f2 = QFont(); f2.setPointSize(8)
        self._count_text.setFont(f2)
        self._count_text.setPos(28, 22)

    def _apply_style(self, color: str):
        c = QColor(color)
        c.setAlpha(55)
        self.setBrush(QBrush(c))
        border = QColor(color)
        border.setAlpha(180)
        self.setPen(QPen(border, 1.5, Qt.PenStyle.DashLine))

    def set_title(self, title: str):
        self._title = title
        self._header_text.setPlainText(title)

    def set_members(self, member_ids: list[str]):
        self._member_ids = list(member_ids)
        n = len(self._member_ids)
        self._count_text.setPlainText(f"{n} node{'s' if n != 1 else ''}")

    def set_collapsed_visual(self, collapsed: bool):
        self.collapsed = collapsed
        self._toggle_text.setPlainText("\u25b8" if collapsed else "\u25be")  # ▸ / ▾
        if collapsed:
            self.setRect(0, 0, GROUP_COLLAPSED_W, GROUP_COLLAPSED_H)
            self._count_text.setVisible(True)
        else:
            self._count_text.setVisible(False)

    def fit_to_members(self, member_items: list[NodeItem]):
        """Resize/reposition the frame around visible member node items (expanded)."""
        if self.collapsed:
            return
        if not member_items:
            self.setRect(0, 0, 160, 60)
            return
        rects = [it.sceneBoundingRect() for it in member_items]
        left = min(r.left() for r in rects) - GROUP_PAD
        top = min(r.top() for r in rects) - GROUP_PAD - GROUP_HEADER_H
        right = max(r.right() for r in rects) + GROUP_PAD
        bottom = max(r.bottom() for r in rects) + GROUP_PAD
        self.setPos(left, top)
        self.setRect(0, 0, max(120.0, right - left), max(60.0, bottom - top))

    def attachment_point(self, toward: QPointF | None = None) -> QPointF:
        """Scene point used for edges that terminate on a collapsed group."""
        r = self.sceneBoundingRect()
        if toward is None:
            return r.center()
        # Pick the side closest to the other endpoint.
        cx, cy = r.center().x(), r.center().y()
        if abs(toward.x() - cx) > abs(toward.y() - cy):
            x = r.right() if toward.x() > cx else r.left()
            return QPointF(x, cy)
        y = r.bottom() if toward.y() > cy else r.top()
        return QPointF(cx, y)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.signals.group_moved.emit(self.group_id)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        # Toggle on the left glyph area; rename on the rest of the header.
        if event.pos().x() < 24:
            self.signals.group_toggle_collapse.emit(self.group_id)
        else:
            self.signals.group_double_clicked.emit(self.group_id)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.pos().x() < 24 and event.pos().y() < GROUP_HEADER_H:
            self.signals.group_toggle_collapse.emit(self.group_id)
            event.accept()
            return
        super().mousePressEvent(event)


class LabelItem(QGraphicsTextItem):
    """Free-form canvas annotation. Double-click to edit."""

    def __init__(self, label_id: str, text: str, color: str = "#9aa2ad", font_size: int = 12, parent=None):
        super().__init__(text, parent)
        self.label_id = label_id
        self.signals = _Signals()
        self.setDefaultTextColor(QColor(color))
        f = QFont()
        f.setPointSize(font_size)
        f.setItalic(True)
        self.setFont(f)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )
        self.setZValue(6)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.signals.label_moved.emit(self.label_id)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        self.signals.label_double_clicked.emit(self.label_id)
        super().mouseDoubleClickEvent(event)

