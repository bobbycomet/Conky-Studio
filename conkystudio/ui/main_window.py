"""Top-level QMainWindow: menu bar + the three tabs."""
from __future__ import annotations

import os

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QFileDialog, QMessageBox, QDialog, QVBoxLayout,
    QLabel, QPlainTextEdit, QPushButton, QInputDialog, QLineEdit, QHBoxLayout,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QDir

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
from conkystudio import update_checker

DEFAULT_INSTALL_ROOT = os.path.expanduser("~/.config/conky")
SUPPORT_DISCORD_URL = "https://discord.gg/kJZCZWg5nw"
SUPPORT_YOUTUBE_URL = "https://www.youtube.com/@BobbyComet"


class PluginsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Plugins")
        self.resize(620, 560)
        self._manifest = None
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
        self.installed_list = QListWidget()
        self.installed_list.setMinimumHeight(120)
        self.installed_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self.installed_list, 1)

        installed_btn_row = QHBoxLayout()
        self.uninstall_btn = QPushButton("Uninstall")
        self.uninstall_btn.setToolTip(
            "Remove selected or checked plugins from this session and from disk"
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
        layout.addLayout(url_row)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        self.load_btn = QPushButton("Install Checked")
        self.load_btn.setObjectName("primary")
        self.load_btn.setEnabled(False)
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

    def _refresh_installed(self):
        self.installed_list.clear()
        try:
            plugins = plugin_loader.loaded_plugins()
        except Exception as e:
            item = QListWidgetItem("(error listing plugins: %s)" % e)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.installed_list.addItem(item)
            self.uninstall_btn.setEnabled(False)
            return
        if not plugins:
            item = QListWidgetItem("(none installed yet)")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.installed_list.addItem(item)
            self.uninstall_btn.setEnabled(False)
            return
        self.uninstall_btn.setEnabled(True)
        for meta in plugins:
            if not isinstance(meta, dict):
                continue
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
        try:
            self._manifest = plugin_loader.fetch_manifest(self.url_edit.text().strip())
        except Exception as e:
            QMessageBox.warning(self, "Couldn't fetch plugins", str(e))
            return
        plugins = getattr(self._manifest, "plugins", None) or []
        if not plugins:
            self.list_widget.addItem("(manifest has no plugins listed yet)")
            return
        try:
            loaded = plugin_loader.loaded_plugin_ids()
        except Exception:
            loaded = set()
        for plugin in plugins:
            try:
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
            except Exception:
                continue
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
                loaded_ids = plugin_loader.loaded_plugin_ids()
                for i in range(self.list_widget.count()):
                    item = self.list_widget.item(i)
                    plugin = item.data(Qt.ItemDataRole.UserRole)
                    if plugin is None:
                        continue
                    if getattr(plugin, "id", None) in loaded_ids:
                        item.setText(
                            "%s  (%s)  - already installed"
                            % (plugin.label, plugin.category)
                        )
                        item.setCheckState(Qt.CheckState.Unchecked)
                        item.setFlags(
                            Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsUserCheckable
                        )
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
    * Use Import Legacy Theme to fix it
    * Then edit anything missing in Studio


Useful Menu Items

    * Project → New/Open/Save
    * Project → Build & Install — exports and adds to Manager
    * Project → Import Legacy Theme — converts old themes into nodes
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Conky Studio v{update_checker.APP_VERSION}")
        self.resize(1280, 820)

        self.current_project_path: str | None = None

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.manager_tab = ManagerTab()
        self.studio_tab = StudioTab()
        self.store_tab = StoreTab()
        self.tabs.addTab(self.manager_tab, "Manager")
        self.tabs.addTab(self.studio_tab, "Studio")
        self.tabs.addTab(self.store_tab, "Store")

        # Tour is reusable — Help → Learn Studio can start it any time
        self._studio_tour = StudioTour(self, self.studio_tab, parent=self)

        self._build_menu()
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

        import_action = QAction("Import Legacy Theme\u2026", self)
        import_action.triggered.connect(self._import_legacy_theme)
        file_menu.addAction(import_action)

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

        help_menu = self.menuBar().addMenu("&Help")
        start_action = QAction("Getting Started…", self)
        start_action.triggered.connect(self._open_getting_started)
        help_menu.addAction(start_action)

        tour_action = QAction("Learn Studio…", self)
        tour_action.setToolTip("Interactive guided tour of the Studio tab (can be run anytime)")
        tour_action.triggered.connect(self._open_studio_tour)
        help_menu.addAction(tour_action)

        support_action = QAction("Support…", self)
        support_action.setToolTip("Discord and YouTube links — always available")
        support_action.triggered.connect(self._open_support)
        help_menu.addAction(support_action)

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


    def _open_getting_started(self):
        GettingStartedDialog(self).exec()

    def _open_studio_tour(self):
        """Always available — no one-shot flag; safe to run repeatedly."""
        self.tabs.setCurrentWidget(self.studio_tab)
        self._studio_tour.start()
        self.statusBar().showMessage("Learn Studio tour — Help → Learn Studio to run again anytime")

    def _open_support(self):
        SupportDialog(self).exec()

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
    def _new_project(self):
        self.studio_tab.new_project()
        self.current_project_path = None
        self.tabs.setCurrentWidget(self.studio_tab)
        self.statusBar().showMessage("New blank HUD created")

    def _new_project_wizard(self):
        dialog = ThemeWizardDialog(self)
        if dialog.exec() and dialog.result_project is not None:
            self.studio_tab.load_project(dialog.result_project)
            self.current_project_path = None
            self.tabs.setCurrentWidget(self.studio_tab)
            self.statusBar().showMessage(f"Created {dialog.result_project.name}")

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Conky Studio project", "", "Conky Studio project (*.json)")
        if not path:
            return
        try:
            project = Project.load(path)
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, "Couldn't open project", str(e))
            return
        self.studio_tab.load_project(project)
        self.current_project_path = path
        self.tabs.setCurrentWidget(self.studio_tab)
        self.statusBar().showMessage(f"Opened {os.path.basename(path)}")

    def _save_project(self):
        path = self.current_project_path
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Save Conky Studio project", "hud.json", "Conky Studio project (*.json)")
            if not path:
                return
        self.studio_tab.project.save(path)
        self.current_project_path = path
        self.statusBar().showMessage(f"Saved {os.path.basename(path)}")

    def _build_to_folder(self):
        out_dir = QFileDialog.getExistingDirectory(self, "Build into folder")
        if not out_dir:
            return
        target = os.path.join(out_dir, self.studio_tab.project.name)
        result = builder.build_project(self.studio_tab.project, target)
        msg = f"Built to {result.output_dir}"
        if result.warnings:
            msg += f"\n\n{len(result.warnings)} warning(s):\n" + "\n".join(f"\u2022 {w}" for w in result.warnings)
        QMessageBox.information(self, "Build complete", msg)

    def _build_and_install(self):
        project = self.studio_tab.project
        target = os.path.join(DEFAULT_INSTALL_ROOT, project.name)
        result = builder.build_project(project, target)
        msg = f"Installed to {result.output_dir}\n\nSwitch to the Manager tab to launch it."
        if result.warnings:
            msg += f"\n\n{len(result.warnings)} warning(s):\n" + "\n".join(f"\u2022 {w}" for w in result.warnings)
        QMessageBox.information(self, "Build complete", msg)
        self.manager_tab.refresh()

    def _import_legacy_theme(self):
        """Import a folder of classic Conky files into a Studio project, then build/install."""
        import traceback
        from conkystudio.importer.legacy_parser import import_legacy_theme

        # Directory picker that still *lists* files + hidden entries so you can
        # see conky.conf / .lua / scripts while choosing the theme folder.
        # Do NOT call setFilter(dialog.filter() | …): on some PyQt6 builds
        # filter() is a name-filter string and that bitwise OR TypeErrors.
        theme_dir = ""
        try:
            dialog = QFileDialog(self, "Choose a legacy theme folder (containing a .conf file)")
            dialog.setFileMode(QFileDialog.FileMode.Directory)
            # Show files in the list (not directories-only), but Accept still returns a dir.
            dialog.setOption(QFileDialog.Option.ShowDirsOnly, False)
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
            dialog.setOption(QFileDialog.Option.ReadOnly, True)
            # QDir filters only — never OR with dialog.filter() / name filters.
            dialog.setFilter(
                QDir.Filter.AllEntries
                | QDir.Filter.Hidden
                | QDir.Filter.AllDirs
                | QDir.Filter.NoDot
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected = dialog.selectedFiles()
                if selected:
                    theme_dir = selected[0]
        except Exception as e:
            QMessageBox.critical(
                self, "Import dialog failed",
                f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}",
            )
            return
        if not theme_dir:
            theme_dir = QFileDialog.getExistingDirectory(
                self, "Choose a legacy theme folder (containing a .conf file)",
            )
        if not theme_dir:
            return

        # If the user highlighted a file, use its parent directory as the theme root.
        if os.path.isfile(theme_dir):
            theme_dir = os.path.dirname(theme_dir) or theme_dir

        try:
            result = import_legacy_theme(theme_dir)
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
                result.project, target, source_search_dirs=[theme_dir],
            )
            try:
                self.manager_tab.refresh()
            except Exception:
                pass

            msg = (
                f"Imported {len(result.project.nodes)} node(s) from {os.path.basename(theme_dir)}.\n\n"
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
        path, _ = QFileDialog.getOpenFileName(self, "Choose a font file", "", "Fonts (*.ttf *.otf *.ttc)")
        if not path:
            return
        result = font_manager.install_font(path)
        if result.success:
            self.studio_tab.property_panel.invalidate_font_cache()
            QMessageBox.information(self, "Font installed", result.message)
        else:
            QMessageBox.warning(self, "Font install failed", result.message)

    def closeEvent(self, event):
        # Only clean up the live Studio preview. Themes started from the
        # Manager are independent process trees (setsid + lock-file). Detach
        # their QProcess handles so Qt does not terminate them on shutdown.
        self.studio_tab.preview_controller.cleanup()
        self.manager_tab.process_manager.detach_all()
        if self._update_worker is not None and self._update_worker.isRunning():
            self._update_worker.wait(2000)
        super().closeEvent(event)
