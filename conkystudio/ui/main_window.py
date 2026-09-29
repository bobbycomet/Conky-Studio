"""Top-level QMainWindow: menu bar + the three tabs."""
from __future__ import annotations

import os
import re
import zipfile

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QFileDialog, QMessageBox, QDialog, QVBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QInputDialog, QLineEdit, QHBoxLayout,
    QListWidget, QListWidgetItem, QComboBox, QFormLayout, QGroupBox,
    QDialogButtonBox, QWidget,
)
from PyQt6.QtGui import QAction, QGuiApplication
from PyQt6.QtCore import Qt, QDir, QTimer, QRect

from conkystudio.model.project import Project
from conkystudio.ui.manager_tab import ManagerTab
from conkystudio.ui.studio.studio_tab import StudioTab
from conkystudio.ui.store_tab import StoreTab
from conkystudio.codegen import builder
from conkystudio.hardware import discovery
from conkystudio.fonts import manager as font_manager
from conkystudio.plugins import loader as plugin_loader
from conkystudio.nodes import registry as node_registry
from conkystudio.ui.studio.theme_wizard import ThemeWizardDialog
from conkystudio.ui.studio.studio_tour import StudioTour
from conkystudio.ui.studio.guided_tour import GuidedTour
from conkystudio import update_checker

DEFAULT_INSTALL_ROOT = os.path.expanduser("~/.config/conky")
SUPPORT_DISCORD_URL = "https://discord.gg/kJZCZWg5nw"
SUPPORT_YOUTUBE_URL = "https://www.youtube.com/@BobbyComet"
NODE_VAULT_STORE_URL = "https://bobbycomet.github.io/Conky-Studio-Community-Plugins/#/"
WIKI_URL = "https://github.com/bobbycomet/Conky-Studio/wiki"


