"""
Position Stage — screen-space layout dock for Conky Studio.

Separate from the node-graph canvas (data flow / wiring). This dock shows a
plane the size of the selected window (or project.canvas for the legacy
single-window path). Visual nodes appear as draggable proxies; moving them
writes back to the same x/y or cx/cy props the property panel edits, so Live
Preview and Build see the change through the existing graph_changed path.

Wire from studio_tab similar to WindowsPanel / PreviewPanel:

    from conkystudio.ui.studio.position_stage import PositionStagePanel

    self.position_stage = PositionStagePanel(self.project)
    self.position_stage.layout_changed.connect(self._on_graph_changed)
    self.position_stage.node_selected.connect(self._on_stage_node_selected)
    # Tabify with Preview / Layers / Windows docks:
    # self.tabifyDockWidget(self.preview_dock, position_stage_dock)

Does not replace the property-panel spinboxes — it is an alternate editor.

Snap bugfix + per-node position lock
---------------------------------------
Snap is applied in StageProxyItem.itemChange(ItemPositionChange) on the
*proposed* position before Qt applies it.  This avoids fighting the live
drag with post-move setPos() (which made proxies feel glued and could leave
them stuck after Snap was turned off).

Also:
• Respects Project node.locked (Layers dock lock) on stage proxies.
• Adds a "Lock position" checkbox for the currently selected proxy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QCheckBox, QSpinBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsSimpleTextItem, QGraphicsItem, QFrame, QSizePolicy,
)
from PyQt6.QtGui import (
    QColor, QPen, QBrush, QPainter, QFont, QWheelEvent, QMouseEvent,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal, QLineF

from conkystudio.model.project import Project, NodeInstance
from conkystudio.nodes import registry
from conkystudio.nodes.canvas import CANVAS_NODE_ID
from conkystudio.theme import PALETTE


# How far past the window rect the scrollable stage extends (each side).
_STAGE_MARGIN = 200

# Minimum proxy size so tiny nodes stay grab-able.
_MIN_PROXY = 16

# Default estimated size when a node has no width/height/radius props.
_DEFAULT_W = 48
_DEFAULT_H = 48


@dataclass
class _PosKeys:
    """Which property pair a visual node uses for screen position."""
    x_key: str  # "x" or "cx"
    y_key: str  # "y" or "cy"
    is_center: bool  # True when cx/cy — proxy centre maps to the value


def _position_keys(node: NodeInstance) -> Optional[_PosKeys]:
    """Return the position property pair for a visual node, or None if none."""
    if not registry.has(node.type):
        return None
    spec = registry.get(node.type)
    if spec.category != "visual":
        return None
    keys = {p.key for p in spec.properties}
    if "cx" in keys and "cy" in keys:
        return _PosKeys("cx", "cy", is_center=True)
    if "x" in keys and "y" in keys:
        return _PosKeys("x", "y", is_center=False)
    return None


def _estimate_size(node: NodeInstance) -> tuple[float, float]:
    """Approximate on-stage width/height from common size props."""
    p = node.props
    if "width" in p and "height" in p:
        return max(_MIN_PROXY, float(p.get("width", _DEFAULT_W))), max(
            _MIN_PROXY, float(p.get("height", _DEFAULT_H))
        )
    if "size" in p:
        s = max(_MIN_PROXY, float(p.get("size", _DEFAULT_W)))
        return s, s
    if "radius" in p:
        r = max(_MIN_PROXY / 2, float(p.get("radius", 30)))
        return r * 2, r * 2
    if "blade_length" in p:
        bl = float(p.get("blade_length", 60))
        return bl * 2, bl * 2
    if "length" in p and "line_width" in p:
        # hline / vline — thin strip
        length = float(p.get("length", 100))
        lw = max(4.0, float(p.get("line_width", 2)))
        if node.type == "visual.vline":
            return lw * 3, length
        return length, lw * 3
    if "bar_count" in p and "bar_width" in p:
        n = int(p.get("bar_count", 16))
        bw = int(p.get("bar_width", 6))
        gap = int(p.get("gap", 3))
        mh = int(p.get("max_height", 60))
        return float(n * bw + (n - 1) * gap), float(mh)
    if "core_count" in p:
        n = int(p.get("core_count", 8))
        bw = int(p.get("bar_width", 10))
        gap = int(p.get("gap", 3))
        bh = int(p.get("bar_height", 48))
        return float(n * bw + (n - 1) * gap), float(bh)
    return float(_DEFAULT_W), float(_DEFAULT_H)


def _read_pos(node: NodeInstance, keys: _PosKeys) -> tuple[float, float]:
    p = node.props
    x = float(p.get(keys.x_key, 0) or 0)
    y = float(p.get(keys.y_key, 0) or 0)
    return x, y


def _write_pos(node: NodeInstance, keys: _PosKeys, x: float, y: float) -> None:
    node.props[keys.x_key] = int(round(x))
    node.props[keys.y_key] = int(round(y))


def _snap(v: float, step: int) -> float:
    if step <= 1:
        return round(v)
    return round(v / step) * step


# ---------------------------------------------------------------------------
# Graphics items
# ---------------------------------------------------------------------------

class StageProxyItem(QGraphicsRectItem):
    """Draggable rectangle representing one visual node on the stage."""

    def __init__(self, node_id: str, label: str, w: float, h: float, parent=None):
        super().__init__(0, 0, w, h, parent)
        self.node_id = node_id
        self._label = label
        self._locked = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self._brush_normal = QBrush(QColor(PALETTE["teal_soft"]))
        self._brush_selected = QBrush(QColor(PALETTE["teal_dim"]))
        self._brush_locked = QBrush(QColor(PALETTE.get("border", "#3a4048")))
        self._pen = QPen(QColor(PALETTE["teal"]), 1.5)
        self._pen_selected = QPen(QColor(PALETTE["gold"]), 2.0)
        self._pen_locked = QPen(QColor(PALETTE.get("text_muted", "#9aa2ad")), 1.5, Qt.PenStyle.DashLine)
        self.setBrush(self._brush_normal)
        self.setPen(self._pen)

        self._text = QGraphicsSimpleTextItem(label, self)
        self._text.setBrush(QBrush(QColor(PALETTE["text"])))
        # Labels must not steal mouse events — otherwise clicks land on the
        # text child and the parent proxy never starts a drag (especially
        # after graph selection raises z-order so the label is under the cursor).
        self._text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._text.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._text.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        self._text.setFont(font)
        self._layout_text()

        self._on_moved = None  # callback set by scene
        self._suppress_move = False

    def _layout_text(self):
        br = self._text.boundingRect()
        r = self.rect()
        self._text.setPos(
            max(2, (r.width() - br.width()) / 2),
            max(2, (r.height() - br.height()) / 2),
        )

    def set_size(self, w: float, h: float):
        self.setRect(0, 0, w, h)
        self._layout_text()

    def set_label(self, label: str):
        self._label = label
        self._text.setText(label)
        self._layout_text()

    def set_locked(self, locked: bool):
        """Freeze proxy position (and visual style). Mirrors Layers lock."""
        self._locked = bool(locked)
        # Always re-assert flags so a prior selection / refresh / focus loss
        # cannot leave proxies stuck non-movable.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not self._locked)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setOpacity(0.55 if self._locked else 1.0)
        # Restyle only when not selected, so selection still reads clearly
        if self.isSelected():
            self.setBrush(self._brush_selected)
            self.setPen(self._pen_selected)
        elif self._locked:
            self.setBrush(self._brush_locked)
            self.setPen(self._pen_locked)
        else:
            self.setBrush(self._brush_normal)
            self.setPen(self._pen)

    def itemChange(self, change, value):
        # --- Snap: rewrite the *proposed* position before Qt applies it -----
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if self._locked:
                return self.pos()  # refuse any move while locked
            scene = self.scene()
            if (
                scene is not None
                and getattr(scene, "_snap_enabled", False)
                and not self._suppress_move
            ):
                step = max(1, int(getattr(scene, "_snap_step", 10)))
                keys = getattr(scene, "_pos_keys", {}).get(self.node_id)
                r = self.rect()
                # value is the proposed top-left of the proxy
                proposed = value if isinstance(value, QPointF) else QPointF(value)
                if keys is not None and keys.is_center:
                    # Snap the *center* (cx/cy), then convert back to top-left
                    cx = proposed.x() + r.width() / 2
                    cy = proposed.y() + r.height() / 2
                    cx = _snap(cx, step)
                    cy = _snap(cy, step)
                    return QPointF(cx - r.width() / 2, cy - r.height() / 2)
                else:
                    return QPointF(_snap(proposed.x(), step), _snap(proposed.y(), step))
            return value

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if not self._suppress_move and self._on_moved:
                self._on_moved(self)

        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if value:
                self.setBrush(self._brush_selected)
                self.setPen(self._pen_selected)
                self.setZValue(20)
            else:
                if self._locked:
                    self.setBrush(self._brush_locked)
                    self.setPen(self._pen_locked)
                else:
                    self.setBrush(self._brush_normal)
                    self.setPen(self._pen)
                self.setZValue(10)
        return super().itemChange(change, value)


class StageScene(QGraphicsScene):
    """Scene holding the window frame + visual proxies."""

    proxy_moved = pyqtSignal(str)       # node_id after a drag settle
    proxy_selected = pyqtSignal(str)   # node_id or ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._win_w = 460
        self._win_h = 640
        self._frame: QGraphicsRectItem | None = None
        self._center_cross: list = []
        self._grid_lines: list = []
        self._proxies: dict[str, StageProxyItem] = {}
        self._snap_enabled = False
        self._snap_step = 10
        self._pos_keys: dict[str, _PosKeys] = {}  # node_id -> keys
        self._project: Project | None = None
        self.selectionChanged.connect(self._on_selection)

    def set_window_size(self, w: int, h: int):
        self._win_w = max(64, w)
        self._win_h = max(64, h)
        self._rebuild_frame()

    def set_snap(self, enabled: bool, step: int):
        self._snap_enabled = enabled
        self._snap_step = max(1, step)

    def set_project(self, project: Project | None):
        self._project = project

    def _rebuild_frame(self):
        # Clear frame/grid decorations only (keep proxies)
        for item in list(self._center_cross) + list(self._grid_lines):
            self.removeItem(item)
        self._center_cross.clear()
        self._grid_lines.clear()
        if self._frame is not None:
            self.removeItem(self._frame)
            self._frame = None

        margin = _STAGE_MARGIN
        self.setSceneRect(
            -margin, -margin,
            self._win_w + 2 * margin,
            self._win_h + 2 * margin,
        )

        # Window boundary — decoration only; never steals clicks from proxies.
        self._frame = QGraphicsRectItem(0, 0, self._win_w, self._win_h)
        self._frame.setPen(QPen(QColor(PALETTE["teal"]), 2, Qt.PenStyle.SolidLine))
        self._frame.setBrush(QBrush(QColor(PALETTE["inset"])))
        self._frame.setZValue(0)
        self._frame.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self._frame.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self._frame.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.addItem(self._frame)

        # Subtle grid inside the window
        grid_pen = QPen(QColor(PALETTE["border"]), 0, Qt.PenStyle.DotLine)
        step = 40
        x = 0
        while x <= self._win_w:
            line = self.addLine(QLineF(x, 0, x, self._win_h), grid_pen)
            line.setZValue(1)
            self._grid_lines.append(line)
            x += step
        y = 0
        while y <= self._win_h:
            line = self.addLine(QLineF(0, y, self._win_w, y), grid_pen)
            line.setZValue(1)
            self._grid_lines.append(line)
            y += step

        # Centre crosshair
        cx, cy = self._win_w / 2, self._win_h / 2
        cross_pen = QPen(QColor(PALETTE["gold_dim"]), 1, Qt.PenStyle.DashLine)
        h = self.addLine(QLineF(cx - 20, cy, cx + 20, cy), cross_pen)
        v = self.addLine(QLineF(cx, cy - 20, cx, cy + 20), cross_pen)
        h.setZValue(2)
        v.setZValue(2)
        self._center_cross = [h, v]

        # Corner labels
        for text, px, py in (
            ("(0,0)", 4, 4),
            (f"({self._win_w},0)", self._win_w - 70, 4),
            (f"(0,{self._win_h})", 4, self._win_h - 16),
            (f"({self._win_w},{self._win_h})", self._win_w - 90, self._win_h - 16),
        ):
            t = self.addSimpleText(text)
            t.setBrush(QBrush(QColor(PALETTE["text_muted"])))
            font = QFont()
            font.setPointSize(8)
            t.setFont(font)
            t.setPos(px, py)
            t.setZValue(3)
            self._grid_lines.append(t)

    def clear_proxies(self):
        for item in self._proxies.values():
            self.removeItem(item)
        self._proxies.clear()
        self._pos_keys.clear()

    def sync_proxies(self, nodes: list[NodeInstance]):
        """Rebuild or update proxies for the given visual nodes."""
        keep = set()
        for n in nodes:
            keys = _position_keys(n)
            if keys is None:
                continue
            keep.add(n.id)
            self._pos_keys[n.id] = keys
            w, h = _estimate_size(n)
            px, py = _read_pos(n, keys)
            if keys.is_center:
                scene_x = px - w / 2
                scene_y = py - h / 2
            else:
                scene_x, scene_y = px, py

            label = n.label or (registry.get(n.type).label if registry.has(n.type) else n.type)
            # Shorten long labels
            if len(label) > 18:
                label = label[:16] + "…"

            item = self._proxies.get(n.id)
            if item is None:
                item = StageProxyItem(n.id, label, w, h)
                item._on_moved = self._on_proxy_moved
                self.addItem(item)
                self._proxies[n.id] = item
            else:
                item.set_size(w, h)
                item.set_label(label)
                item._on_moved = self._on_proxy_moved

            try:
                item._suppress_move = True
                item.setPos(scene_x, scene_y)
            finally:
                item._suppress_move = False
            # Always re-assert lock/movable so refresh after Live Preview or
            # graph selection cannot leave proxies non-movable.
            item.set_locked(bool(getattr(n, "locked", False)))

        # Remove stale
        for nid in list(self._proxies.keys()):
            if nid not in keep:
                self.removeItem(self._proxies.pop(nid))
                self._pos_keys.pop(nid, None)

    def _on_proxy_moved(self, item: StageProxyItem):
        """Commit proxy position into node.props. Snap is already applied by
        StageProxyItem.itemChange(ItemPositionChange), so do NOT call setPos
        here — that was the source of the 'locked to grid forever' bug."""
        if self._project is None:
            return
        keys = self._pos_keys.get(item.node_id)
        node = self._project.node(item.node_id)
        if keys is None or node is None:
            return
        if getattr(node, "locked", False):
            return

        pos = item.pos()
        r = item.rect()
        if keys.is_center:
            x = pos.x() + r.width() / 2
            y = pos.y() + r.height() / 2
        else:
            x, y = pos.x(), pos.y()

        # Integer pixels (props are int); snap already handled upstream
        _write_pos(node, keys, x, y)
        self.proxy_moved.emit(item.node_id)

    def _on_selection(self):
        selected = [it for it in self.selectedItems() if isinstance(it, StageProxyItem)]
        nid = selected[0].node_id if selected else ""
        self.proxy_selected.emit(nid)

    def select_node(self, node_id: str):
        for nid, item in self._proxies.items():
            item.setSelected(nid == node_id)


class StageView(QGraphicsView):
    """Zoomable / pannable view over the stage scene."""

    def __init__(self, scene: StageScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        # RubberBandDrag lets Qt move ItemIsMovable items on left-drag.
        # Never leave this stuck on ScrollHandDrag — that pan-only mode is
        # what made proxies appear frozen after Live Preview stole focus
        # mid-click (mouseRelease never fired on this view).
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(PALETTE["void"])))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMinimumHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._panning = False
        self._pan_start = QPointF()

    @staticmethod
    def _proxy_under(item: QGraphicsItem | None) -> StageProxyItem | None:
        """Walk parent chain so label children still resolve to the proxy."""
        while item is not None:
            if isinstance(item, StageProxyItem):
                return item
            item = item.parentItem()
        return None

    def ensure_item_drag_mode(self):
        """Force item-drag mode and clear any half-finished pan.

        Safe to call after Live Preview start/stop, dock show, or focus
        return — the Conky preview window often steals focus mid-gesture
        so mouseRelease never resets ScrollHandDrag on this view.
        """
        self._panning = False
        self.unsetCursor()
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def focusInEvent(self, event):
        self.ensure_item_drag_mode()
        super().focusInEvent(event)

    def showEvent(self, event):
        self.ensure_item_drag_mode()
        super().showEvent(event)

    def enterEvent(self, event):
        # Returning the pointer to the stage after the Conky preview window
        # took focus — restore item drag so the next click can move proxies.
        self.ensure_item_drag_mode()
        super().enterEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        # Pan only via middle-click or Alt+left — never put the view into
        # ScrollHandDrag on a plain left click. That mode + focus loss to
        # the Live Preview Conky window left the stage stuck pan-only.
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.AltModifier
        ):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._panning and event.button() in (
            Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton
        ):
            self._panning = False
            self.unsetCursor()
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            event.accept()
            return
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        super().mouseReleaseEvent(event)

    def fit_window(self):
        scene = self.scene()
        if scene is None or not isinstance(scene, StageScene):
            return
        # Fit the window rect with a little padding
        margin = 40
        rect = QRectF(
            -margin, -margin,
            scene._win_w + 2 * margin,
            scene._win_h + 2 * margin,
        )
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class PositionStagePanel(QWidget):
    """
    Dockable Position Stage panel.

    Signals
    -------
    layout_changed
        Emitted after any proxy drag writes new x/y (or cx/cy) values.
        Connect to the same handler as property_panel.changed / graph_changed.
    node_selected(str)
        node_id of the selected proxy, or "" when nothing is selected.
        Useful for syncing the property panel selection.
    """

    layout_changed = pyqtSignal()
    node_selected = pyqtSignal(str)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self._suppress = False
        self._suppress_lock = False
        self._window_id = "primary"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # ---- header row ----
        header = QHBoxLayout()
        title = QLabel("Position Stage")
        title.setProperty("role", "heading")
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        hint = QLabel(
            "Drag visuals on the window plane. Does not replace X/Y spinboxes — "
            "an alternate layout editor. Ctrl+scroll zooms · Alt+drag or middle-click pans."
        )
        hint.setProperty("role", "caption")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ---- controls row ----
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Window"))
        self.window_combo = QComboBox()
        self.window_combo.setMinimumWidth(140)
        self.window_combo.setToolTip(
            "Which window’s resolution the stage represents. "
            "Matches Live Preview / Windows dock."
        )
        self.window_combo.currentIndexChanged.connect(self._on_window_changed)
        ctrl.addWidget(self.window_combo, 1)

        self.snap_chk = QCheckBox("Snap")
        self.snap_chk.setToolTip("Snap dragged positions to a pixel grid")
        self.snap_chk.toggled.connect(self._on_snap_changed)
        ctrl.addWidget(self.snap_chk)

        ctrl.addWidget(QLabel("Step"))
        self.snap_spin = QSpinBox()
        self.snap_spin.setRange(1, 100)
        self.snap_spin.setValue(10)
        self.snap_spin.setSuffix(" px")
        self.snap_spin.setFixedWidth(72)
        self.snap_spin.setToolTip("Grid step in pixels when Snap is on")
        self.snap_spin.valueChanged.connect(self._on_snap_changed)
        ctrl.addWidget(self.snap_spin)

        self.lock_chk = QCheckBox("Lock position")
        self.lock_chk.setToolTip(
            "Freeze the selected visual's stage position. "
            "Same as the lock icon in Layers — uncheck to move again."
        )
        self.lock_chk.setEnabled(False)
        self.lock_chk.toggled.connect(self._on_lock_toggled)
        ctrl.addWidget(self.lock_chk)

        fit_btn = QPushButton("Fit")
        fit_btn.setToolTip("Zoom to fit the window rectangle")
        fit_btn.clicked.connect(self._fit)
        ctrl.addWidget(fit_btn)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(32)
        refresh_btn.setToolTip("Reload proxies from the current project")
        refresh_btn.clicked.connect(self.refresh)
        ctrl.addWidget(refresh_btn)

        layout.addLayout(ctrl)

        # ---- stage view ----
        self.scene = StageScene(self)
        self.scene.set_project(project)
        self.scene.proxy_moved.connect(self._on_proxy_moved)
        self.scene.proxy_selected.connect(self.node_selected.emit)
        self.scene.proxy_selected.connect(self._on_proxy_selected_for_lock)

        self.view = StageView(self.scene)
        layout.addWidget(self.view, 1)

        # Status line
        self.status = QLabel("")
        self.status.setProperty("role", "caption")
        layout.addWidget(self.status)

        self._rebuild_window_combo()
        self.refresh()

    # ------------------------------------------------------------------ public API
    def set_project(self, project: Project):
        self.project = project
        self.scene.set_project(project)
        self._rebuild_window_combo()
        self.refresh()

    def set_window(self, window_id: str):
        """Select a window programmatically (e.g. from Windows panel)."""
        wid = window_id or "primary"
        self._suppress = True
        idx = self.window_combo.findData(wid)
        if idx < 0:
            idx = 0
        self.window_combo.setCurrentIndex(idx)
        self._suppress = False
        self._window_id = str(self.window_combo.currentData() or "primary")
        self.refresh()

    def select_node(self, node_id: str):
        """Highlight a proxy to match canvas / property-panel selection.

        Selection alone must never disable dragging.
        """
        self.scene.select_node(node_id)
        for nid, item in list(self.scene._proxies.items()):
            node = self.project.node(nid) if self.project is not None else None
            locked = bool(getattr(node, "locked", False)) if node is not None else False
            item.set_locked(locked)
        self._on_proxy_selected_for_lock(node_id)
        self.view.ensure_item_drag_mode()

    def reset_interaction(self):
        """Re-enable proxy dragging after Live Preview or focus changes.

        Call from studio_tab when Live Preview starts or stops, e.g.::

            self.preview_controller.started.connect(self.position_stage.reset_interaction)
            self.preview_controller.stopped.connect(self.position_stage.reset_interaction)
        """
        self.view.ensure_item_drag_mode()
        for nid, item in list(self.scene._proxies.items()):
            node = self.project.node(nid) if self.project is not None else None
            locked = bool(getattr(node, "locked", False)) if node is not None else False
            item.set_locked(locked)

    def refresh(self):
        """Full rebuild of frame size + proxies from the current project."""
        if self.project is None:
            return
        w, h = self._current_window_size()
        self.scene.set_window_size(w, h)
        self.scene.set_snap(self.snap_chk.isChecked(), self.snap_spin.value())

        visuals = self._visuals_for_window()
        self.scene.sync_proxies(visuals)
        self.view.ensure_item_drag_mode()
        self.status.setText(
            f"{w}×{h} px  ·  {len(visuals)} visual(s)"
            + ("  ·  snap " + str(self.snap_spin.value()) + "px" if self.snap_chk.isChecked() else "")
        )

    def notify_graph_changed(self):
        """Called from studio_tab when the graph changes elsewhere (prop panel, etc.)."""
        # Avoid feedback loops during our own drag writes
        if self._suppress:
            return
        self.refresh()

    # ------------------------------------------------------------------ internals
    def _rebuild_window_combo(self):
        self._suppress = True
        self.window_combo.clear()
        if self.project is None:
            self.window_combo.addItem("Main (primary)", "primary")
            self._suppress = False
            return

        wins = []
        if hasattr(self.project, "ensure_windows"):
            try:
                self.project.ensure_windows()
            except Exception:
                pass
        if hasattr(self.project, "enabled_windows"):
            try:
                wins = list(self.project.enabled_windows())
            except Exception:
                wins = []
        if not wins and hasattr(self.project, "windows"):
            wins = list(getattr(self.project, "windows", []) or [])

        if not wins:
            self.window_combo.addItem("Main (primary)", "primary")
        else:
            primary = None
            if hasattr(self.project, "primary_window"):
                try:
                    primary = self.project.primary_window()
                except Exception:
                    primary = wins[0] if wins else None
            for w in sorted(wins, key=lambda x: (getattr(x, "z", 0), getattr(x, "id", ""))):
                label = getattr(w, "name", None) or getattr(w, "id", "window")
                mon = getattr(w, "monitor", "auto") or "auto"
                if mon not in ("auto", "primary"):
                    label = f"{label} @ {mon}"
                if primary is not None and getattr(w, "id", None) == getattr(primary, "id", None):
                    label = f"{label} (primary)"
                self.window_combo.addItem(label, getattr(w, "id", "primary"))

        # Restore selection
        idx = self.window_combo.findData(self._window_id)
        self.window_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._window_id = str(self.window_combo.currentData() or "primary")
        self._suppress = False

    def _current_window_size(self) -> tuple[int, int]:
        if self.project is None:
            return 460, 640
        wid = self._window_id
        if hasattr(self.project, "window") and wid not in ("", "primary"):
            try:
                w = self.project.window(wid)
                if w is not None:
                    return int(w.width), int(w.height)
            except Exception:
                pass
        if hasattr(self.project, "primary_window"):
            try:
                pw = self.project.primary_window()
                if pw is not None:
                    return int(pw.width), int(pw.height)
            except Exception:
                pass
        # Legacy canvas path
        c = getattr(self.project, "canvas", None)
        if c is not None:
            return int(getattr(c, "width", 460)), int(getattr(c, "height", 640))
        return 460, 640

    def _visuals_for_window(self) -> list[NodeInstance]:
        """Visual nodes to show on the stage for the selected window.

        Prefer WindowSettings.visible_node_ids when present and non-empty;
        otherwise all visible visual nodes (single shared graph).
        """
        if self.project is None:
            return []

        filter_ids: set[str] | None = None
        wid = self._window_id
        if hasattr(self.project, "window") and wid not in ("", "primary"):
            try:
                w = self.project.window(wid)
                vids = getattr(w, "visible_node_ids", None) if w else None
                if vids:
                    filter_ids = set(vids)
            except Exception:
                pass
        if filter_ids is None and hasattr(self.project, "primary_window"):
            try:
                pw = self.project.primary_window()
                vids = getattr(pw, "visible_node_ids", None) if pw else None
                if vids:
                    filter_ids = set(vids)
            except Exception:
                pass

        out = []
        for n in self.project.nodes:
            if n.id == CANVAS_NODE_ID:
                continue
            if not getattr(n, "visible", True):
                continue
            if not registry.has(n.type):
                continue
            if registry.get(n.type).category != "visual":
                continue
            if filter_ids is not None and n.id not in filter_ids:
                continue
            if _position_keys(n) is None:
                continue
            out.append(n)
        return out

    def _on_window_changed(self, *_args):
        if self._suppress:
            return
        self._window_id = str(self.window_combo.currentData() or "primary")
        self.refresh()

    def _on_snap_changed(self, *_args):
        self.scene.set_snap(self.snap_chk.isChecked(), self.snap_spin.value())
        self.status.setText(
            self.status.text().split("  ·  snap")[0]
            + ("  ·  snap " + str(self.snap_spin.value()) + "px" if self.snap_chk.isChecked() else "")
        )

    def _on_proxy_moved(self, node_id: str):
        self._suppress = True
        try:
            self.layout_changed.emit()
        finally:
            self._suppress = False

    def _on_proxy_selected_for_lock(self, node_id: str):
        """Keep Lock checkbox in sync with the selected proxy."""
        self._suppress_lock = True
        try:
            if not node_id or self.project is None:
                self.lock_chk.setEnabled(False)
                self.lock_chk.setChecked(False)
                return
            node = self.project.node(node_id)
            if node is None:
                self.lock_chk.setEnabled(False)
                self.lock_chk.setChecked(False)
                return
            self.lock_chk.setEnabled(True)
            self.lock_chk.setChecked(bool(getattr(node, "locked", False)))
        finally:
            self._suppress_lock = False

    def _on_lock_toggled(self, checked: bool):
        if getattr(self, "_suppress_lock", False) or self.project is None:
            return
        # Selected proxy on the stage
        selected = [
            it for it in self.scene.selectedItems()
            if isinstance(it, StageProxyItem)
        ]
        if not selected:
            return
        node_id = selected[0].node_id
        node = self.project.node(node_id)
        if node is None:
            return
        # Prefer Project.set_locked if available (emits the same path Layers uses)
        if hasattr(self.project, "set_locked"):
            self.project.set_locked(node_id, checked)
        else:
            node.locked = checked
        item = self.scene._proxies.get(node_id)
        if item is not None:
            item.set_locked(checked)
        # Notify studio so Layers dock + canvas update
        self.layout_changed.emit()

    def _fit(self):
        self.view.fit_window()


