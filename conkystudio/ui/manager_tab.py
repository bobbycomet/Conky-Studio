"""
The Manager tab: "Discover installed themes. Install by drag-and-drop.
Launch and stop themes." Everything here operates on real folders under
~/.config/conky and ~/.conky (see manager/scanner.py, installer.py,
process.py) -- Conky Studio never needs to be running for an installed
theme to keep working, this tab is just a convenient front end for the
same start.sh anyone could run by hand.
"""
from __future__ import annotations

import json
import os
import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QSplitter, QTextEdit, QFileDialog, QInputDialog, QMessageBox, QFrame,
    QComboBox,
)
from PyQt6.QtGui import QPixmap, QIcon, QDragEnterEvent, QDropEvent, QFont
from PyQt6.QtCore import Qt, QSize

from conkystudio.manager import scanner, installer
from conkystudio.manager.process import ThemeProcessManager
from conkystudio.model.theme_meta import ThemeMeta, THEME_META_FILENAME
from conkystudio.hardware import discovery

THUMB_SIZE = QSize(96, 96)


class _DropArea(QFrame):
    def __init__(self, on_files, parent=None):
        super().__init__(parent)
        self._on_files = on_files
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(56)
        layout = QVBoxLayout(self)
        label = QLabel("Drop a .zip, .tar.gz, or .tar theme here to install it, or click to browse")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.setStyleSheet("_DropArea { border: 1px dashed #3a4048; border-radius: 8px; }")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose theme archive(s)",
            "",
            "Theme archives (*.zip *.tar.gz *.tgz *.tar);;All files (*)",
        )
        if paths:
            self._on_files(paths)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._on_files(paths)


class ManagerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.process_manager = ThemeProcessManager(self)
        self.process_manager.state_changed.connect(self._on_state_changed)
        self.process_manager.log_line.connect(self._on_log_line)
        self.themes: list = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        heading_row = QHBoxLayout()
        heading = QLabel("Theme Manager")
        heading.setProperty("role", "heading")
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        heading_row.addWidget(refresh_btn)
        outer.addLayout(heading_row)

        self.drop_area = _DropArea(self._install_files)
        outer.addWidget(self.drop_area)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        self.list_widget = QListWidget()
        self.list_widget.setIconSize(THUMB_SIZE)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.list_widget)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.detail_name = QLabel("\u2014")
        self.detail_name.setProperty("role", "heading")
        detail_layout.addWidget(self.detail_name)
        self.detail_meta = QLabel("")
        self.detail_meta.setProperty("role", "caption")
        self.detail_meta.setWordWrap(True)
        detail_layout.addWidget(self.detail_meta)

        # Per-theme monitor pin (saved into theme.json, applied at Start)
        pin_row = QHBoxLayout()
        pin_row.addWidget(QLabel("Pin to monitor"))
        self.monitor_combo = QComboBox()
        self.monitor_combo.setToolTip(
            "Pin this theme to a specific output when you press Start. "
            "Saved into theme.json. 'Auto' leaves placement to the conf / alignment."
        )
        self._fill_monitor_combo()
        self.monitor_combo.currentIndexChanged.connect(self._on_monitor_changed)
        pin_row.addWidget(self.monitor_combo, 1)
        rescan_mon_btn = QPushButton("Rescan")
        rescan_mon_btn.setToolTip("Rescan connected monitors")
        rescan_mon_btn.clicked.connect(self._rescan_monitors)
        pin_row.addWidget(rescan_mon_btn)
        detail_layout.addLayout(pin_row)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("\u25b6 Start")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self._start_selected)
        self.stop_btn = QPushButton("\u25a0 Stop")
        self.stop_btn.clicked.connect(self._stop_selected)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        detail_layout.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        open_folder_btn = QPushButton("Open Folder")
        open_folder_btn.clicked.connect(self._open_folder_selected)
        duplicate_btn = QPushButton("Duplicate")
        duplicate_btn.clicked.connect(self._duplicate_selected)
        export_btn = QPushButton("Export .zip")
        export_btn.clicked.connect(self._export_selected)
        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setObjectName("danger")
        uninstall_btn.clicked.connect(self._uninstall_selected)
        for b in (open_folder_btn, duplicate_btn, export_btn, uninstall_btn):
            btn_row2.addWidget(b)
        detail_layout.addLayout(btn_row2)

        # Shown only when the selected theme has no theme.json yet.
        self.generate_meta_btn = QPushButton("Generate theme.json for this theme")
        self.generate_meta_btn.setObjectName("primary")
        self.generate_meta_btn.clicked.connect(self._generate_theme_json)
        self.generate_meta_btn.setVisible(False)
        detail_layout.addWidget(self.generate_meta_btn)

        # theme.json — collapsible viewer/editor (same pattern as README).
        # Always visible when a theme is selected so you can edit at any time.
        meta_row = QHBoxLayout()
        self.meta_toggle = QPushButton("\u25b8 theme.json")
        self.meta_toggle.setCheckable(True)
        self.meta_toggle.clicked.connect(self._toggle_meta)
        meta_row.addWidget(self.meta_toggle)
        meta_row.addStretch(1)
        self.meta_edit_btn = QPushButton("Edit")
        self.meta_edit_btn.clicked.connect(self._start_editing_meta)
        meta_row.addWidget(self.meta_edit_btn)
        self.meta_save_btn = QPushButton("Save")
        self.meta_save_btn.setObjectName("primary")
        self.meta_save_btn.clicked.connect(self._save_meta)
        self.meta_save_btn.setVisible(False)
        meta_row.addWidget(self.meta_save_btn)
        self.meta_cancel_btn = QPushButton("Cancel")
        self.meta_cancel_btn.clicked.connect(self._cancel_editing_meta)
        self.meta_cancel_btn.setVisible(False)
        meta_row.addWidget(self.meta_cancel_btn)
        detail_layout.addLayout(meta_row)

        self.meta_view = QTextEdit()
        self.meta_view.setReadOnly(True)
        self.meta_view.setVisible(False)
        self.meta_view.setFont(QFont("monospace"))
        self.meta_view.setPlaceholderText(
            '{\n  "name": "My Theme",\n  "author": "",\n  "version": "1.0",\n'
            '  "description": "",\n  "resolution": ""\n}'
        )
        detail_layout.addWidget(self.meta_view, 1)

        # README stays collapsed by default -- a long one previously pushed
        # the action buttons above out of reach on shorter windows; now the
        # buttons are always at a fixed position and README only takes
        # space once you ask for it.
        readme_row = QHBoxLayout()
        self.readme_toggle = QPushButton("\u25b8 README")
        self.readme_toggle.setCheckable(True)
        self.readme_toggle.clicked.connect(self._toggle_readme)
        readme_row.addWidget(self.readme_toggle)
        readme_row.addStretch(1)
        self.readme_edit_btn = QPushButton("Edit")
        self.readme_edit_btn.clicked.connect(self._start_editing_readme)
        readme_row.addWidget(self.readme_edit_btn)
        self.readme_save_btn = QPushButton("Save")
        self.readme_save_btn.setObjectName("primary")
        self.readme_save_btn.clicked.connect(self._save_readme)
        self.readme_save_btn.setVisible(False)
        readme_row.addWidget(self.readme_save_btn)
        self.readme_cancel_btn = QPushButton("Cancel")
        self.readme_cancel_btn.clicked.connect(self._cancel_editing_readme)
        self.readme_cancel_btn.setVisible(False)
        readme_row.addWidget(self.readme_cancel_btn)
        detail_layout.addLayout(readme_row)

        self.readme_view = QTextEdit()
        self.readme_view.setReadOnly(True)
        self.readme_view.setVisible(False)
        detail_layout.addWidget(self.readme_view, 1)

        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        current_path = self._selected_path()
        self.themes = scanner.scan_installed_themes()
        self.list_widget.clear()
        for t in self.themes:
            item = QListWidgetItem(t.meta.name)
            if t.has_preview:
                item.setIcon(QIcon(QPixmap(t.preview_path).scaled(
                    THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)))
            item.setData(Qt.ItemDataRole.UserRole, t.path)
            running = self.process_manager.is_running(t.path)
            marker = "\u25cf " if running else ""
            item.setText(f"{marker}{t.meta.name}")
            self.list_widget.addItem(item)
            if t.path == current_path:
                self.list_widget.setCurrentItem(item)
        if self.list_widget.currentItem() is None and self.list_widget.count():
            self.list_widget.setCurrentRow(0)

    def _selected_path(self) -> str:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def _selected_theme(self):
        path = self._selected_path()
        for t in self.themes:
            if t.path == path:
                return t
        return None

    def _on_selection_changed(self, *_args):
        t = self._selected_theme()
        if t is None:
            self.detail_name.setText("\u2014")
            self.detail_meta.setText("")
            self.readme_view.setPlainText("")
            self.meta_view.setPlainText("")
            self.generate_meta_btn.setVisible(False)
            self.meta_toggle.setEnabled(False)
            self.meta_edit_btn.setEnabled(False)
            self.readme_toggle.setEnabled(False)
            self.readme_edit_btn.setEnabled(False)
            self.monitor_combo.setEnabled(False)
            return

        self.meta_toggle.setEnabled(True)
        self.meta_edit_btn.setEnabled(True)
        self.readme_toggle.setEnabled(True)
        self.readme_edit_btn.setEnabled(True)
        self.monitor_combo.setEnabled(True)

        self.detail_name.setText(t.meta.name)
        self.detail_meta.setText(
            f"by {t.meta.author or 'unknown'} \u00b7 v{t.meta.version} \u00b7 {t.meta.resolution}\n{t.meta.description}"
        )

        # --- monitor pin ---
        self._load_monitor_for_theme(t)

        # --- README ---
        readme_path = os.path.join(t.path, "README.md")
        if os.path.isfile(readme_path):
            with open(readme_path, "r", encoding="utf-8", errors="replace") as f:
                self.readme_view.setPlainText(f.read())
        else:
            self.readme_view.setPlainText("(no README.md in this theme)")
        self.readme_toggle.setChecked(False)
        self.readme_view.setVisible(False)
        self.readme_toggle.setText("\u25b8 README")
        self.readme_view.setReadOnly(True)
        self.readme_edit_btn.setVisible(True)
        self.readme_save_btn.setVisible(False)
        self.readme_cancel_btn.setVisible(False)

        # --- theme.json ---
        meta_path = os.path.join(t.path, THEME_META_FILENAME)
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8", errors="replace") as f:
                    raw = f.read()
                try:
                    raw = json.dumps(json.loads(raw), indent=2, ensure_ascii=False) + "\n"
                except json.JSONDecodeError:
                    pass
                self.meta_view.setPlainText(raw)
            except OSError:
                self.meta_view.setPlainText("(could not read theme.json)")
        else:
            self.meta_view.setPlainText(
                "(no theme.json yet; use Generate above, or Edit and Save to create one)"
            )
        self.meta_toggle.setChecked(False)
        self.meta_view.setVisible(False)
        self.meta_toggle.setText("\u25b8 theme.json")
        self.meta_view.setReadOnly(True)
        self.meta_edit_btn.setVisible(True)
        self.meta_save_btn.setVisible(False)
        self.meta_cancel_btn.setVisible(False)

        self.generate_meta_btn.setVisible(not t.has_theme_json)

        running = self.process_manager.is_running(t.path)
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def _toggle_readme(self, checked: bool):
        self.readme_view.setVisible(checked)
        self.readme_toggle.setText(("\u25be" if checked else "\u25b8") + " README")

    def _start_editing_readme(self):
        t = self._selected_theme()
        if t is None:
            return
        self.readme_toggle.setChecked(True)
        self._toggle_readme(True)
        self.readme_view.setReadOnly(False)
        self.readme_view.setFocus()
        self.readme_edit_btn.setVisible(False)
        self.readme_save_btn.setVisible(True)
        self.readme_cancel_btn.setVisible(True)

    def _save_readme(self):
        t = self._selected_theme()
        if t is None:
            return
        with open(os.path.join(t.path, "README.md"), "w", encoding="utf-8") as f:
            f.write(self.readme_view.toPlainText())
        self.readme_view.setReadOnly(True)
        self.readme_edit_btn.setVisible(True)
        self.readme_save_btn.setVisible(False)
        self.readme_cancel_btn.setVisible(False)

    def _cancel_editing_readme(self):
        self._on_selection_changed()  # reloads README.md from disk, discarding unsaved edits
        self.readme_view.setReadOnly(True)
        self.readme_edit_btn.setVisible(True)
        self.readme_save_btn.setVisible(False)
        self.readme_cancel_btn.setVisible(False)

    def _toggle_meta(self, checked: bool):
        self.meta_view.setVisible(checked)
        self.meta_toggle.setText(("\u25be" if checked else "\u25b8") + " theme.json")

    def _start_editing_meta(self):
        t = self._selected_theme()
        if t is None:
            return
        # If there is no file yet, seed a sensible template from the scanned meta
        # so the user is not staring at the "(no theme.json yet…)" placeholder.
        meta_path = os.path.join(t.path, THEME_META_FILENAME)
        if not os.path.isfile(meta_path):
            seed = {
                "name": t.meta.name or "",
                "author": t.meta.author or "",
                "version": getattr(t.meta, "version", None) or "1.0",
                "description": t.meta.description or "",
                "resolution": t.meta.resolution or "",
            }
            self.meta_view.setPlainText(json.dumps(seed, indent=2, ensure_ascii=False) + "\n")
        self.meta_toggle.setChecked(True)
        self._toggle_meta(True)
        self.meta_view.setReadOnly(False)
        self.meta_view.setFocus()
        self.meta_edit_btn.setVisible(False)
        self.meta_save_btn.setVisible(True)
        self.meta_cancel_btn.setVisible(True)

    def _save_meta(self):
        t = self._selected_theme()
        if t is None:
            return
        text = self.meta_view.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "theme.json", "Content is empty, nothing saved.")
            return
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            QMessageBox.warning(
                self,
                "Invalid JSON",
                f"theme.json must be valid JSON before it can be saved:\n\n{e}",
            )
            return
        if not isinstance(data, dict):
            QMessageBox.warning(self, "Invalid theme.json", "Root value must be a JSON object.")
            return
        pretty = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        path = os.path.join(t.path, THEME_META_FILENAME)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(pretty)
        except OSError as e:
            QMessageBox.warning(self, "Couldn't save theme.json", str(e))
            return
        self.meta_view.setPlainText(pretty)
        self.meta_view.setReadOnly(True)
        self.meta_edit_btn.setVisible(True)
        self.meta_save_btn.setVisible(False)
        self.meta_cancel_btn.setVisible(False)
        # Refresh list + detail so name/author/version pick up the new values.
        self.refresh()

    def _cancel_editing_meta(self):
        self._on_selection_changed()  # reloads theme.json from disk, discarding unsaved edits
        self.meta_view.setReadOnly(True)
        self.meta_edit_btn.setVisible(True)
        self.meta_save_btn.setVisible(False)
        self.meta_cancel_btn.setVisible(False)

    def _generate_theme_json(self):
        t = self._selected_theme()
        if t is None:
            return
        name, ok = QInputDialog.getText(self, "Generate theme.json", "Theme name:", text=t.meta.name)
        if not ok or not name.strip():
            return
        author, _ok2 = QInputDialog.getText(self, "Generate theme.json", "Author (optional):", text=t.meta.author)
        description, _ok3 = QInputDialog.getText(
            self, "Generate theme.json", "Description (optional):", text=t.meta.description or ""
        )
        meta = ThemeMeta(
            name=name.strip(),
            author=(author or "").strip(),
            description=(description or "").strip(),
            resolution=t.meta.resolution,
            created_with="conky-studio (generated after the fact)",
        )
        meta.save(os.path.join(t.path, THEME_META_FILENAME))
        self.refresh()

    # ------------------------------------------------------------------
    def _install_files(self, paths: list):
        notes = []
        for path in paths:
            lower = path.lower()
            if not lower.endswith((".zip", ".tar.gz", ".tgz", ".tar")):
                notes.append(f"{os.path.basename(path)}: unsupported type (use .zip / .tar.gz / .tgz / .tar)")
                continue
            result = installer.install_theme_archive(path)
            notes.append(result.message)
            if not result.success:
                QMessageBox.warning(self, "Install failed", result.message)
        self.refresh()
        if notes:
            # Always surface what happened (including whether start.sh was generated)
            QMessageBox.information(self, "Install", "\n".join(notes))

    def _fill_monitor_combo(self):
        self.monitor_combo.blockSignals(True)
        self.monitor_combo.clear()
        for value, label in discovery.monitor_choices_for_ui():
            self.monitor_combo.addItem(label, value)
        self.monitor_combo.blockSignals(False)

    def _rescan_monitors(self):
        self._fill_monitor_combo()
        t = self._selected_theme()
        if t is not None:
            self._load_monitor_for_theme(t)

    def _load_monitor_for_theme(self, t):
        """Sync combo from theme.json monitor field."""
        mon = "auto"
        meta_path = os.path.join(t.path, THEME_META_FILENAME)
        if os.path.isfile(meta_path):
            try:
                mon = (ThemeMeta.load(meta_path).monitor or "auto").strip() or "auto"
            except Exception:
                mon = getattr(t.meta, "monitor", None) or "auto"
        else:
            mon = getattr(t.meta, "monitor", None) or "auto"
        self.monitor_combo.blockSignals(True)
        idx = self.monitor_combo.findData(mon)
        self.monitor_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.monitor_combo.blockSignals(False)

    def _on_monitor_changed(self, *_args):
        t = self._selected_theme()
        if t is None:
            return
        mon = self.monitor_combo.currentData()
        if mon is None:
            return
        mon = str(mon)
        meta_path = os.path.join(t.path, THEME_META_FILENAME)
        try:
            if os.path.isfile(meta_path):
                meta = ThemeMeta.load(meta_path)
            else:
                meta = ThemeMeta(
                    name=t.meta.name or os.path.basename(t.path),
                    author=t.meta.author or "",
                    description=t.meta.description or "",
                    resolution=t.meta.resolution or "",
                )
            meta.monitor = mon
            meta.save(meta_path)
            t.meta.monitor = mon
            t.has_theme_json = True
            self.generate_meta_btn.setVisible(False)
        except Exception as e:
            QMessageBox.warning(self, "Monitor pin", f"Could not save monitor pin: {e}")

    def _start_selected(self):
        t = self._selected_theme()
        if t:
            mon = self.monitor_combo.currentData()
            self.process_manager.start(t.path, monitor=str(mon) if mon else None)

    def _stop_selected(self):
        t = self._selected_theme()
        if t:
            self.process_manager.stop(t.path)

    def _on_state_changed(self, theme_path: str, running: bool):
        self.refresh()

    def _on_log_line(self, theme_path: str, line: str):
        pass  # surfaced via a future "logs" panel; kept quiet for now to avoid noisy popups

    def _open_folder_selected(self):
        t = self._selected_theme()
        if t:
            subprocess.Popen(["xdg-open", t.path])

    def _duplicate_selected(self):
        t = self._selected_theme()
        if not t:
            return
        name, ok = QInputDialog.getText(self, "Duplicate theme", "New name:", text=f"{t.meta.name} copy")
        if ok and name.strip():
            result = installer.duplicate_theme(t.path, name.strip())
            if not result.success:
                QMessageBox.warning(self, "Duplicate failed", result.message)
            self.refresh()

    def _export_selected(self):
        t = self._selected_theme()
        if not t:
            return
        out_path, _ = QFileDialog.getSaveFileName(self, "Export theme as", f"{t.meta.name}.zip", "Zip archive (*.zip)")
        if out_path:
            installer.export_theme_zip(t.path, out_path)

    def _uninstall_selected(self):
        t = self._selected_theme()
        if not t:
            return
        confirm = QMessageBox.question(self, "Uninstall theme", f"Delete '{t.meta.name}' permanently? This can't be undone.")
        if confirm == QMessageBox.StandardButton.Yes:
            self.process_manager.stop(t.path)
            installer.uninstall_theme(t.path)
            self.refresh()


