"""
The Layers dock: a parallel, more ergonomic view of the same node graph,
focused purely on stacking and visibility -- exactly the "easier than
manually editing z values" pitch. Top of the list = highest z = drawn
last = visually on top, matching the Photoshop/GIMP convention.

Deliberately reuses Project.reorder_nodes/set_visible/set_locked (added
alongside this) rather than poking at node.z directly, so the Studio's
one graph_changed -> debounced-preview-rebuild pipeline picks up Layers
dock edits automatically, the same as any canvas edit.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QToolButton, QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from conkystudio.theme import PALETTE
from conkystudio.model.project import Project
from conkystudio.nodes import registry
from conkystudio.nodes.canvas import CANVAS_NODE_ID

_NODE_ID_ROLE = Qt.ItemDataRole.UserRole


class _LayerRow(QWidget):
    visibility_toggled = pyqtSignal(str, bool)
    lock_toggled = pyqtSignal(str, bool)

    def __init__(self, node_id: str, label: str, color: str, visible: bool, locked: bool, parent=None):
        super().__init__(parent)
        self.node_id = node_id
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        swatch = QLabel()
        swatch.setFixedSize(10, 10)
        swatch.setStyleSheet(f"background:{color}; border-radius: 5px;")
        layout.addWidget(swatch)

        self.name_label = QLabel(label)
        layout.addWidget(self.name_label, 1)

        self.eye_btn = QToolButton()
        self.eye_btn.setCheckable(True)
        self.eye_btn.setChecked(not visible)  # checked == hidden, for a consistent "toggled on = off" affordance
        self._apply_eye_text()
        self.eye_btn.toggled.connect(self._on_eye)
        layout.addWidget(self.eye_btn)

        self.lock_btn = QToolButton()
        self.lock_btn.setCheckable(True)
        self.lock_btn.setChecked(locked)
        self._apply_lock_text()
        self.lock_btn.toggled.connect(self._on_lock)
        layout.addWidget(self.lock_btn)

    def _apply_eye_text(self):
        self.eye_btn.setText("\U0001F441" if not self.eye_btn.isChecked() else "\u2014")
        self.eye_btn.setToolTip("Hide" if not self.eye_btn.isChecked() else "Show")

    def _apply_lock_text(self):
        self.lock_btn.setText("\U0001F512" if self.lock_btn.isChecked() else "\U0001F513")
        self.lock_btn.setToolTip("Unlock" if self.lock_btn.isChecked() else "Lock")

    def _on_eye(self, checked: bool):
        self._apply_eye_text()
        self.visibility_toggled.emit(self.node_id, not checked)

    def _on_lock(self, checked: bool):
        self._apply_lock_text()
        self.lock_toggled.emit(self.node_id, checked)


class _LayerList(QListWidget):
    """Overridden only so a completed internal drag reorder is reported as
    one clean 'here is the new full order' signal instead of the caller
    having to reconstruct it from Qt's move events."""
    order_changed = pyqtSignal(list)

    def dropEvent(self, event):
        super().dropEvent(event)
        ids = [self.item(i).data(_NODE_ID_ROLE) for i in range(self.count())]
        self.order_changed.emit(ids)


class LayersDock(QWidget):
    layers_changed = pyqtSignal()

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self._on_selection_request = None   # set by studio_tab to select-on-canvas
        self._suppress = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        heading = QLabel("Layers")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        hint = QLabel("Drag to reorder \u2014 top draws last (on top).")
        hint.setProperty("role", "caption")
        layout.addWidget(hint)

        self.list_widget = _LayerList()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.order_changed.connect(self._on_order_changed)
        self.list_widget.itemSelectionChanged.connect(self._on_list_selection_changed)
        layout.addWidget(self.list_widget, 1)

        self.refresh()

    def set_selection_callback(self, fn):
        """fn(node_id) -- called when a Layers row is clicked, so the
        canvas can select the matching node too."""
        self._on_selection_request = fn

    # ------------------------------------------------------------------
    def refresh(self):
        self._suppress = True
        self.list_widget.clear()

        def _is_visual(n):
            if not registry.has(n.type):
                # Missing plugin nodes stay in the stack as red placeholders.
                return True
            return registry.get(n.type).category == "visual"

        visual_nodes = sorted(
            (n for n in self.project.nodes if _is_visual(n)),
            key=lambda n: -n.z,   # highest z (top of visual stack) first, matching the dock's top-to-bottom convention
        )
        for n in visual_nodes:
            if registry.has(n.type):
                spec = registry.get(n.type)
                color, label = spec.color, (n.label or spec.label)
            else:
                color, label = "#c44", (n.label or f"Missing: {n.type}")
            item = QListWidgetItem()
            item.setData(_NODE_ID_ROLE, n.id)
            item.setSizeHint(_LayerRow(n.id, "", color, True, False).sizeHint())
            self.list_widget.addItem(item)
            row = _LayerRow(n.id, label, color, n.visible, n.locked)
            row.visibility_toggled.connect(self._on_visibility_toggled)
            row.lock_toggled.connect(self._on_lock_toggled)
            self.list_widget.setItemWidget(item, row)
        self._suppress = False

    def select_node(self, node_id: str):
        self._suppress = True
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setSelected(item.data(_NODE_ID_ROLE) == node_id)
        self._suppress = False

    # ------------------------------------------------------------------
    def _on_order_changed(self, ordered_ids: list):
        self.project.reorder_nodes(ordered_ids)
        self.refresh()   # re-derive row widgets in the new z order rather than trust Qt's own reshuffle
        self.layers_changed.emit()

    def _on_visibility_toggled(self, node_id: str, visible: bool):
        self.project.set_visible(node_id, visible)
        self.layers_changed.emit()

    def _on_lock_toggled(self, node_id: str, locked: bool):
        self.project.set_locked(node_id, locked)
        self.layers_changed.emit()

    def _on_list_selection_changed(self):
        if self._suppress or self._on_selection_request is None:
            return
        items = self.list_widget.selectedItems()
        if items:
            self._on_selection_request(items[0].data(_NODE_ID_ROLE))

