"""
Right-hand dock: the inspector. Rebuilds its form from scratch every time
the canvas selection changes, grouped into QGroupBoxes by PropertySpec.group
(matching the "Text / Font / Colour / Data Source / Refresh" style
grouping sketched in the original brief). A bindable property that
currently has an incoming wire shows a small "bound to <node>" chip with
an Unbind button instead of its constant editor -- the wire IS the value,
editing a greyed-out constant underneath it would be misleading.

Every QFormLayout here uses WrapLongRows: when a field is too wide for
the panel, Qt drops it onto its own line under the label instead of
forcing the whole row (and the whole dock) wider. Combined with the
scroll area's horizontal scrollbar being permanently off, this is what
keeps the panel from ever requiring a sideways scroll to see a cut-off
field -- narrow it however far and fields stack instead of clipping.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox, QLabel, QLineEdit, QCheckBox,
    QComboBox, QPushButton, QHBoxLayout, QGridLayout, QFileDialog, QScrollArea,
    QSizePolicy, QDoubleSpinBox, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal

from conkystudio.model.project import Project
from conkystudio.nodes import registry
from conkystudio.nodes.canvas import CANVAS_NODE_ID
from conkystudio.ui.widgets import ColorSwatchButton, SliderSpin
from conkystudio.fonts import manager as font_manager


def _wrapping_form() -> QFormLayout:
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
    # A field that doesn't fit drops to its own line under the label
    # instead of forcing the row (and the dock) wider than it should be.
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form


class PropertyPanel(QWidget):
    changed = pyqtSignal()             # a property value changed
    unbind_requested = pyqtSignal(str, str)   # node_id, prop_key
    label_changed = pyqtSignal(str, str)       # node_id, new_label

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self.node_id: str = ""
        self._font_families_cache: list[str] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        # Never invite a sideways scroll -- if content doesn't fit, the
        # forms above wrap their fields instead of spilling out the side.
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        self._build_empty_state()

    def _build_empty_state(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(14, 14, 14, 14)
        heading = QLabel("Nothing selected")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        cap = QLabel("Click a node on the canvas to edit its properties.")
        cap.setProperty("role", "caption")
        cap.setWordWrap(True)
        layout.addWidget(cap)
        layout.addStretch(1)
        self.scroll.setWidget(w)

    def _build_missing_plugin_state(self, node):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(14, 14, 14, 14)
        heading = QLabel("Missing plugin")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        cap = QLabel(
            f"Node type <b>{node.type}</b> is not installed.\n\n"
            "This project still opens so you can edit other nodes. "
            "Install the plugin via Tools → Plugins, or re-open the project "
            "and use the missing-plugin prompt if a source URL was saved with it."
        )
        cap.setWordWrap(True)
        layout.addWidget(cap)
        layout.addStretch(1)
        self.scroll.setWidget(w)

    # ------------------------------------------------------------------
    def show_node(self, node_id: str):
        self.node_id = node_id
        if not node_id:
            self._build_empty_state()
            return
        node = self.project.node(node_id)
        if node is None:
            self._build_empty_state()
            return
        if not registry.has(node.type):
            self._build_missing_plugin_state(node)
            return
        spec = registry.get(node.type)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QLabel(spec.label)
        header.setProperty("role", "heading")
        header.setWordWrap(True)
        layout.addWidget(header)

        if node_id != CANVAS_NODE_ID:
            name_row = QHBoxLayout()
            name_row.addWidget(QLabel("Name"))
            name_edit = QLineEdit(node.label)
            name_edit.setPlaceholderText(spec.label)
            name_edit.editingFinished.connect(lambda: self.label_changed.emit(node_id, name_edit.text()))
            name_row.addWidget(name_edit, 1)
            layout.addLayout(name_row)

        if spec.description:
            desc = QLabel(spec.description)
            desc.setProperty("role", "caption")
            desc.setWordWrap(True)
            layout.addWidget(desc)

        groups: dict[str, QFormLayout] = {}
        boxes: dict[str, QGroupBox] = {}
        group_order: list[str] = []
        for pspec in spec.properties:
            if pspec.group not in groups:
                box = QGroupBox(pspec.group)
                form = _wrapping_form()
                box.setLayout(form)
                groups[pspec.group] = form
                boxes[pspec.group] = box
                group_order.append(pspec.group)
            form = groups[pspec.group]

            edge = self.project.edge_for_prop(node_id, pspec.key)
            if pspec.bindable and edge is not None:
                form.addRow(pspec.label, self._bound_chip(edge.src_node, node_id, pspec.key))
            else:
                editor = self._make_editor(node, pspec)
                if pspec.help:
                    editor.setToolTip(pspec.help)
                form.addRow(pspec.label, editor)

        for gname in group_order:
            layout.addWidget(boxes[gname])

        if node_id != CANVAS_NODE_ID and spec.category == "visual":
            layout.addWidget(self._interaction_box(node))

        layout.addStretch(1)
        self.scroll.setWidget(root)

    def _interaction_box(self, node) -> QGroupBox:
        box = QGroupBox("Interaction")
        form = _wrapping_form()
        box.setLayout(form)

        cmd_edit = QLineEdit(node.on_click_command)
        cmd_edit.setPlaceholderText("Shell command to run on click, e.g. playerctl play-pause")
        cmd_edit.editingFinished.connect(lambda: self._set_click_field(node.id, "on_click_command", cmd_edit.text()))
        form.addRow("On click", cmd_edit)

        # A 2x2 grid (X/Y on one row, W/H on the next) rather than one
        # long X-Y-W-H row -- four label+spinbox pairs side by side was
        # exactly what forced this panel wider than the dock could give
        # it, with the last field or two clipped off past the edge.
        region_row = QWidget()
        region_grid = QGridLayout(region_row)
        region_grid.setContentsMargins(0, 0, 0, 0)
        region_grid.setHorizontalSpacing(6)
        region_grid.setVerticalSpacing(4)
        specs = [("click_x", "X"), ("click_y", "Y"), ("click_w", "W"), ("click_h", "H")]
        for i, (key, label) in enumerate(specs):
            row, col = divmod(i, 2)
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(4)
            cell_layout.addWidget(QLabel(label))
            spin = QDoubleSpinBox()
            spin.setRange(-4000, 4000)
            spin.setDecimals(0)
            spin.setValue(getattr(node, key))
            spin.setFixedWidth(56)
            spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            spin.valueChanged.connect(lambda v, k=key: self._set_click_field(node.id, k, v))
            cell_layout.addWidget(spin)
            cell_layout.addStretch(1)
            region_grid.addWidget(cell, row, col)
        form.addRow("Click region", region_row)

        hint = QLabel("Region is in canvas pixels, independent of this node's own drawing position -- "
                       "set it to wherever you actually want the clickable hotspot.")
        hint.setProperty("role", "caption")
        hint.setWordWrap(True)
        form.addRow(hint)
        return box

    def _set_click_field(self, node_id: str, key: str, value):
        node = self.project.node(node_id)
        if node is None:
            return
        setattr(node, key, value)
        self.changed.emit()

    def _bound_chip(self, src_node_id: str, dst_node_id: str, prop_key: str) -> QWidget:
        src = self.project.node(src_node_id)
        src_label = (src.label or registry.get(src.type).label) if src else "?"
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        chip = QLabel(f"\u25cf bound to {src_label}")
        chip.setStyleSheet("color: #4fd1c5; font-weight: 600;")
        chip.setWordWrap(True)
        row.addWidget(chip, 1)
        btn = QPushButton("Unbind")
        btn.setFixedWidth(70)
        btn.clicked.connect(lambda: self.unbind_requested.emit(dst_node_id, prop_key))
        row.addWidget(btn)
        return w

    # ------------------------------------------------------------------
    def _make_editor(self, node, pspec) -> QWidget:
        value = node.props.get(pspec.key, pspec.default)
        kind = pspec.kind

        if kind in (registry.FLOAT, registry.INT):
            step = pspec.step if kind == registry.FLOAT else max(1, int(pspec.step))
            decimals = 2 if kind == registry.FLOAT and step < 1 else (1 if kind == registry.FLOAT else 0)
            w = SliderSpin(pspec.minimum, pspec.maximum, step, float(value), decimals=decimals)
            w.valueChanged.connect(lambda v, k=pspec.key: self._set_prop(k, v if kind == registry.FLOAT else int(v)))
            return w

        if kind == registry.COLOR:
            w = ColorSwatchButton(str(value))
            w.colorChanged.connect(lambda hexstr, k=pspec.key: self._set_prop(k, hexstr))
            return w

        if kind == registry.BOOL:
            w = QCheckBox()
            w.setChecked(bool(value))
            w.toggled.connect(lambda checked, k=pspec.key: self._set_prop(k, checked))
            return w

        if kind == registry.ENUM:
            w = QComboBox()
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            choices = pspec.choices or []
            labels = pspec.choice_labels or choices
            for c, l in zip(choices, labels):
                w.addItem(l, c)
            idx = choices.index(value) if value in choices else 0
            w.setCurrentIndex(idx)
            w.currentIndexChanged.connect(lambda i, k=pspec.key, cc=choices: self._set_prop(k, cc[i]) if 0 <= i < len(cc) else None)
            return w

        if kind == registry.FONT:
            w = QComboBox()
            w.setEditable(True)
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            families = self._font_families()
            w.addItems(families)
            if value and value not in families:
                w.addItem(value)
            w.setCurrentText(str(value))
            w.currentTextChanged.connect(lambda t, k=pspec.key: self._set_prop(k, t))
            return w

        if kind == registry.PATH:
            # Hardened PATH editor: node_id is snapshotted at build time so a
            # selection change mid-edit can't misattribute the write, and a
            # blank commit from a plain focus-out won't wipe a stored path.
            container = QWidget()
            row = QHBoxLayout(container)
            row.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(str(value))
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

            node_id_snap = self.node_id
            prop_key = pspec.key
            browse = QPushButton("\u2026")
            browse.setFixedWidth(28)

            def _write_path(path_str: str, nid=node_id_snap, key=prop_key):
                n = self.project.node(nid)
                if n is None:
                    return
                n.props[key] = path_str
                if not self.node_id:
                    self.node_id = nid
                if nid == CANVAS_NODE_ID:
                    self.project.sync_canvas_from_node()
                self.changed.emit()

            def commit_path():
                text = edit.text().strip()
                n = self.project.node(node_id_snap)
                if n is None:
                    return
                # Focus went to Browse: empty editingFinished is noise.
                if not text and QApplication.focusWidget() is browse:
                    return
                existing = (n.props.get(prop_key) or "").strip()
                # Don't wipe a stored path with "" from a generic focus-out.
                if not text and existing:
                    return
                if text != existing:
                    _write_path(text)

            def do_browse():
                parent = self.window() if self.window() is not None else self
                path, _ = QFileDialog.getOpenFileName(
                    parent,
                    "Choose image file",
                    edit.text() or "",
                    "Images (*.png *.svg *.jpg *.jpeg *.webp);;All files (*)",
                )
                if not path:
                    return
                edit.blockSignals(True)
                edit.setText(path)
                edit.blockSignals(False)
                _write_path(path)

            edit.editingFinished.connect(commit_path)
            browse.clicked.connect(do_browse)
            row.addWidget(edit, 1)
            row.addWidget(browse)
            return container

        if kind == registry.CODE:
            from PyQt6.QtWidgets import QPlainTextEdit
            from PyQt6.QtGui import QFont as _QFont
            w = QPlainTextEdit(str(value))
            mono = _QFont("Monospace")
            mono.setStyleHint(_QFont.StyleHint.Monospace)
            w.setFont(mono)
            w.setTabChangesFocus(False)
            w.setMinimumHeight(140)
            w.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            w.textChanged.connect(lambda k=pspec.key, e=w: self._set_prop(k, e.toPlainText()))
            return w

        # STRING and anything unrecognised
        w = QLineEdit(str(value))
        w.editingFinished.connect(lambda k=pspec.key, e=w: self._set_prop(k, e.text()))
        return w

    def _font_families(self) -> list[str]:
        if self._font_families_cache is None:
            self._font_families_cache = font_manager.list_families()
        return self._font_families_cache

    def _set_prop(self, key: str, value):
        node = self.project.node(self.node_id)
        if node is None:
            return
        node.props[key] = value
        if self.node_id == CANVAS_NODE_ID:
            self.project.sync_canvas_from_node()
        self.changed.emit()

    def invalidate_font_cache(self):
        self._font_families_cache = None
