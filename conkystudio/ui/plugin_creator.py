"""
Plugin Creation — formalize a custom node into a distributable plugin.

Architecture fit
----------------
Custom Lua / Custom Script / ad-hoc logic already act as escape hatches
inside Studio. This dialog does not reinvent the node model; it takes the
same shape (id, properties, Lua/script body, category) and emits a
PluginNode that passes plugins/schema.py + loader validation, ready for:

  ~/.config/conky-studio/plugins/          (local pack)
  or a community-store plugins.json entry

Flow
----
  1. Choose category (logic | visual | source | canvas_ext)
  2. Identity + metadata
  3. Properties (same kinds the property panel already edits)
  4. Body (lua_expr / lua_draw_body / script_body / conf directives)
  5. Validate against schema
  6. Export single-plugin JSON and/or install into local plugins dir

Wire from MainWindow Tools menu:

    from conkystudio.ui.plugin_creator import PluginCreatorDialog

    action = QAction("Plugin Creation…", self)
    action.triggered.connect(self._open_plugin_creator)
    tools_menu.addAction(action)

    def _open_plugin_creator(self):
        dialog = PluginCreatorDialog(self)
        if dialog.exec() and dialog.exported_path:
            self.statusBar().showMessage(f"Plugin exported: {dialog.exported_path}")
            try:
                self.studio_tab.palette._refresh()
            except Exception:
                pass
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QComboBox, QCheckBox, QSpinBox,
    QDoubleSpinBox, QGroupBox, QListWidget, QListWidgetItem, QMessageBox,
    QFileDialog, QTabWidget, QWidget, QScrollArea, QFrame, QSplitter,
    QInputDialog, QSizePolicy,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from conkystudio.plugins.schema import (
    ALLOWED_CATEGORIES,
    ALLOWED_KINDS,
    ALLOWED_OUTPUT_KINDS,
    ALLOWED_SOURCE_OUTPUT_KINDS,
    ALLOWED_POLL_MODES,
    CANVAS_EXT_ALLOWED_KEYS,
    PluginManifest,
    PluginNode,
    PluginProperty,
)
from conkystudio.plugins import loader as plugin_loader


# id must match loader._ID_RE
_ID_RE = re.compile(r"^(logic|visual|source|canvas_ext)(\.[a-z][a-z0-9_]*)+$")
_PROP_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")

LOCAL_PLUGINS_DIR = os.path.expanduser("~/.config/conky-studio/plugins")

# Sensible starter bodies so authors are not staring at a blank box.
_STARTER_BODIES = {
    "logic": (
        "-- Return a Lua expression. Use {property_key} for substituted values.\n"
        "-- Example: clamp a number\n"
        "math.max({min_v}, math.min({max_v}, tonumber({value}) or 0))"
    ),
    "visual": (
        "    -- Draw with cr, W, H in scope. Use {property_key} placeholders.\n"
        "    -- Example: filled circle at (cx, cy)\n"
        "    local r, g, b = {color}\n"
        "    cairo_set_source_rgba(cr, r, g, b, {opacity})\n"
        "    cairo_arc(cr, {cx}, {cy}, {radius}, 0, 2 * math.pi)\n"
        "    cairo_fill(cr)"
    ),
    "source": (
        "#!/usr/bin/env bash\n"
        "# Print a single value to stdout (last line is the value).\n"
        "# Use {property_key} placeholders; they become literal text at build.\n"
        "echo \"0\""
    ),
    "canvas_ext": "",
}


def _default_id_for_category(category: str) -> str:
    return f"{category}.plugin.my_node"


def _plugin_to_export_dict(plugin: PluginNode) -> dict:
    """JSON-serializable plugin object (same shape as plugins.json entries)."""
    return plugin_loader._plugin_to_dict(plugin)


def validate_plugin_draft(plugin: PluginNode) -> list[str]:
    """Run the same checks as loader validation without registering."""
    try:
        return plugin_loader.validate_only(
            PluginManifest(api_version="1.1", plugins=[plugin], source="plugin-creator")
        )
    except Exception as e:
        return [str(e)]


# ---------------------------------------------------------------------------
# Property row editor
# ---------------------------------------------------------------------------

class _PropertyEditorDialog(QDialog):
    """Add or edit one PluginProperty."""

    def __init__(self, prop: Optional[PluginProperty] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Property" if prop else "Add property")
        self.resize(420, 420)
        self.result_prop: Optional[PluginProperty] = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.key_edit = QLineEdit(prop.key if prop else "")
        self.key_edit.setPlaceholderText("e.g. radius")
        form.addRow("Key", self.key_edit)

        self.label_edit = QLineEdit(prop.label if prop else "")
        self.label_edit.setPlaceholderText("Shown in the inspector")
        form.addRow("Label", self.label_edit)

        self.kind_combo = QComboBox()
        for k in sorted(ALLOWED_KINDS):
            self.kind_combo.addItem(k)
        if prop and prop.kind in ALLOWED_KINDS:
            self.kind_combo.setCurrentText(prop.kind)
        form.addRow("Kind", self.kind_combo)

        self.default_edit = QLineEdit("" if prop is None else str(prop.default))
        form.addRow("Default", self.default_edit)

        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-1e9, 1e9)
        self.min_spin.setDecimals(4)
        self.min_spin.setValue(float(prop.minimum) if prop else 0.0)
        form.addRow("Minimum", self.min_spin)

        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-1e9, 1e9)
        self.max_spin.setDecimals(4)
        self.max_spin.setValue(float(prop.maximum) if prop else 100.0)
        form.addRow("Maximum", self.max_spin)

        self.step_spin = QDoubleSpinBox()
        self.step_spin.setRange(0.0001, 1e6)
        self.step_spin.setDecimals(4)
        self.step_spin.setValue(float(prop.step) if prop else 1.0)
        form.addRow("Step", self.step_spin)

        self.choices_edit = QLineEdit(
            ",".join(prop.choices) if prop and prop.choices else ""
        )
        self.choices_edit.setPlaceholderText("enum only: a,b,c")
        form.addRow("Choices", self.choices_edit)

        self.choice_labels_edit = QLineEdit(
            ",".join(prop.choice_labels) if prop and prop.choice_labels else ""
        )
        self.choice_labels_edit.setPlaceholderText("optional friendly labels")
        form.addRow("Choice labels", self.choice_labels_edit)

        self.bindable_chk = QCheckBox("Bindable (accepts a wire)")
        self.bindable_chk.setChecked(bool(prop.bindable) if prop else False)
        form.addRow(self.bindable_chk)

        self.accepts_edit = QLineEdit(
            ",".join(prop.accepts) if prop and prop.accepts else ""
        )
        self.accepts_edit.setPlaceholderText("e.g. percent,number,celsius")
        form.addRow("Accepts kinds", self.accepts_edit)

        self.group_edit = QLineEdit(prop.group if prop else "General")
        form.addRow("Group", self.group_edit)

        self.help_edit = QPlainTextEdit(prop.help if prop else "")
        self.help_edit.setMaximumHeight(60)
        form.addRow("Help", self.help_edit)

        layout.addLayout(form)

        btns = QHBoxLayout()
        ok = QPushButton("OK")
        ok.setObjectName("primary")
        ok.clicked.connect(self._accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def _accept(self):
        key = self.key_edit.text().strip()
        if not _PROP_KEY_RE.match(key):
            QMessageBox.warning(
                self, "Property",
                "Key must be lowercase letters/digits/underscores, starting with a letter.",
            )
            return
        kind = self.kind_combo.currentText()
        default_raw = self.default_edit.text().strip()
        default: Any = default_raw
        if kind in ("float", "int"):
            try:
                default = float(default_raw) if kind == "float" else int(float(default_raw))
            except ValueError:
                default = 0.0 if kind == "float" else 0
        elif kind == "bool":
            default = default_raw.lower() in ("1", "true", "yes", "on")
        choices = None
        choice_labels = None
        if kind == "enum":
            choices = [c.strip() for c in self.choices_edit.text().split(",") if c.strip()]
            if not choices:
                QMessageBox.warning(self, "Property", "Enum kind needs at least one choice.")
                return
            labels = [c.strip() for c in self.choice_labels_edit.text().split(",") if c.strip()]
            choice_labels = labels if labels else None
        accepts = None
        accepts_raw = self.accepts_edit.text().strip()
        if accepts_raw:
            accepts = [a.strip() for a in accepts_raw.split(",") if a.strip()]

        self.result_prop = PluginProperty(
            key=key,
            label=self.label_edit.text().strip() or key,
            kind=kind,
            default=default,
            minimum=self.min_spin.value(),
            maximum=self.max_spin.value(),
            step=self.step_spin.value(),
            choices=choices,
            choice_labels=choice_labels,
            bindable=self.bindable_chk.isChecked(),
            accepts=accepts,
            help=self.help_edit.toPlainText().strip(),
            group=self.group_edit.text().strip() or "General",
        )
        self.accept()


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class PluginCreatorDialog(QDialog):
    """Tools → Plugin Creation — author, validate, and export a plugin."""

    def __init__(self, parent=None, *, seed_from_custom_lua: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Plugin Creation")
        self.resize(780, 720)
        self.exported_path: str = ""
        self._properties: list[PluginProperty] = []
        self._seed_lua = seed_from_custom_lua or ""

        root = QVBoxLayout(self)

        heading = QLabel("Plugin Creation")
        heading.setProperty("role", "heading")
        root.addWidget(heading)

        intro = QLabel(
            "Turn an escape-hatch custom node into a portable plugin. "
            "Fill identity, properties, and the code body, then Validate and Export. "
            "Exported JSON matches the community plugins.json / local pack format."
        )
        intro.setProperty("role", "caption")
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self._build_identity_tab()
        self._build_properties_tab()
        self._build_body_tab()
        self._build_media_tab()
        self._build_export_tab()

        # Footer actions
        footer = QHBoxLayout()
        self.validate_btn = QPushButton("Validate")
        self.validate_btn.clicked.connect(self._validate)
        footer.addWidget(self.validate_btn)

        self.export_btn = QPushButton("Export JSON…")
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self._export_json)
        footer.addWidget(self.export_btn)

        self.install_btn = QPushButton("Install locally")
        self.install_btn.setToolTip(
            f"Write into {LOCAL_PLUGINS_DIR} and register for this session"
        )
        self.install_btn.clicked.connect(self._install_local)
        footer.addWidget(self.install_btn)

        footer.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self.status = QLabel("")
        self.status.setProperty("role", "caption")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self._on_category_changed()
        if self._seed_lua:
            self.body_edit.setPlainText(self._seed_lua)

    # ---- tabs ----------------------------------------------------------

    def _build_identity_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        self.category_combo = QComboBox()
        for c in sorted(ALLOWED_CATEGORIES):
            self.category_combo.addItem(c)
        self.category_combo.setCurrentText("visual")
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        form.addRow("Category", self.category_combo)

        self.id_edit = QLineEdit(_default_id_for_category("visual"))
        self.id_edit.setPlaceholderText("visual.plugin.my_ring")
        form.addRow("Type id", self.id_edit)

        self.label_edit = QLineEdit("My Plugin Node")
        form.addRow("Label", self.label_edit)

        self.author_edit = QLineEdit("")
        form.addRow("Author", self.author_edit)

        self.version_edit = QLineEdit("1.0.0")
        form.addRow("Version", self.version_edit)

        self.desc_edit = QPlainTextEdit("")
        self.desc_edit.setMaximumHeight(80)
        self.desc_edit.setPlaceholderText("Short description shown in the Plugins dialog / store.")
        form.addRow("Description", self.desc_edit)

        self.color_edit = QLineEdit("#8a5fd6")
        form.addRow("Accent colour", self.color_edit)

        self.subcategory_edit = QLineEdit("Plugins")
        form.addRow("Subcategory", self.subcategory_edit)

        self.output_kind_combo = QComboBox()
        self.output_kind_combo.addItem("(none)")
        for k in sorted(ALLOWED_OUTPUT_KINDS):
            self.output_kind_combo.addItem(k)
        form.addRow("Output kind", self.output_kind_combo)

        self.simple_mode_chk = QCheckBox("Show in Simple palette")
        form.addRow(self.simple_mode_chk)

        # Source-only polling defaults
        self.poll_mode_combo = QComboBox()
        for m in sorted(ALLOWED_POLL_MODES):
            self.poll_mode_combo.addItem(m)
        self.poll_mode_combo.setCurrentText("execi")
        form.addRow("Poll mode default", self.poll_mode_combo)

        self.poll_interval_spin = QSpinBox()
        self.poll_interval_spin.setRange(1, 3600)
        self.poll_interval_spin.setValue(5)
        form.addRow("Poll interval (sec)", self.poll_interval_spin)

        hint = QLabel(
            "Id must look like category.plugin.name (lowercase). "
            "Logic needs output_kind + lua_expr; visual needs lua_draw_body; "
            "source needs script_body; canvas_ext needs conf directives."
        )
        hint.setProperty("role", "caption")
        hint.setWordWrap(True)
        form.addRow(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(w)
        self.tabs.addTab(scroll, "1 · Identity")

    def _build_properties_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        layout.addWidget(QLabel(
            "Properties become inspector fields. In the code body, reference them as {key}."
        ))

        self.prop_list = QListWidget()
        self.prop_list.setMinimumHeight(200)
        layout.addWidget(self.prop_list, 1)

        row = QHBoxLayout()
        add_btn = QPushButton("Add…")
        add_btn.clicked.connect(self._add_property)
        edit_btn = QPushButton("Edit…")
        edit_btn.clicked.connect(self._edit_property)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_property)
        presets_btn = QPushButton("Add common…")
        presets_btn.setToolTip("Insert typical position / style properties for the current category")
        presets_btn.clicked.connect(self._add_common_properties)
        row.addWidget(add_btn)
        row.addWidget(edit_btn)
        row.addWidget(remove_btn)
        row.addWidget(presets_btn)
        row.addStretch(1)
        layout.addLayout(row)

        self.tabs.addTab(w, "2 · Properties")

    def _build_body_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        self.body_hint = QLabel("")
        self.body_hint.setWordWrap(True)
        self.body_hint.setProperty("role", "caption")
        layout.addWidget(self.body_hint)

        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)

        self.body_edit = QPlainTextEdit()
        self.body_edit.setFont(mono)
        self.body_edit.setPlaceholderText("Code body — see Identity for which field this maps to.")
        layout.addWidget(self.body_edit, 1)

        self.helpers_edit = QPlainTextEdit()
        self.helpers_edit.setFont(mono)
        self.helpers_edit.setMaximumHeight(100)
        self.helpers_edit.setPlaceholderText(
            "Optional lua_helpers (emitted once per project). Leave blank if unused."
        )
        layout.addWidget(QLabel("Shared helpers (visual only, optional)"))
        layout.addWidget(self.helpers_edit)

        # canvas_ext: key=value lines
        self.conf_edit = QPlainTextEdit()
        self.conf_edit.setFont(mono)
        self.conf_edit.setMaximumHeight(120)
        self.conf_edit.setPlaceholderText(
            "canvas_ext only: one directive per line, e.g.\n"
            "border_width={width}\n"
            "temperature_unit=celsius"
        )
        layout.addWidget(QLabel("Conf directives (canvas_ext)"))
        layout.addWidget(self.conf_edit)

        load_custom = QPushButton("Paste starter template")
        load_custom.clicked.connect(self._load_starter)
        layout.addWidget(load_custom)

        self.tabs.addTab(w, "3 · Code body")

    def _build_media_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        self.tags_edit = QLineEdit("")
        self.tags_edit.setPlaceholderText("comma-separated, e.g. gauge,glow,hud")
        form.addRow("Tags", self.tags_edit)

        self.homepage_edit = QLineEdit("")
        form.addRow("Homepage URL", self.homepage_edit)

        self.license_edit = QLineEdit("")
        self.license_edit.setPlaceholderText("e.g. MIT")
        form.addRow("License", self.license_edit)

        self.icon_edit = QLineEdit("")
        self.icon_edit.setPlaceholderText("https://…/icon.png  or  bare icon.png")
        form.addRow("Icon", self.icon_edit)

        self.screenshot_edit = QLineEdit("")
        form.addRow("Screenshot (store)", self.screenshot_edit)

        self.gif_edit = QLineEdit("")
        form.addRow("GIF demo (store)", self.gif_edit)

        self.video_edit = QLineEdit("")
        form.addRow("Video link (store)", self.video_edit)

        note = QLabel(
            "Icon is the only media field Studio shows in the palette / Plugins list. "
            "Screenshot, GIF, and video are for the community store website only."
        )
        note.setProperty("role", "caption")
        note.setWordWrap(True)
        form.addRow(note)

        self.tabs.addTab(w, "4 · Media")

    def _build_export_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Validation output and export preview"))

        self.validation_log = QPlainTextEdit()
        self.validation_log.setReadOnly(True)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.validation_log.setFont(mono)
        layout.addWidget(self.validation_log, 1)

        preview_btn = QPushButton("Preview JSON")
        preview_btn.clicked.connect(self._preview_json)
        layout.addWidget(preview_btn)

        self.tabs.addTab(w, "5 · Validate / Export")

    # ---- category ------------------------------------------------------

    def _on_category_changed(self, *_args):
        cat = self.category_combo.currentText()
        # Nudge id prefix if it still matches an old category
        current_id = self.id_edit.text().strip()
        if not current_id or not current_id.startswith(cat + "."):
            # preserve suffix after first two segments when possible
            parts = current_id.split(".")
            if len(parts) >= 3 and parts[1] == "plugin":
                self.id_edit.setText(f"{cat}.plugin.{parts[-1]}")
            else:
                self.id_edit.setText(_default_id_for_category(cat))

        is_source = cat == "source"
        is_logic = cat == "logic"
        is_canvas = cat == "canvas_ext"
        self.poll_mode_combo.setEnabled(is_source)
        self.poll_interval_spin.setEnabled(is_source)
        self.output_kind_combo.setEnabled(is_logic or is_source)
        self.helpers_edit.setEnabled(cat == "visual")
        self.conf_edit.setEnabled(is_canvas)
        self.body_edit.setEnabled(not is_canvas)

        hints = {
            "logic": "Body = lua_expr (expression returning a value). Placeholders: {prop_key}.",
            "visual": "Body = lua_draw_body inside draw_node_*(cr, W, H). Placeholders: {prop_key}. Color props expand to r, g, b floats.",
            "source": "Body = bash script_body. Last stdout line is the value. Placeholders become literal text.",
            "canvas_ext": "Use Conf directives below (allowed keys only). Body box is unused.",
        }
        self.body_hint.setText(hints.get(cat, ""))

        if is_logic and self.output_kind_combo.currentText() == "(none)":
            self.output_kind_combo.setCurrentText("number")
        if is_source and self.output_kind_combo.currentText() == "(none)":
            self.output_kind_combo.setCurrentText("number")

    def _load_starter(self):
        cat = self.category_combo.currentText()
        if cat == "canvas_ext":
            self.conf_edit.setPlainText("border_width={width}\n")
            return
        self.body_edit.setPlainText(_STARTER_BODIES.get(cat, ""))

    # ---- properties list -----------------------------------------------

    def _refresh_prop_list(self):
        self.prop_list.clear()
        for p in self._properties:
            extra = "  [bindable]" if p.bindable else ""
            self.prop_list.addItem(f"{p.key}  ({p.kind})  default={p.default!r}{extra}")

    def _add_property(self):
        dlg = _PropertyEditorDialog(parent=self)
        if dlg.exec() and dlg.result_prop:
            if any(p.key == dlg.result_prop.key for p in self._properties):
                QMessageBox.warning(self, "Property", f"Duplicate key: {dlg.result_prop.key}")
                return
            self._properties.append(dlg.result_prop)
            self._refresh_prop_list()

    def _edit_property(self):
        row = self.prop_list.currentRow()
        if row < 0 or row >= len(self._properties):
            return
        dlg = _PropertyEditorDialog(self._properties[row], parent=self)
        if dlg.exec() and dlg.result_prop:
            new_key = dlg.result_prop.key
            for i, p in enumerate(self._properties):
                if i != row and p.key == new_key:
                    QMessageBox.warning(self, "Property", f"Duplicate key: {new_key}")
                    return
            self._properties[row] = dlg.result_prop
            self._refresh_prop_list()

    def _remove_property(self):
        row = self.prop_list.currentRow()
        if row < 0 or row >= len(self._properties):
            return
        del self._properties[row]
        self._refresh_prop_list()

    def _add_common_properties(self):
        cat = self.category_combo.currentText()
        existing = {p.key for p in self._properties}
        presets: list[PluginProperty] = []
        if cat == "visual":
            presets = [
                PluginProperty(key="cx", label="Center X", kind="int", default=100,
                               minimum=-4000, maximum=4000, group="Position"),
                PluginProperty(key="cy", label="Center Y", kind="int", default=100,
                               minimum=-4000, maximum=4000, group="Position"),
                PluginProperty(key="radius", label="Radius", kind="float", default=40.0,
                               minimum=1, maximum=2000, group="Shape"),
                PluginProperty(key="color", label="Colour", kind="color", default="#4fd1c5",
                               group="Style"),
                PluginProperty(key="opacity", label="Opacity", kind="float", default=1.0,
                               minimum=0, maximum=1, step=0.05, group="Style"),
            ]
        elif cat == "logic":
            presets = [
                PluginProperty(key="value", label="Value", kind="float", default=0.0,
                               minimum=-1e9, maximum=1e9, bindable=True,
                               accepts=["percent", "celsius", "number"], group="Input"),
                PluginProperty(key="min_v", label="Min", kind="float", default=0.0, group="Range"),
                PluginProperty(key="max_v", label="Max", kind="float", default=100.0, group="Range"),
            ]
        elif cat == "source":
            presets = [
                PluginProperty(key="endpoint", label="Endpoint / arg", kind="string",
                               default="", group="Config"),
            ]
        elif cat == "canvas_ext":
            presets = [
                PluginProperty(key="width", label="Border width", kind="int", default=1,
                               minimum=0, maximum=50, group="Style"),
            ]
        added = 0
        for p in presets:
            if p.key not in existing:
                self._properties.append(p)
                added += 1
        self._refresh_prop_list()
        self.status.setText(f"Added {added} common property(ies).")

    # ---- build PluginNode ----------------------------------------------

    def build_plugin(self) -> PluginNode:
        cat = self.category_combo.currentText()
        out_kind = self.output_kind_combo.currentText()
        if out_kind == "(none)":
            out_kind = None

        tags = [t.strip() for t in self.tags_edit.text().split(",") if t.strip()]

        body = self.body_edit.toPlainText()
        helpers = self.helpers_edit.toPlainText().strip() or None

        conf_directives: dict = {}
        if cat == "canvas_ext":
            for line in self.conf_edit.toPlainText().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                conf_directives[k.strip()] = v.strip()

        return PluginNode(
            id=self.id_edit.text().strip(),
            category=cat,
            label=self.label_edit.text().strip() or self.id_edit.text().strip(),
            author=self.author_edit.text().strip(),
            version=self.version_edit.text().strip() or "1.0.0",
            description=self.desc_edit.toPlainText().strip(),
            color=self.color_edit.text().strip() or "#5f8fd6",
            subcategory=self.subcategory_edit.text().strip() or "Plugins",
            output_kind=out_kind,
            properties=list(self._properties),
            lua_expr=body if cat == "logic" else None,
            lua_draw_body=body if cat == "visual" else None,
            tags=tags,
            lua_helpers=helpers if cat == "visual" else None,
            simple_mode=self.simple_mode_chk.isChecked(),
            homepage=self.homepage_edit.text().strip(),
            license=self.license_edit.text().strip(),
            icon=self.icon_edit.text().strip(),
            screenshot=self.screenshot_edit.text().strip(),
            gif=self.gif_edit.text().strip(),
            video=self.video_edit.text().strip(),
            script_body=body if cat == "source" else None,
            poll_mode_default=self.poll_mode_combo.currentText() if cat == "source" else "execi",
            poll_interval_default=self.poll_interval_spin.value() if cat == "source" else 5,
            conf_directives=conf_directives,
        )

    # ---- validate / export ---------------------------------------------

    def _validate(self) -> bool:
        plugin = self.build_plugin()
        errors = validate_plugin_draft(plugin)
        # Extra client-side checks that mirror loader._validate closely
        if not _ID_RE.match(plugin.id):
            errors.append(
                f"{plugin.id}: id must match logic.* / visual.* / source.* / canvas_ext.* "
                f"(e.g. visual.plugin.ring)"
            )
        if plugin.category == "logic" and not (plugin.lua_expr or "").strip():
            errors.append(f"{plugin.id}: logic plugins need lua_expr")
        if plugin.category == "visual" and not (plugin.lua_draw_body or "").strip():
            errors.append(f"{plugin.id}: visual plugins need lua_draw_body")
        if plugin.category == "source" and not (plugin.script_body or "").strip():
            errors.append(f"{plugin.id}: source plugins need script_body")
        if plugin.category == "canvas_ext":
            if not plugin.conf_directives:
                errors.append(f"{plugin.id}: canvas_ext needs at least one conf directive")
            for key in plugin.conf_directives:
                if key not in CANVAS_EXT_ALLOWED_KEYS:
                    errors.append(
                        f"{plugin.id}: conf key {key!r} not in allowed list "
                        f"({sorted(CANVAS_EXT_ALLOWED_KEYS)})"
                    )

        # Placeholder coverage
        template = (
            (plugin.lua_expr or "") + "\n" + (plugin.lua_draw_body or "") + "\n"
            + (plugin.lua_helpers or "") + "\n" + (plugin.script_body or "") + "\n"
            + "\n".join(plugin.conf_directives.values())
        )
        keys = {p.key for p in plugin.properties}
        for match in re.findall(r"\{([a-z][a-z0-9_]*)\}", template):
            if match not in keys and match != "cr":
                errors.append(
                    f"{plugin.id}: template references {{{match}}} but no such property"
                )

        self.tabs.setCurrentIndex(4)
        if errors:
            self.validation_log.setPlainText(
                "VALIDATION FAILED\n\n" + "\n".join(f"• {e}" for e in errors)
            )
            self.status.setText(f"{len(errors)} validation error(s).")
            return False

        self.validation_log.setPlainText(
            "VALIDATION OK\n\n"
            f"id: {plugin.id}\n"
            f"category: {plugin.category}\n"
            f"properties: {len(plugin.properties)}\n"
            f"Ready to export or install."
        )
        self.status.setText("Validation passed.")
        return True

    def _preview_json(self):
        plugin = self.build_plugin()
        payload = {
            "api_version": "1.1",
            "updated_at": "",
            "source": "plugin-creator",
            "plugins": [_plugin_to_export_dict(plugin)],
        }
        self.tabs.setCurrentIndex(4)
        self.validation_log.setPlainText(json.dumps(payload, indent=2) + "\n")

    def _export_json(self):
        if not self._validate():
            QMessageBox.warning(
                self, "Plugin Creation",
                "Fix validation errors before exporting.",
            )
            return
        plugin = self.build_plugin()
        default_name = plugin.id.replace(".", "_") + ".json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export plugin JSON",
            default_name,
            "Plugin JSON (*.json);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        # Single-plugin file (community store one-file-per-plugin style)
        # OR a mini-manifest — both are loadable via load_manifest_file.
        as_manifest = QMessageBox.question(
            self,
            "Export format",
            "Export as a full manifest (plugins: […])?\n\n"
            "Yes = manifest wrapper (drop into ~/.config/conky-studio/plugins/)\n"
            "No  = single plugin object (for $ref / store packs)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        entry = _plugin_to_export_dict(plugin)
        if as_manifest == QMessageBox.StandardButton.Yes:
            payload = {
                "api_version": "1.1",
                "updated_at": "",
                "source": "plugin-creator",
                "plugins": [entry],
            }
        else:
            payload = entry

        try:
            Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Export failed", str(e))
            return

        self.exported_path = path
        self.status.setText(f"Exported to {path}")
        QMessageBox.information(self, "Export complete", f"Wrote:\n{path}")

    def _install_local(self):
        if not self._validate():
            QMessageBox.warning(
                self, "Plugin Creation",
                "Fix validation errors before installing.",
            )
            return
        plugin = self.build_plugin()
        try:
            plugin_loader.register_plugin(plugin, source="plugin-creator")
            plugin_loader.persist_plugins([plugin], source="plugin-creator")
            if hasattr(plugin_loader, "clear_uninstalled"):
                plugin_loader.clear_uninstalled([plugin.id])
        except plugin_loader.PluginError as e:
            QMessageBox.warning(self, "Install failed", str(e))
            return
        except Exception as e:
            QMessageBox.warning(self, "Install failed", str(e))
            return

        self.exported_path = str(plugin_loader.installed_pack_path())
        self.status.setText(f"Installed {plugin.id} into local plugins pack.")
        QMessageBox.information(
            self,
            "Installed",
            f"{plugin.label} ({plugin.id}) is registered for this session "
            f"and saved under {LOCAL_PLUGINS_DIR}.\n\n"
            "It appears in the Nodes palette after refresh.",
        )


# ---------------------------------------------------------------------------
# Optional: seed from a selected Custom Lua node in Studio
# ---------------------------------------------------------------------------

def open_plugin_creator_from_node(parent, node) -> Optional[str]:
    """If *node* is visual.custom_lua or source.custom_script, pre-fill the dialog.

    Returns exported path or empty string.
    """
    seed = None
    category_hint = "visual"
    if node is not None:
        ntype = getattr(node, "type", "")
        props = getattr(node, "props", {}) or {}
        if ntype == "visual.custom_lua":
            seed = str(props.get("code") or "")
            category_hint = "visual"
        elif ntype == "source.custom_script":
            seed = str(props.get("script_body") or "")
            category_hint = "source"

    dialog = PluginCreatorDialog(parent, seed_from_custom_lua=seed)
    if seed is not None:
        dialog.category_combo.setCurrentText(category_hint)
        dialog._on_category_changed()
        if seed:
            dialog.body_edit.setPlainText(seed)
    dialog.exec()
    return dialog.exported_path or None
 