class PluginsDialog(QDialog):
    # Categories plugins may use -- display label -> registry category key.
    # "All" is handled separately (maps to None, no filter).
    _CATEGORY_FILTER_KEYS = {
        "Logic": "logic",
        "Visual": "visual",
        "Source": "source",
        "Canvas Ext": "canvas_ext",
    }
    _CATEGORY_FILTERS = ("All",) + tuple(_CATEGORY_FILTER_KEYS.keys())

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plugins")
        self.resize(620, 620)
        self._manifest = None
        self._installed_cache: list = []  # raw meta dicts, filtered on display
        self._fetch_cache: list = []      # PluginNode instances from last Fetch
        layout = QVBoxLayout(self)

        heading = QLabel("Plugins")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        warn = QLabel(
            "A plugin's Lua runs wherever you use it, inside Conky's own process -- the same trust "
            "level as installing a theme or script. Only load plugins from a source you trust. "
            "Installed plugins are saved under ~/.config/conky-studio/plugins/ and stay available "
            "across restarts and Fetch operations until you uninstall them."
        )
        warn.setProperty("role", "caption")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        installed_heading = QLabel("Installed")
        installed_heading.setProperty("role", "heading")
        layout.addWidget(installed_heading)

        installed_filter_row = QHBoxLayout()
        installed_filter_row.addWidget(QLabel("Category"))
        self.installed_category = QComboBox()
        for name in self._CATEGORY_FILTERS:
            self.installed_category.addItem(name)
        self.installed_category.setToolTip(
            "Show only installed plugins in this category (Logic / Visual / Source / Canvas Ext)"
        )
        self.installed_category.currentIndexChanged.connect(self._rebuild_installed_list)
        installed_filter_row.addWidget(self.installed_category)
        installed_filter_row.addStretch(1)
        layout.addLayout(installed_filter_row)

        self.installed_list = QListWidget()
        self.installed_list.setMinimumHeight(120)
        self.installed_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.installed_list, 1)

        installed_btn_row = QHBoxLayout()
        self.uninstall_btn = QPushButton("Uninstall")
        self.uninstall_btn.setToolTip(
            "Remove selected or checked plugins from this session and from disk "
            "(only items currently visible under the category filter are considered)"
        )
        self.uninstall_btn.clicked.connect(self._uninstall_selected)
        installed_btn_row.addWidget(self.uninstall_btn)
        installed_btn_row.addStretch(1)
        layout.addLayout(installed_btn_row)

        fetch_heading = QLabel("Fetch / install more")
        fetch_heading.setProperty("role", "heading")
        layout.addWidget(fetch_heading)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Manifest URL"))
        self.url_edit = QLineEdit(getattr(plugin_loader, "DEFAULT_PLUGINS_URL", ""))
        url_row.addWidget(self.url_edit, 1)
        fetch_btn = QPushButton("Fetch")
        fetch_btn.setObjectName("primary")
        fetch_btn.clicked.connect(self._fetch)
        url_row.addWidget(fetch_btn)
        visit_store_btn = QPushButton("Visit Store \u2197")
        visit_store_btn.setToolTip("Open the Node Vault website in your browser")
        visit_store_btn.clicked.connect(self._open_node_vault)
        url_row.addWidget(visit_store_btn)
        layout.addLayout(url_row)

        fetch_filter_row = QHBoxLayout()
        fetch_filter_row.addWidget(QLabel("Category"))
        self.fetch_category = QComboBox()
        for name in self._CATEGORY_FILTERS:
            self.fetch_category.addItem(name)
        self.fetch_category.setToolTip(
            "Show only catalogue plugins in this category before installing"
        )
        self.fetch_category.currentIndexChanged.connect(self._rebuild_fetch_list)
        fetch_filter_row.addWidget(self.fetch_category)
        fetch_filter_row.addStretch(1)
        layout.addLayout(fetch_filter_row)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        self.load_btn = QPushButton("Install Checked")
        self.load_btn.setObjectName("primary")
        self.load_btn.setEnabled(False)
        self.load_btn.setToolTip(
            "Install checked plugins from the list below "
            "(only the currently filtered category is shown)"
        )
        self.load_btn.clicked.connect(self._load_checked)
        btn_row.addWidget(self.load_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        try:
            self._refresh_installed()
        except Exception as e:
            self.installed_list.clear()
            self.installed_list.addItem("(could not list installed plugins: %s)" % e)
            self.uninstall_btn.setEnabled(False)

    def _open_node_vault(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(NODE_VAULT_STORE_URL))

    @staticmethod
    def _category_key(raw) -> str:
        return (str(raw or "")).strip().lower()

    def _filter_category_value(self, combo: QComboBox):
        """None = All; otherwise the registry category key (logic/visual/source/canvas_ext)."""
        text = (combo.currentText() or "All").strip()
        if text == "All":
            return None
        return self._CATEGORY_FILTER_KEYS.get(text, text.lower())

    def _refresh_installed(self):
        try:
            plugins = plugin_loader.loaded_plugins()
        except Exception as e:
            self._installed_cache = []
            self.installed_list.clear()
            item = QListWidgetItem("(error listing plugins: %s)" % e)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.installed_list.addItem(item)
            self.uninstall_btn.setEnabled(False)
            return
        # Alphabetical by label, then id
        self._installed_cache = sorted(
            [m for m in plugins if isinstance(m, dict)],
            key=lambda m: (
                (m.get("label") or m.get("id") or "").lower(),
                (m.get("id") or "").lower(),
            ),
        )
        self._rebuild_installed_list()

    def _rebuild_installed_list(self):
        self.installed_list.clear()
        cat = self._filter_category_value(self.installed_category)
        filtered = self._installed_cache
        if cat is not None:
            filtered = [
                m for m in self._installed_cache
                if self._category_key(m.get("category")) == cat
            ]
        if not filtered:
            if not self._installed_cache:
                msg = "(none installed yet)"
            else:
                msg = "(none in this category)"
            item = QListWidgetItem(msg)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.installed_list.addItem(item)
            self.uninstall_btn.setEnabled(False)
            return
        self.uninstall_btn.setEnabled(True)
        for meta in filtered:
            pid = meta.get("id") or ""
            label = "%s  (%s)  -  %s" % (
                meta.get("label", pid),
                meta.get("category", "?"),
                pid,
            )
            if meta.get("version"):
                label += "  v%s" % meta["version"]
            item = QListWidgetItem(label)
            item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, pid)
            tip = meta.get("description") or ""
            if meta.get("source"):
                tip = (tip + " | " if tip else "") + ("Source: %s" % meta["source"])
            if tip:
                item.setToolTip(tip)
            self.installed_list.addItem(item)

    def _uninstall_selected(self):
        ids = []
        for i in range(self.installed_list.count()):
            item = self.installed_list.item(i)
            pid = item.data(Qt.ItemDataRole.UserRole)
            if not pid:
                continue
            if item.checkState() == Qt.CheckState.Checked or item.isSelected():
                ids.append(pid)
        seen = set()
        ids = [x for x in ids if not (x in seen or seen.add(x))]
        if not ids:
            QMessageBox.information(
                self,
                "Plugins",
                "Select or check one or more installed plugins, then click Uninstall.",
            )
            return
        try:
            removed, errors = plugin_loader.uninstall_plugins(ids)
        except Exception as e:
            QMessageBox.warning(self, "Plugins", "Uninstall failed: %s" % e)
            return
        msg = ("Uninstalled: " + ", ".join(removed)) if removed else "Nothing uninstalled."
        if errors:
            msg += " | Errors: " + " ; ".join(errors)
        QMessageBox.information(self, "Plugins", msg)
        try:
            self._refresh_installed()
        except Exception:
            pass
        try:
            loaded = plugin_loader.loaded_plugin_ids()
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                plugin = item.data(Qt.ItemDataRole.UserRole)
                if plugin is None:
                    continue
                pid = getattr(plugin, "id", None)
                if pid and pid not in loaded:
                    item.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    item.setCheckState(Qt.CheckState.Checked)
                    item.setText("%s  (%s)" % (plugin.label, plugin.category))
        except Exception:
            pass

    def _fetch(self):
        self.list_widget.clear()
        self.load_btn.setEnabled(False)
        self._fetch_cache = []
        try:
            self._manifest = plugin_loader.fetch_manifest(self.url_edit.text().strip())
        except Exception as e:
            QMessageBox.warning(self, "Couldn't fetch plugins", str(e))
            return
        plugins = getattr(self._manifest, "plugins", None) or []
        if not plugins:
            self.list_widget.addItem("(manifest has no plugins listed yet)")
            return
        # Alphabetical by label, then id
        self._fetch_cache = sorted(
            list(plugins),
            key=lambda p: (
                (getattr(p, "label", None) or getattr(p, "id", "") or "").lower(),
                (getattr(p, "id", "") or "").lower(),
            ),
        )
        self._rebuild_fetch_list()

    def _rebuild_fetch_list(self):
        self.list_widget.clear()
        if not self._fetch_cache:
            if self._manifest is not None:
                self.list_widget.addItem("(manifest has no plugins listed yet)")
            self.load_btn.setEnabled(False)
            return
        try:
            loaded = plugin_loader.loaded_plugin_ids()
        except Exception:
            loaded = set()
        cat = self._filter_category_value(self.fetch_category)
        shown = 0
        for plugin in self._fetch_cache:
            try:
                pcat = self._category_key(getattr(plugin, "category", ""))
                if cat is not None and pcat != cat:
                    continue
                already = getattr(plugin, "id", None) in loaded
                label = "%s  (%s)" % (plugin.label, plugin.category)
                if already:
                    label += "  - already installed"
                item = QListWidgetItem(label)
                flags = (
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                if already:
                    flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
                item.setFlags(flags)
                item.setCheckState(
                    Qt.CheckState.Unchecked if already else Qt.CheckState.Checked
                )
                item.setData(Qt.ItemDataRole.UserRole, plugin)
                desc = getattr(plugin, "description", None)
                if desc:
                    item.setToolTip(desc)
                self.list_widget.addItem(item)
                shown += 1
            except Exception:
                continue
        if shown == 0:
            self.list_widget.addItem("(none in this category)")
            self.load_btn.setEnabled(False)
        else:
            self.load_btn.setEnabled(True)

    def _load_checked(self):
        loaded, errors = [], []
        loaded_nodes = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            plugin = item.data(Qt.ItemDataRole.UserRole)
            if plugin is None or item.checkState() != Qt.CheckState.Checked:
                continue
            try:
                plugin_loader.register_plugin(plugin)
                loaded.append(getattr(plugin, "label", getattr(plugin, "id", "?")))
                loaded_nodes.append(plugin)
            except Exception as e:
                errors.append(str(e))
        if loaded_nodes:
            try:
                src = ""
                if self._manifest is not None:
                    src = getattr(self._manifest, "source", "") or ""
                plugin_loader.persist_plugins(
                    loaded_nodes,
                    source=src or "plugins-dialog",
                )
                try:
                    ids = [getattr(p, "id", None) for p in loaded_nodes]
                    ids = [i for i in ids if i]
                    if ids and hasattr(plugin_loader, "clear_uninstalled"):
                        plugin_loader.clear_uninstalled(ids)
                except Exception:
                    pass
            except OSError as e:
                errors.append("Could not save plugins for next launch: %s" % e)
        msg = ("Installed: " + ", ".join(loaded)) if loaded else "Nothing installed."
        if errors:
            msg += " | Errors: " + " ; ".join(errors)
        QMessageBox.information(self, "Plugins", msg)
        try:
            self._refresh_installed()
        except Exception:
            pass
        if loaded:
            try:
                self._rebuild_fetch_list()
            except Exception:
                pass


class GettingStartedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Getting Started")
        self.resize(640, 560)
        layout = QVBoxLayout(self)

        heading = QLabel("Getting Started with Conky Studio")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText(_GETTING_STARTED_TEXT)
        layout.addWidget(body, 1)

        close = QPushButton("Close")
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        layout.addWidget(close)


class SupportDialog(QDialog):
    """Always available from Help → Support — not one-shot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Support")
        self.resize(480, 280)
        layout = QVBoxLayout(self)

        heading = QLabel("Support & guides")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        body = QLabel(
            "Get help, share HUDs, and watch video guides from the developer.\n\n"
            "These links stay available anytime under Help → Support."
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        discord_btn = QPushButton("Open Discord")
        discord_btn.setObjectName("primary")
        discord_btn.clicked.connect(lambda: self._open(SUPPORT_DISCORD_URL))
        layout.addWidget(discord_btn)

        yt_btn = QPushButton("Open YouTube (@BobbyComet)")
        yt_btn.clicked.connect(lambda: self._open(SUPPORT_YOUTUBE_URL))
        layout.addWidget(yt_btn)

        layout.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def _open(self, url: str):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))


class UpdateAvailableDialog(QDialog):
    """Shown when a newer release exists on GitHub -- reachable both from
    the silent startup check (only when there's actually something new)
    and from Help -> Check for Updates... ."""

    def __init__(self, result: "update_checker.UpdateCheckResult", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.resize(460, 220)
        self._download_url = result.download_url
        layout = QVBoxLayout(self)

        heading = QLabel("A new version of Conky Studio is available")
        heading.setProperty("role", "heading")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        body = QLabel(
            f"You have v{result.current_version}. "
            f"v{result.latest_version or '?'} is now available.\n\n"
            "Go to GitHub to get the new release, or if it is installed, use "
            "Griffin Updater to update to the new version."
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        layout.addStretch(1)

        github_btn = QPushButton("Open GitHub Release")
        github_btn.setObjectName("primary")
        github_btn.clicked.connect(self._open_github)
        layout.addWidget(github_btn)

        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def _open_github(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(self._download_url))


_GETTING_STARTED_TEXT = """Welcome to Conky Studio! You can build a live desktop HUD without writing a full theme by hand.


What You’re Building

Conky Studio lets you design a HUD using a visual node graph.
When you Build or use Live Preview, your design is turned into real Conky files (config, Lua, scripts) — the same files people used to write manually.

No mockups. No shortcuts. What you build is what runs.


The 3 Core Ideas

1. Sources — your data

These are values pulled from your system:

    * CPU %, GPU, RAM
    * Network speed
    * Weather
    * Custom scripts

Think of these as the *sensors* of your HUD.


2. Logic — optional processing

Use logic when raw values need adjustment:

    * Smooth jumpy values
    * Convert units (°F → °C)
    * Set thresholds (e.g. “above 80%”)
    * Build multi-step behaviors

If the number isn’t exactly what you want, Logic fixes it.


3. Visuals — what you see

These are what appear on screen:

    * Rings, bars, graphs
    * Text and icons
    * Effects (glow, pulse, radar, etc.)
    * Custom Lua for advanced drawing

This is your actual HUD.


How Nodes Connect

    * Each node is a box with input/output sockets
    * Drag from one socket to another to connect them
    * Data flows like this:

  Source → (optional Logic) → Visual

Examples:

CPU %       → Smooth → Ring
Weather °F  → Convert → Text

If nothing is connected, the value in the property panel is used instead.


Build Your First HUD (30–60 seconds)

    1. Go to the Studio tab
    2. Add a Source (e.g. CPU %)
    3. Add a Visual (e.g. Ring or Bar)
    4. Connect the Source to the Visual
    5. Move and style it using position, size, and color
    6. Click Start in Studio to preview then Build & Install

Alternatively, you can create a starter HUD by using the New HUD feature.

IMPORTANT NOTE: Change the name of the HUD before you build it out!
    * Keeping the name the same will make the manager think this is not a finished HUD.
    * If you launch it without the name change, you will have a blank screen.

That’s it; you’ve made a working widget.


Tabs Overview

    * Manager — Start/stop installed themes (`~/.config/conky/`)
    * Studio — Build and edit your HUD
    * Store — Community themes and assets (when available)


Important Note (Theme Launching)

If a theme appears in Manager but won’t start:

    * It must have a start.sh file
    * Use Import Custom to fix it
    * Then edit anything missing in Studio


Useful Menu Items

    * Project → New/Open/Save
    * Project → Build & Install — exports and adds to Manager
    * Project → Import Custom — imports Lua/sh/conf files as nodes
    * Tools → Plugins — install extra node packs (only trust known sources)
    * Tools → Hardware & Session — check system compatibility
    * Help → Getting Started: this guide


Images and Icons

    * Image/Icon nodes load files (PNG, etc.)
    * Can rotate or change based on triggers
    * Place assets in the theme’s `images/` folder when building

NOTE:

    * Imported themes using Custom Lua draw their own visuals
    * Image/Icon nodes do not control those automatically
    * Weather icons are drawn via Cairo, just move and resize them


If Something Looks Empty

    * Make sure Conky is installed and working
    * Ensure Build/Preview completed successfully
    * Scripts (weather, sensors) may need a moment to cache data
    * Check Tools → Hardware & Session for issues


Final Tip

You don’t need to learn everything at once.

Start with:
→ one Source
→ one Visual

Get that working, then expand.

That’s how you build everything.
"""


class HardwareDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hardware & Session")
        self.resize(560, 420)
        layout = QVBoxLayout(self)
        heading = QLabel("Hardware & Session Report")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        layout.addWidget(self.text, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self._run()

    def _run(self):
        # Structured session + hardware report (detection, severity, guidance).
        self.text.setPlainText(discovery.format_hardware_report())


def _safe_filename(name: str) -> str:
    """Turn a HUD name into a filesystem-safe filename stem (no extension).

    Strips characters that are illegal or awkward in filenames (path
    separators, quotes, etc.), collapses whitespace, and falls back to
    "hud" if nothing usable is left -- e.g. a name that's empty or is
    made up entirely of stripped characters.
    """
    cleaned = re.sub(r'[\\/:*?"<>|]+', "", name or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "hud"


class SaveProjectDialog(QDialog):
    """Shown on every Save Project.

    Lets the user edit manifest fields, attach font files when custom
    families are used, and choose the .cstudio destination. Skip writes a
    generic manifest and still packs imported images + project.json.
    """

    # result_mode: "save" | "skip" | None (cancel)
    def __init__(self, project: Project, suggested_path: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Project")
        self.setMinimumWidth(520)
        self.project = project
        self.result_mode: str | None = None
        self.font_files: list[str] = []
        self._suggested = suggested_path or (
            _safe_filename(project.name or "Untitled HUD") + ".cstudio"
        )

        root = QVBoxLayout(self)

        intro = QLabel(
            "Every save creates a portable .cstudio package (project graph + "
            "imported images + manifest). Fill in the package info below, or "
            "click Skip for a generic manifest."
        )
        intro.setWordWrap(True)
        intro.setProperty("role", "caption")
        root.addWidget(intro)

        # ---- Manifest fields ----------------------------------------------
        manifest_box = QGroupBox("Package manifest (manifest.json)")
        form = QFormLayout(manifest_box)

        self.name_edit = QLineEdit(project.name or "Untitled HUD")
        self.author_edit = QLineEdit(project.author or "")
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlainText(project.description or "")
        self.description_edit.setMaximumHeight(80)
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(
            "Optional notes for anyone who opens this package…"
        )
        self.notes_edit.setMaximumHeight(70)

        form.addRow("Name", self.name_edit)
        form.addRow("Author", self.author_edit)
        form.addRow("Description", self.description_edit)
        form.addRow("Notes", self.notes_edit)
        root.addWidget(manifest_box)

        # ---- Fonts --------------------------------------------------------
        font_box = QGroupBox("Fonts")
        font_layout = QVBoxLayout(font_box)
        uncommon = project.collect_uncommon_font_families()
        all_families = project.collect_font_families()
        if uncommon:
            font_layout.addWidget(QLabel(
                "This HUD uses custom font families that may be missing on "
                "other machines:"
            ))
            fam_label = QLabel("• " + "\n• ".join(uncommon))
            fam_label.setWordWrap(True)
            font_layout.addWidget(fam_label)
        elif all_families:
            font_layout.addWidget(QLabel(
                "Fonts used: " + ", ".join(all_families)
                + " (common system families — no files required)."
            ))
        else:
            font_layout.addWidget(QLabel("No font families set on nodes."))

        self.font_list = QListWidget()
        self.font_list.setMinimumHeight(60)
        font_layout.addWidget(self.font_list)

        font_btn_row = QHBoxLayout()
        add_font_btn = QPushButton("Add font files…")
        add_font_btn.setToolTip("Choose .ttf / .otf files to embed in the package")
        add_font_btn.clicked.connect(self._add_fonts)
        remove_font_btn = QPushButton("Remove selected")
        remove_font_btn.clicked.connect(self._remove_selected_fonts)
        font_btn_row.addWidget(add_font_btn)
        font_btn_row.addWidget(remove_font_btn)
        font_btn_row.addStretch(1)
        font_layout.addLayout(font_btn_row)
        root.addWidget(font_box)

        # ---- Destination --------------------------------------------------
        dest_box = QGroupBox("Save location")
        dest_layout = QHBoxLayout(dest_box)
        self.path_edit = QLineEdit(self._suggested)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_dest)
        dest_layout.addWidget(self.path_edit, 1)
        dest_layout.addWidget(browse_btn)
        root.addWidget(dest_box)

        # ---- Buttons: Save | Skip | Cancel --------------------------------
        buttons = QDialogButtonBox()
        self.save_btn = buttons.addButton("Save package", QDialogButtonBox.ButtonRole.AcceptRole)
        self.skip_btn = buttons.addButton("Skip", QDialogButtonBox.ButtonRole.ActionRole)
        self.cancel_btn = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.skip_btn.setToolTip(
            "Use a generic manifest.json; still saves project.json and imported images."
        )
        self.save_btn.clicked.connect(self._on_save)
        self.skip_btn.clicked.connect(self._on_skip)
        self.cancel_btn.clicked.connect(self.reject)
        root.addWidget(buttons)

    def _add_fonts(self):
        # Non-native dialog so we can show hidden dirs like ~/.fonts.
        start_dir = ""
        for candidate in (
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts"),
            os.path.expanduser("~"),
        ):
            if os.path.isdir(candidate):
                start_dir = candidate
                break

        dialog = QFileDialog(self, "Choose font files to include in the package", start_dir)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setNameFilters([
            "Fonts (*.ttf *.otf *.ttc *.woff *.woff2)",
            "All files (*)",
        ])
        # Native GTK/KDE dialogs often hide dotfolders; Qt dialog can show them.
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFilter(
            QDir.Filter.AllEntries
            | QDir.Filter.NoDotAndDotDot
            | QDir.Filter.AllDirs
            | QDir.Filter.Files
            | QDir.Filter.Hidden
        )
        if not dialog.exec():
            return
        for p in dialog.selectedFiles() or []:
            if p and p not in self.font_files:
                self.font_files.append(p)
                self.font_list.addItem(p)

    def _remove_selected_fonts(self):
        for item in self.font_list.selectedItems():
            path = item.text()
            if path in self.font_files:
                self.font_files.remove(path)
            row = self.font_list.row(item)
            self.font_list.takeItem(row)

    def _browse_dest(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Conky Studio project",
            self.path_edit.text() or self._suggested,
            "Conky Studio project (*.cstudio);;Legacy project JSON (*.json)",
        )
        if path:
            if not path.lower().endswith((".cstudio", ".json")):
                path = path + ".cstudio"
            self.path_edit.setText(path)

    def _resolved_path(self) -> str:
        path = (self.path_edit.text() or "").strip()
        if not path:
            path = self._suggested
        if not path.lower().endswith((".cstudio", ".json")):
            path = path + ".cstudio"
        return path

    def manifest_extra(self) -> dict:
        return {
            "name": self.name_edit.text().strip() or "Untitled HUD",
            "author": self.author_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "notes": self.notes_edit.toPlainText().strip(),
        }

    def _on_save(self):
        if not self._resolved_path():
            QMessageBox.warning(self, "Save Project", "Choose where to save the package.")
            return
        self.result_mode = "save"
        self.accept()

    def _on_skip(self):
        # Generic manifest; still need a destination.
        if not self._resolved_path():
            QMessageBox.warning(self, "Save Project", "Choose where to save the package.")
            return
        self.result_mode = "skip"
        self.accept()

    def destination_path(self) -> str:
        return self._resolved_path()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Conky Studio v{update_checker.APP_VERSION}")

        # Low floor so vertical resize always works. Child docks used to
        # inflate minimumSizeHint so the resize cursor appeared but height
        # would not shrink.
        self.setMinimumSize(640, 360)
        self._geometry_applied = False
        self._apply_initial_geometry()

        self.current_project_path: str | None = None
        # True after any canvas/property/window edit since last successful save
        # or project load. Used by closeEvent to offer Save now.
        self._project_dirty: bool = False

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.manager_tab = ManagerTab()
        self.studio_tab = StudioTab()
        self.store_tab = StoreTab()
        self.tabs.addTab(self.manager_tab, "Manager")
        self.tabs.addTab(self.studio_tab, "Studio")
        self.tabs.addTab(self.store_tab, "Store")

        self.studio_tab.project_changed.connect(self._on_project_edited)

        # Tours are reusable — Help menu can start them any time
        self._studio_tour = StudioTour(self, self.studio_tab, parent=self)
        self._guided_tour = GuidedTour(self, parent=self)

        self._build_menu()
        self._build_toolbar()
        # Re-register plugins persisted under ~/.config/conky-studio/plugins/
        try:
            # Only restore plugins the user installed (local packs). Remote
            # catalogue is fetched on demand via Tools → Plugins.
            plugin_loader.load_all(include_remote=False)
            self.studio_tab.palette._refresh()
        except Exception:
            pass
        self.statusBar().showMessage("Ready")

        # Silent -- only ever speaks up (via UpdateAvailableDialog) if a
        # newer release actually exists. Kept off the UI thread so a
        # slow/unreachable network never delays showing the window.
        self._update_worker: update_checker.UpdateCheckWorker | None = None
        self._check_for_updates(manual=False)

    def _apply_initial_geometry(self) -> None:
        """Size and center the window inside the available desktop area.

        Prefer a shorter default height so the title bar stays on-screen on
        common laptop displays. Never exceed ~75% of available height.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail: QRect = screen.availableGeometry()
        else:
            avail = QRect(0, 0, 1280, 720)

        margin = 64
        max_w = max(640, avail.width() - margin)
        max_h = max(360, avail.height() - margin)
        # Width can stay generous; height stays deliberately modest.
        w = min(1100, max_w)
        h = min(800, max_h, int(avail.height() * 0.95))
        w = min(w, avail.width())
        h = min(h, avail.height())
        h = max(h, 360)
        x = avail.x() + max(0, (avail.width() - w) // 2)
        y = avail.y() + max(0, (avail.height() - h) // 2)
        self.setGeometry(x, y, w, h)

    def minimumSizeHint(self):
        from PyQt6.QtCore import QSize
        # Override Qt's aggregated child hint so palette/dock content cannot
        # force a multi-hundred-pixel vertical floor.
        return QSize(640, 360)

    def showEvent(self, event):
        super().showEvent(event)
        # Re-apply once screens are fully known (AppImage / multi-monitor).
        if not self._geometry_applied:
            self._geometry_applied = True
            self._apply_initial_geometry()

    def _build_toolbar(self):
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        import_btn = QPushButton("Import Custom Files")
        import_btn.setToolTip(
            "Pick Lua / shell script / .conf / conkyrc files and import them as nodes."
        )
        import_btn.clicked.connect(self._import_custom_files)
        toolbar.addWidget(import_btn)

    def _build_menu(self):
        file_menu = self.menuBar().addMenu("&Project")

        new_action = QAction("New HUD\u2026", self)
        new_action.triggered.connect(self._new_project_wizard)
        file_menu.addAction(new_action)

        blank_action = QAction("New Blank HUD", self)
        blank_action.triggered.connect(self._new_project)
        file_menu.addAction(blank_action)

        open_action = QAction("Open Project\u2026", self)
        open_action.triggered.connect(self._open_project)
        file_menu.addAction(open_action)

        import_cstudio_action = QAction("Import .cstudio Project\u2026", self)
        import_cstudio_action.setToolTip(
            "Import a shared .cstudio (or .zip) package: unpack it, "
            "save a local .cstudio copy, and open it in Studio."
        )
        import_cstudio_action.triggered.connect(self._import_cstudio_project)
        file_menu.addAction(import_cstudio_action)

        save_action = QAction("Save Project\u2026", self)
        save_action.triggered.connect(self._save_project)
        file_menu.addAction(save_action)

        file_menu.addSeparator()

        build_action = QAction("Build to Folder\u2026", self)
        build_action.triggered.connect(self._build_to_folder)
        file_menu.addAction(build_action)

        install_action = QAction("Build && Install to Manager", self)
        install_action.triggered.connect(self._build_and_install)
        file_menu.addAction(install_action)

        file_menu.addSeparator()

        import_action = QAction("Import Custom Files\u2026", self)
        import_action.triggered.connect(self._import_custom_files)
        file_menu.addAction(import_action)
        self._import_custom_files_action = import_action

        tools_menu = self.menuBar().addMenu("&Tools")
        hw_action = QAction("Hardware && Session\u2026", self)
        hw_action.triggered.connect(lambda: HardwareDialog(self).exec())
        tools_menu.addAction(hw_action)

        font_action = QAction("Install Font\u2026", self)
        font_action.triggered.connect(self._install_font)
        tools_menu.addAction(font_action)

        plugins_action = QAction("Plugins\u2026", self)
        plugins_action.triggered.connect(self._open_plugins_dialog)
        tools_menu.addAction(plugins_action)

        plugin_create_action = QAction("Plugin Creation\u2026", self)
        plugin_create_action.setToolTip(
            "Author a logic / visual / source / canvas_ext plugin from the "
            "custom-node model: validate schema, export JSON, or install locally."
        )
        plugin_create_action.triggered.connect(self._open_plugin_creator)
        tools_menu.addAction(plugin_create_action)

        help_menu = self.menuBar().addMenu("&Help")
        start_action = QAction("Getting Started…", self)
        start_action.triggered.connect(self._open_getting_started)
        help_menu.addAction(start_action)

        full_tour_action = QAction("Take the Full Tour…", self)
        full_tour_action.setToolTip(
            "Theme Wizard (Minimal + Showcase) → Studio (nodes, sensors, naming) → "
            "Manager → Store. Recommended first run."
        )
        full_tour_action.triggered.connect(self._open_full_tour)
        help_menu.addAction(full_tour_action)

        tour_action = QAction("Learn Studio…", self)
        tour_action.setToolTip("Interactive guided tour of the Studio tab only (can be run anytime)")
        tour_action.triggered.connect(self._open_studio_tour)
        help_menu.addAction(tour_action)

        wizard_tour_action = QAction("Learn Theme Wizard…", self)
        wizard_tour_action.setToolTip(
            "Opens Theme Wizard already mid-tour, walking through category, resolution, "
            "panels, extras, and complexity (can be run anytime)"
        )
        wizard_tour_action.triggered.connect(self._open_theme_wizard_tour)
        help_menu.addAction(wizard_tour_action)

        support_action = QAction("Support…", self)
        support_action.setToolTip("Discord and YouTube links — always available")
        support_action.triggered.connect(self._open_support)
        help_menu.addAction(support_action)

        wiki_action = QAction("Wiki…", self)
        wiki_action.setToolTip("Open the Conky Studio GitHub wiki in your browser")
        wiki_action.triggered.connect(self._open_wiki)
        help_menu.addAction(wiki_action)

        help_menu.addSeparator()
        update_action = QAction("Check for Updates…", self)
        update_action.triggered.connect(lambda: self._check_for_updates(manual=True))
        help_menu.addAction(update_action)

    def _open_plugins_dialog(self):
        try:
            dialog = PluginsDialog(self)
            dialog.exec()
        except Exception as e:
            QMessageBox.warning(
                self, "Plugins", "Could not open Plugins dialog: %s" % e
            )
            return
        try:
            self.studio_tab.palette._refresh()
        except Exception:
            pass

    def _open_plugin_creator(self):
        try:
            from conkystudio.ui.plugin_creator import PluginCreatorDialog

            # Optional seed from currently selected Custom Lua / Custom Script
            seed = None
            node = None
            try:
                nid = getattr(self.studio_tab.property_panel, "node_id", "") or ""
                if nid:
                    node = self.studio_tab.project.node(nid)
                if node is not None:
                    ntype = getattr(node, "type", "")
                    props = getattr(node, "props", {}) or {}
                    if ntype == "visual.custom_lua":
                        seed = str(props.get("code") or "")
                    elif ntype == "source.custom_script":
                        seed = str(props.get("script_body") or "")
            except Exception:
                seed = None
                node = None

            dialog = PluginCreatorDialog(self, seed_from_custom_lua=seed)
            if seed and node is not None:
                ntype = getattr(node, "type", "")
                if ntype == "source.custom_script":
                    dialog.category_combo.setCurrentText("source")
                else:
                    dialog.category_combo.setCurrentText("visual")
                dialog._on_category_changed()
                dialog.body_edit.setPlainText(seed)

            dialog.exec()
            if getattr(dialog, "exported_path", None):
                self.statusBar().showMessage(f"Plugin: {dialog.exported_path}")
            try:
                self.studio_tab.palette._refresh()
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(
                self, "Plugin Creation", "Could not open Plugin Creation: %s" % e
            )

    def _open_getting_started(self):
        GettingStartedDialog(self).exec()

    def _open_full_tour(self):
        """Theme Wizard → Studio → Manager → Store. Safe to re-run anytime."""
        try:
            self._guided_tour.stop()
        except Exception:
            pass
        self._guided_tour.start()
        self.statusBar().showMessage(
            "Full tour — Wizard → Studio → Manager → Store (Help → Take the Full Tour to run again)"
        )

    def _open_studio_tour(self):
        """Always available — no one-shot flag; safe to run repeatedly."""
        self.tabs.setCurrentWidget(self.studio_tab)
        self._studio_tour.start()
        self.statusBar().showMessage("Learn Studio tour — Help → Learn Studio to run again anytime")

    def _open_theme_wizard_tour(self):
        """Opens a fresh Theme Wizard dialog and starts its tour immediately,
        instead of making the person open the wizard and click its own
        'Take the tour' button (which is gated behind picking a category —
        see ThemeWizardDialog._on_category_chosen). The dialog is otherwise
        the normal New HUD flow: Create still builds and loads a project the
        same way _new_project_wizard does."""
        if not self._confirm_unsaved_before_new():
            return
        dialog = ThemeWizardDialog(self)
        # start_tour() measures widget geometry, so it needs the dialog to
        # have actually laid out and painted first — deferred the same way
        # ThemeWizardTour.start() itself defers its first step. The timer
        # still fires once exec()'s nested event loop below starts spinning.
        QTimer.singleShot(50, dialog.start_tour)
        if dialog.exec() and dialog.result_project is not None:
            self.studio_tab.load_project(dialog.result_project)
            self.current_project_path = None
            self._mark_project_clean()
            self.tabs.setCurrentWidget(self.studio_tab)
            self.statusBar().showMessage(f"Created {dialog.result_project.name}")

    def _open_support(self):
        SupportDialog(self).exec()

    def _open_wiki(self):
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(WIKI_URL))

    def _check_for_updates(self, manual: bool):
        """manual=True (Help -> Check for Updates...) always reports a
        result, even "you're up to date" or a network error. manual=False
        (silent startup check) only ever shows anything when an update
        is actually available."""
        if self._update_worker is not None and self._update_worker.isRunning():
            if manual:
                self.statusBar().showMessage("Already checking for updates…")
            return
        if manual:
            self.statusBar().showMessage("Checking for updates…")
        worker = update_checker.UpdateCheckWorker(self)
        worker.finished_check.connect(lambda result: self._on_update_check_finished(result, manual))
        self._update_worker = worker
        worker.start()

    def _on_update_check_finished(self, result, manual: bool):
        if not result.checked_ok:
            self.statusBar().showMessage("Ready")
            if manual:
                QMessageBox.warning(
                    self, "Check for Updates",
                    f"Couldn't check for updates: {result.error}",
                )
            return

        if result.update_available:
            self.statusBar().showMessage(f"Update available: v{result.latest_version}")
            UpdateAvailableDialog(result, self).exec()
            return

        self.statusBar().showMessage("Ready")
        if manual:
            QMessageBox.information(
                self, "Check for Updates",
                f"You're up to date (v{result.current_version}).",
            )

    # ------------------------------------------------------------------
    def _confirm_unsaved_before_new(self) -> bool:
        """If the current HUD has unsaved edits, ask before replacing it.

        Returns True when it is OK to create/load a new project.
        """
        if not self._project_dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            "You have changes that have not been saved yet.\n"
            "Create new project?"
        )
        save_btn = box.addButton("Save now", QMessageBox.ButtonRole.AcceptRole)
        create_btn = box.addButton(
            "Yes, create new project", QMessageBox.ButtonRole.DestructiveRole
        )
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(save_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel_btn:
            return False
        if clicked is save_btn:
            return self._save_project()
        # Yes, create new project — discard unsaved work
        return clicked is create_btn

    def _new_project(self):
        if not self._confirm_unsaved_before_new():
            return
        self.studio_tab.new_project()
        self.current_project_path = None
        self._mark_project_clean()
        self.tabs.setCurrentWidget(self.studio_tab)
        self.statusBar().showMessage("New blank HUD created")

    def _new_project_wizard(self):
        if not self._confirm_unsaved_before_new():
            return
        dialog = ThemeWizardDialog(self)
        if dialog.exec() and dialog.result_project is not None:
            self.studio_tab.load_project(dialog.result_project)
            self.current_project_path = None
            self._mark_project_clean()
            self.tabs.setCurrentWidget(self.studio_tab)
            self.statusBar().showMessage(f"Created {dialog.result_project.name}")

    def _open_project(self):
        # Prefer .cstudio packages; legacy Hud.json / .json still openable.
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Conky Studio project",
            "",
            "Conky Studio project (*.cstudio);;Legacy project JSON (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            project = Project.load(path)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as e:
            QMessageBox.warning(self, "Couldn't open project", str(e))
            return
        self.studio_tab.load_project(project)
        # Save on a legacy .json will re-prompt for .cstudio so projects
        # move to the portable format.
        self.current_project_path = path
        self._mark_project_clean()
        self.tabs.setCurrentWidget(self.studio_tab)
        kind = "package" if path.lower().endswith((".cstudio", ".zip")) else "legacy JSON"
        self.statusBar().showMessage(f"Opened {os.path.basename(path)} ({kind})")

    def _import_cstudio_project(self):
        """Import a shared .cstudio / .zip package: unpack, save a local
        .cstudio copy wherever the user chooses, and open it in Studio.
        """
        src, _ = QFileDialog.getOpenFileName(
            self,
            "Import .cstudio project",
            "",
            "Conky Studio package (*.cstudio *.zip);;All files (*)",
        )
        if not src:
            return

        try:
            if src.lower().endswith(".cstudio"):
                project = Project.load(src)
            elif zipfile.is_zipfile(src):
                project = Project.load_package_from_zip(src)
            else:
                QMessageBox.warning(
                    self,
                    "Import failed",
                    "That file is not a .cstudio package or a zip archive.",
                )
                return
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as e:
            QMessageBox.warning(self, "Couldn't import package", str(e))
            return

        default_name = _safe_filename(project.name or "Imported HUD") + ".cstudio"
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Save imported project as",
            default_name,
            "Conky Studio project (*.cstudio)",
        )
        if not dest:
            return
        if not dest.lower().endswith(".cstudio"):
            dest = dest + ".cstudio"

        try:
            warnings = project.save_package(dest)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Couldn't save imported project", str(e))
            return

        self.studio_tab.load_project(project)
        self.current_project_path = dest
        self._mark_project_clean()
        self.tabs.setCurrentWidget(self.studio_tab)
        msg = f"Imported {os.path.basename(src)} → {os.path.basename(dest)}"
        if warnings:
            QMessageBox.warning(
                self,
                "Imported with warnings",
                msg + "\n\n" + "\n".join(f"• {w}" for w in warnings[:12]),
            )
        self.statusBar().showMessage(msg)

    def _on_project_edited(self):
        self._project_dirty = True

    def _mark_project_clean(self):
        self._project_dirty = False

    def _save_project(self) -> bool:
        """Always show the Save Project form, then write a .cstudio package.

        Save package — user-edited manifest + optional font files + images.
        Skip — generic manifest.json; still packs project.json and images.
        Cancel — abort.

        Returns True if the project was saved successfully, False if the user
        cancelled or the write failed.
        """
        project = self.studio_tab.project
        suggested = self.current_project_path or ""
        if not suggested or not suggested.lower().endswith(".cstudio"):
            suggested = _safe_filename(project.name or "Untitled HUD") + ".cstudio"

        dialog = SaveProjectDialog(project, suggested_path=suggested, parent=self)
        if not dialog.exec() or not dialog.result_mode:
            return False

        path = dialog.destination_path()
        if path.lower().endswith(".json") and not path.lower().endswith(".cstudio"):
            # Legacy JSON escape hatch from Browse — no package form data.
            try:
                project.save_legacy_json(path)
            except OSError as e:
                QMessageBox.warning(self, "Couldn't save project", str(e))
                return False
            self.current_project_path = path
            self._mark_project_clean()
            self.statusBar().showMessage(f"Saved {os.path.basename(path)} (legacy JSON)")
            return True

        if not path.lower().endswith(".cstudio"):
            path = path + ".cstudio"

        generic = dialog.result_mode == "skip"
        extra_fonts = [] if generic else list(dialog.font_files or [])
        manifest_extra = None if generic else dialog.manifest_extra()

        # Apply identity fields to the in-memory project before pack (Save path).
        if not generic and manifest_extra:
            project.name = manifest_extra.get("name") or project.name
            project.author = manifest_extra.get("author") or ""
            project.description = manifest_extra.get("description") or ""

        try:
            warnings = project.save(
                path,
                extra_font_files=extra_fonts or None,
                manifest_extra=manifest_extra,
                generic_manifest=generic,
            )
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Couldn't save project", str(e))
            return False

        self.current_project_path = path
        self._mark_project_clean()
        kind = "generic manifest" if generic else "package"
        msg = f"Saved {os.path.basename(path)} ({kind})"
        if warnings:
            msg += f" — {len(warnings)} warning(s)"
            QMessageBox.warning(
                self,
                "Saved with warnings",
                msg + "\n\n" + "\n".join(f"• {w}" for w in warnings[:12]),
            )
        self.statusBar().showMessage(msg)
        return True

    def _build_to_folder(self):
        out_dir = QFileDialog.getExistingDirectory(self, "Build into folder")
        if not out_dir:
            return
        project = self.studio_tab.project
        target = os.path.join(out_dir, project.name)
        result = builder.build_project(
            project, target, source_search_dirs=project.search_dirs() or None,
        )
        msg = f"Built to {result.output_dir}"
        if result.warnings:
            msg += f"\n\n{len(result.warnings)} warning(s):\n" + "\n".join(f"\u2022 {w}" for w in result.warnings)
        QMessageBox.information(self, "Build complete", msg)

    def _build_and_install(self):
        project = self.studio_tab.project
        target = os.path.join(DEFAULT_INSTALL_ROOT, project.name)
        result = builder.build_project(
            project, target, source_search_dirs=project.search_dirs() or None,
        )
        msg = f"Installed to {result.output_dir}\n\nSwitch to the Manager tab to launch it."
        if result.warnings:
            msg += f"\n\n{len(result.warnings)} warning(s):\n" + "\n".join(f"\u2022 {w}" for w in result.warnings)
        QMessageBox.information(self, "Build complete", msg)
        self.manager_tab.refresh()

    def _import_custom_files(self):
        """Import a hand-picked set of Lua / sh / conf / conkyrc files into a
        Studio project, then build/install. Unlike the old whole-theme-folder
        importer, this works on individual files: pick just the ones you
        want (or select every file in a folder at once, most file dialogs
        support that) and each gets classified into the node it fits --
        Custom Lua for Cairo draw hooks, Custom Script for shell scripts
        (or a matching built-in source when the name is recognised), and
        the first .conf/conkyrc gets the full canvas + TEXT treatment.
        Python and other non-shell/Lua/Conky files are skipped, never
        guessed at."""
        import traceback
        from conkystudio.importer.legacy_parser import import_custom_files

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose Lua / shell script / conf / conkyrc files to import",
            "",
            "Conky Studio importable (*.lua *.sh *.bash *.conf conkyrc *);;All files (*)",
        )
        if not paths:
            return
        # Search every folder the selected files came from at build time
        # (companion scripts/images referenced by path may live alongside
        # a file picked from a different folder than the .conf/.lua).
        search_dirs = list(dict.fromkeys(os.path.dirname(p) or "." for p in paths))

        try:
            result = import_custom_files(paths)
        except FileNotFoundError as e:
            QMessageBox.warning(self, "Import failed", str(e))
            return
        except Exception as e:
            QMessageBox.critical(
                self, "Import crashed",
                f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}",
            )
            return

        try:
            self.studio_tab.load_project(result.project)
            self.current_project_path = None
            self._mark_project_clean()
            self.tabs.setCurrentWidget(self.studio_tab)
        except Exception as e:
            QMessageBox.critical(
                self, "Import loaded but canvas failed",
                f"The project was parsed ({len(result.project.nodes)} nodes) but Studio "
                f"could not display it:\n\n{type(e).__name__}: {e}\n\n{traceback.format_exc()}",
            )
            return

        # Build + install so Manager can Start it. Sanitize the folder name.
        try:
            safe_name = "".join(
                c if (c.isalnum() or c in "-_.") else "_"
                for c in (result.project.name or "imported")
            ).strip("_") or "imported"
            target = os.path.join(DEFAULT_INSTALL_ROOT, safe_name)
            os.makedirs(DEFAULT_INSTALL_ROOT, exist_ok=True)
            build = builder.build_project(
                result.project, target, source_search_dirs=search_dirs,
            )
            try:
                self.manager_tab.refresh()
            except Exception:
                pass

            msg = (
                f"Imported {len(result.project.nodes)} node(s) from {len(paths)} file(s).\n\n"
                f"This is semantic extraction, not a pixel-perfect recreation — expect to "
                f"reposition things. Unrecognised bits became Custom Script or Custom Lua nodes.\n\n"
                f"Installed to {build.output_dir}\n"
                f"Switch to the Manager tab and hit Start to launch it."
            )
            if result.warnings:
                msg += f"\n\n{len(result.warnings)} import note(s):\n" + "\n".join(
                    f"• {w}" for w in result.warnings[:15]
                )
                if len(result.warnings) > 15:
                    msg += f"\n…and {len(result.warnings) - 15} more."
            if getattr(build, "warnings", None):
                msg += f"\n\n{len(build.warnings)} build warning(s):\n" + "\n".join(
                    f"• {w}" for w in build.warnings[:10]
                )
            QMessageBox.information(self, "Import complete", msg)
        except Exception as e:
            QMessageBox.critical(
                self, "Import partially succeeded",
                f"The theme is open in Studio, but Build/Install failed:\n\n"
                f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}",
            )

    def _install_font(self):
        start_dir = ""
        for candidate in (
            os.path.expanduser("~/.fonts"),
            os.path.expanduser("~/.local/share/fonts"),
            os.path.expanduser("~"),
        ):
            if os.path.isdir(candidate):
                start_dir = candidate
                break
        dialog = QFileDialog(self, "Choose a font file", start_dir)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setNameFilters(["Fonts (*.ttf *.otf *.ttc)", "All files (*)"])
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFilter(
            QDir.Filter.AllEntries
            | QDir.Filter.NoDotAndDotDot
            | QDir.Filter.AllDirs
            | QDir.Filter.Files
            | QDir.Filter.Hidden
        )
        if not dialog.exec():
            return
        selected = dialog.selectedFiles()
        if not selected:
            return
        path = selected[0]
        result = font_manager.install_font(path)
        if result.success:
            self.studio_tab.property_panel.invalidate_font_cache()
            QMessageBox.information(self, "Font installed", result.message)
        else:
            QMessageBox.warning(self, "Font install failed", result.message)

    def closeEvent(self, event):
        if self._project_dirty:
            if self.current_project_path:
                text = (
                    "You have made changes since your last save.\n"
                    "Do you want to save now?"
                )
            else:
                text = (
                    "You have not saved your project.\n"
                    "All progress will be lost if you exit.\n\n"
                    "Save now?"
                )
            box = QMessageBox(self)
            box.setWindowTitle("Unsaved changes")
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(text)
            save_btn = box.addButton("Save now", QMessageBox.ButtonRole.AcceptRole)
            exit_btn = box.addButton("Continue to exit", QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(save_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked is cancel_btn:
                event.ignore()
                return
            if clicked is save_btn:
                if not self._save_project():
                    # User cancelled the save form or save failed — stay open.
                    event.ignore()
                    return
            # Continue to exit (or successful save) falls through to cleanup.

        # Only clean up the live Studio preview. Themes started from the
        # Manager are independent process trees (setsid + lock-file). Detach
        # their QProcess handles so Qt does not terminate them on shutdown.
        self.studio_tab.preview_controller.cleanup()
        self.manager_tab.process_manager.detach_all()
        if self._update_worker is not None and self._update_worker.isRunning():
            self._update_worker.wait(2000)
        super().closeEvent(event)

