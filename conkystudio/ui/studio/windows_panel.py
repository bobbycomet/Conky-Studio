"""
Studio dock: manage multi-monitor windows for the current project.

Wire from studio_tab similar to LayersDock:
    self.windows_panel = WindowsPanel(self.project)
    self.windows_panel.windows_changed.connect(self._on_graph_changed)
    self.windows_panel.preview_window_selected.connect(
        self.preview_controller.set_preview_window)
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox, QCheckBox,
    QFormLayout, QGroupBox, QMessageBox, QSizePolicy, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal

from conkystudio.model.project import Project, WindowSettings
from conkystudio.hardware import discovery

_WINDOW_ID_ROLE = Qt.ItemDataRole.UserRole


def _wrapping_form() -> QFormLayout:
    form = QFormLayout()
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form


class WindowsPanel(QWidget):
    windows_changed = pyqtSignal()
    preview_window_selected = pyqtSignal(str)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.project = project
        self._suppress = False
        self._monitor_choices = discovery.monitor_choices_for_ui()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Single scroll area for the whole panel — same pattern as PropertyPanel.
        # Narrow the dock and fields wrap; short the dock and the whole page scrolls.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        heading = QLabel("Windows / Monitors")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        hint = QLabel(
            "Each window is a separate Conky process. Single-monitor themes "
            "keep one entry (auto). Add more to pin HUDs to specific outputs."
        )
        hint.setProperty("role", "caption")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list_widget = QListWidget()
        self.list_widget.setMinimumHeight(80)
        self.list_widget.setMaximumHeight(160)
        self.list_widget.currentItemChanged.connect(self._on_select)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        add_btn = QPushButton("Add")
        add_btn.setToolTip("Add window")
        add_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        add_btn.clicked.connect(self._add)
        btn_row.addWidget(add_btn)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setToolTip("Remove selected window")
        self.remove_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.remove_btn.clicked.connect(self._remove)
        btn_row.addWidget(self.remove_btn)
        refresh_btn = QPushButton("Rescan")
        refresh_btn.setToolTip("Rescan monitors")
        refresh_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        refresh_btn.clicked.connect(self._rescan_monitors)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        box = QGroupBox("Selected window")
        form = _wrapping_form()
        box.setLayout(form)

        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._apply_editor)
        form.addRow("Name", self.name_edit)

        self.monitor_combo = QComboBox()
        self.monitor_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._fill_monitors()
        self.monitor_combo.currentIndexChanged.connect(self._apply_editor)
        form.addRow("Monitor", self.monitor_combo)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(64, 7680)
        self.width_spin.valueChanged.connect(self._apply_editor)
        form.addRow("Width", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(64, 4320)
        self.height_spin.valueChanged.connect(self._apply_editor)
        form.addRow("Height", self.height_spin)

        self.align_combo = QComboBox()
        self.align_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for a in (
            "top_left", "top_right", "top_middle",
            "bottom_left", "bottom_right", "bottom_middle",
            "middle_left", "middle_right", "middle_middle",
        ):
            self.align_combo.addItem(a, a)
        self.align_combo.currentIndexChanged.connect(self._apply_editor)
        form.addRow("Alignment", self.align_combo)

        self.window_type_combo = QComboBox()
        self.window_type_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for value, label in (
            ("auto", "Auto-detect (recommended)"),
            ("normal", "Normal (undecorated, always-below)"),
            ("desktop", "Desktop"),
            ("dock", "Dock"),
        ):
            self.window_type_combo.addItem(label, value)
        self.window_type_combo.setToolTip(
            "Per-window layering, same choices as the Canvas node's Window layering "
            "field. Desktop/Dock are the common cause of an X BadWindow error on this "
            "window specifically -- if this window misbehaves or won't stay anchored, "
            "try Normal here, independent of what the primary window/Canvas uses."
        )
        self.window_type_combo.currentIndexChanged.connect(self._apply_editor)
        form.addRow("Window type", self.window_type_combo)

        self.gap_x_spin = QSpinBox()
        self.gap_x_spin.setRange(0, 4000)
        self.gap_x_spin.valueChanged.connect(self._apply_editor)
        form.addRow("Gap X", self.gap_x_spin)

        self.gap_y_spin = QSpinBox()
        self.gap_y_spin.setRange(0, 4000)
        self.gap_y_spin.valueChanged.connect(self._apply_editor)
        form.addRow("Gap Y", self.gap_y_spin)

        self.enabled_chk = QCheckBox("Enabled")
        self.enabled_chk.toggled.connect(self._apply_editor)
        form.addRow(self.enabled_chk)

        preview_btn = QPushButton("Preview this window")
        preview_btn.setToolTip("Live Preview shows only the selected window conf")
        preview_btn.clicked.connect(self._preview_selected)
        form.addRow(preview_btn)

        scene_btn = QPushButton("Use visible layers as scene")
        scene_btn.setToolTip(
            "Store the currently visible (eye-open) visual nodes as this window's "
            "scene filter. Other windows can keep the full graph or their own subset. "
            "Clear scene filter restores the full shared graph for this window."
        )
        scene_btn.clicked.connect(self._capture_visible_scene)
        form.addRow(scene_btn)

        clear_scene_btn = QPushButton("Clear scene filter")
        clear_scene_btn.setToolTip("This window draws the full shared graph again")
        clear_scene_btn.clicked.connect(self._clear_scene_filter)
        form.addRow(clear_scene_btn)

        self.scene_label = QLabel("")
        self.scene_label.setProperty("role", "caption")
        self.scene_label.setWordWrap(True)
        form.addRow(self.scene_label)

        layout.addWidget(box)
        layout.addStretch(1)
        self.scroll.setWidget(root)

        self.refresh()

    def set_project(self, project: Project):
        self.project = project
        self.refresh()

    def _fill_monitors(self):
        self.monitor_combo.blockSignals(True)
        self.monitor_combo.clear()
        for value, label in self._monitor_choices:
            self.monitor_combo.addItem(label, value)
        self.monitor_combo.blockSignals(False)

    def _rescan_monitors(self):
        self._monitor_choices = discovery.monitor_choices_for_ui()
        self._fill_monitors()
        self.refresh()

    def refresh(self):
        self._suppress = True
        self.project.ensure_windows()
        self.list_widget.clear()
        primary = self.project.primary_window()
        for w in sorted(self.project.windows, key=lambda x: (x.z, x.id)):
            mon = w.monitor or "auto"
            mark = " *" if w.id == primary.id else ""
            disabled = "" if w.enabled else " (off)"
            item = QListWidgetItem(f"{w.name or w.id} @ {mon}{mark}{disabled}")
            item.setData(_WINDOW_ID_ROLE, w.id)
            self.list_widget.addItem(item)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        self._suppress = False
        self._load_editor()

    def _current_window(self):
        item = self.list_widget.currentItem()
        if not item:
            return None
        return self.project.window(item.data(_WINDOW_ID_ROLE))

    def _on_select(self, *_args):
        if not self._suppress:
            self._load_editor()

    def _load_editor(self):
        w = self._current_window()
        self._suppress = True
        if w is None:
            self.name_edit.clear()
            self._suppress = False
            return
        self.name_edit.setText(w.name)
        idx = self.monitor_combo.findData(w.monitor)
        self.monitor_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.width_spin.setValue(w.width)
        self.height_spin.setValue(w.height)
        aidx = self.align_combo.findData(w.alignment)
        self.align_combo.setCurrentIndex(aidx if aidx >= 0 else 0)
        wtidx = self.window_type_combo.findData(getattr(w, "window_type", "auto") or "auto")
        self.window_type_combo.setCurrentIndex(wtidx if wtidx >= 0 else 0)
        self.gap_x_spin.setValue(w.gap_x)
        self.gap_y_spin.setValue(w.gap_y)
        self.enabled_chk.setChecked(w.enabled)
        vids = getattr(w, "visible_node_ids", None) or []
        if vids:
            self.scene_label.setText(f"Scene filter: {len(vids)} node(s)")
        else:
            self.scene_label.setText("Scene filter: full shared graph")
        self._suppress = False

    def _capture_visible_scene(self):
        w = self._current_window()
        if w is None:
            return
        # Visual nodes that are currently eye-open in the Layers dock
        ids = [
            n.id for n in self.project.nodes
            if str(getattr(n, "type", "")).startswith("visual.")
            and getattr(n, "visible", True)
        ]
        w.visible_node_ids = list(ids)
        self.scene_label.setText(f"Scene filter: {len(ids)} node(s)")
        self.windows_changed.emit()

    def _clear_scene_filter(self):
        w = self._current_window()
        if w is None:
            return
        w.visible_node_ids = []
        self.scene_label.setText("Scene filter: full shared graph")
        self.windows_changed.emit()

    def _apply_editor(self, *_args):
        if self._suppress:
            return
        w = self._current_window()
        if w is None:
            return
        w.name = self.name_edit.text().strip() or w.name
        mon = self.monitor_combo.currentData()
        if mon:
            w.monitor = str(mon)
        w.width = self.width_spin.value()
        w.height = self.height_spin.value()
        al = self.align_combo.currentData()
        if al:
            w.alignment = str(al)
        wt = self.window_type_combo.currentData()
        if wt:
            w.window_type = str(wt)
        w.gap_x = self.gap_x_spin.value()
        w.gap_y = self.gap_y_spin.value()
        w.enabled = self.enabled_chk.isChecked()
        if w.id == self.project.primary_window().id:
            self.project.sync_canvas_from_primary()
        self.refresh()
        self.windows_changed.emit()

    def _add(self):
        w = self.project.add_window(copy_from_primary=True)
        self.refresh()
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(_WINDOW_ID_ROLE) == w.id:
                self.list_widget.setCurrentRow(i)
                break
        self.windows_changed.emit()

    def _remove(self):
        w = self._current_window()
        if w is None:
            return
        if len(self.project.ensure_windows()) <= 1:
            QMessageBox.information(self, "Windows", "A project always needs at least one window.")
            return
        self.project.remove_window(w.id)
        self.refresh()
        self.windows_changed.emit()

    def _preview_selected(self):
        w = self._current_window()
        if w:
            self.preview_window_selected.emit(w.id)

