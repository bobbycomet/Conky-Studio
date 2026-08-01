"""
The Studio tab: palette | canvas + preview | layers + property panel, all
as dockable QDockWidgets inside an embedded QMainWindow so users can
close, float, or re-tab any of them. A slim strip along the bottom lists
whichever docks are currently hidden, so hiding a dock never means
hunting through a menu to bring it back.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QMainWindow, QDockWidget, QLineEdit,
    QLabel, QPushButton, QTabWidget,
)
from PyQt6.QtCore import Qt, QPointF, pyqtSignal

from conkystudio.model.project import Project
from conkystudio.nodes.canvas import CANVAS_NODE_ID
from conkystudio.ui.studio.node_canvas import NodeCanvasScene, NodeCanvasView
from conkystudio.ui.studio.palette_panel import PalettePanel
from conkystudio.ui.studio.property_panel import PropertyPanel
from conkystudio.ui.studio.preview_panel import PreviewPanel
from conkystudio.ui.studio.layers_dock import LayersDock
from conkystudio.preview.live_preview import LivePreviewController


def _starter_project() -> Project:
    """What Project -> New HUD -> New actually opens: a couple of
    completely ordinary, freely-deletable nodes already wired together,
    so the first thing anyone sees is "oh, THAT'S how a wire works"
    rather than a blank canvas with one settings node on it."""
    from conkystudio.model.project import NodeInstance, new_id

    p = Project(name="Untitled HUD")
    p.ensure_canvas_node()
    cpu = p.add_node(NodeInstance(id=new_id("n"), type="source.cpu_percent", x=-360, y=-40))
    gauge = p.add_node(NodeInstance(id=new_id("n"), type="visual.arc_gauge", z=0, x=-40, y=-120,
                        props={"cx": 100, "cy": 100, "radius": 70, "value_suffix": "% CPU"}))
    label = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=1, x=-40, y=60,
                        props={"value": "Delete me, or drag more nodes in", "x": 10, "y": 200,
                               "font_size": 11, "color": "#5c636d"}))
    p.add_edge(cpu.id, gauge.id, "value")
    return p


class _HiddenDocksStrip(QWidget):
    """A slim bar along the bottom that only shows up once at least one
    dock is closed. Each hidden dock gets its own small toggle button
    here -- reopening a panel becomes "click its tab at the bottom"
    instead of hunting through a menu for it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._buttons: dict[QDockWidget, QPushButton] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)
        self._hint = QLabel("Hidden panels:")
        self._hint.setProperty("role", "caption")
        layout.addWidget(self._hint)
        layout.addStretch(1)
        self.setVisible(False)

    def register(self, dock: QDockWidget, label: str):
        btn = QPushButton(label)
        btn.setFixedHeight(22)
        btn.clicked.connect(lambda: self._reopen(dock))
        btn.setVisible(not dock.isVisible())
        self.layout().insertWidget(self.layout().count() - 1, btn)
        self._buttons[dock] = btn
        dock.visibilityChanged.connect(lambda visible, d=dock: self._on_visibility(d, visible))
        self._refresh()

    def _reopen(self, dock: QDockWidget):
        dock.setVisible(True)
        dock.raise_()

    def _on_visibility(self, dock: QDockWidget, visible: bool):
        btn = self._buttons.get(dock)
        if btn is not None:
            btn.setVisible(not visible)
        self._refresh()

    def _refresh(self):
        any_hidden = any(btn.isVisible() for btn in self._buttons.values())
        self.setVisible(any_hidden)


class StudioTab(QWidget):
    project_changed = pyqtSignal()

    def __init__(self, project: Project | None = None, parent=None):
        super().__init__(parent)
        self.project = project or _starter_project()
        self.project.ensure_canvas_node()
        self.preview_controller = LivePreviewController(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        name_bar = QHBoxLayout()
        name_bar.setContentsMargins(10, 8, 10, 0)
        name_bar.addWidget(QLabel("HUD name"))
        self.name_edit = QLineEdit(self.project.name)
        self.name_edit.setMaximumWidth(260)
        self.name_edit.editingFinished.connect(self._on_name_edited)
        name_bar.addWidget(self.name_edit)
        name_bar.addStretch(1)
        outer.addLayout(name_bar)

        # An embedded QMainWindow is what actually gives us real,
        # independent QDockWidgets here (closable, floatable into their
        # own window, tabify-able with each other) inside a single tab of
        # the app's outer QMainWindow -- a QSplitter can't do any of that.
        self.dock_host = QMainWindow()
        self.dock_host.setDockNestingEnabled(True)
        self.dock_host.setTabPosition(Qt.DockWidgetArea.RightDockWidgetArea, QTabWidget.TabPosition.North)
        outer.addWidget(self.dock_host, 1)

        self.hidden_strip = _HiddenDocksStrip()
        outer.addWidget(self.hidden_strip)

        # ---- central: canvas + preview ---------------------------------
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.scene = NodeCanvasScene(self.project)
        self.view = NodeCanvasView(self.scene)
        center_layout.addWidget(self.view, 1)

        self.preview_panel = PreviewPanel(self.preview_controller)
        self.preview_panel.set_project_getter(lambda: self.project)
        center_layout.addWidget(self.preview_panel)
        self.dock_host.setCentralWidget(center)

        # ---- docks -------------------------------------------------------
        self.palette = PalettePanel()
        self.palette.setMinimumWidth(230)
        self.palette.setMaximumWidth(340)
        self.palette_dock = self._make_dock("Nodes", self.palette, Qt.DockWidgetArea.LeftDockWidgetArea)

        self.layers_dock = LayersDock(self.project)
        self.layers_dock.setMinimumWidth(200)
        self.layers_dock.setMaximumWidth(300)
        self.layers_dock_widget = self._make_dock("Layers", self.layers_dock, Qt.DockWidgetArea.RightDockWidgetArea)

        self.property_panel = PropertyPanel(self.project)
        self.property_panel.setMinimumWidth(260)
        self.property_panel.setMaximumWidth(400)
        self.property_dock = self._make_dock("Properties", self.property_panel, Qt.DockWidgetArea.RightDockWidgetArea)

        self.dock_host.tabifyDockWidget(self.layers_dock_widget, self.property_dock)
        self.layers_dock_widget.raise_()

        # The Properties dock only earns screen space once something is
        # actually selected to edit -- it starts closed rather than
        # sitting there empty saying "Nothing selected".
        self.property_dock.hide()

        # ---- wiring --------------------------------------------------
        self.palette.node_type_activated.connect(self._add_node_center)
        self.view.node_type_dropped.connect(self._add_node_at)
        self.scene.node_selected.connect(self._on_node_selected)
        self.scene.graph_changed.connect(self._on_graph_changed)
        self.property_panel.changed.connect(self._on_graph_changed)
        self.property_panel.unbind_requested.connect(self._on_unbind)
        self.property_panel.label_changed.connect(self.scene.refresh_node_label)
        self.layers_dock.set_selection_callback(self._select_node_from_layers)
        self.layers_dock.layers_changed.connect(self._on_layers_changed)

    # ------------------------------------------------------------------
    def _make_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self.dock_host)
        dock.setObjectName(f"dock_{title.lower()}")
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.dock_host.addDockWidget(area, dock)
        self.hidden_strip.register(dock, title)
        # A floated dock becomes its own real top-level window rather
        # than a Qt::Tool popup, so it stays open and usable even if the
        # main Conky Studio window gets minimized.
        dock.topLevelChanged.connect(lambda floating, d=dock: self._on_dock_floated(d, floating))
        return dock

    @staticmethod
    def _on_dock_floated(dock: QDockWidget, floating: bool):
        if floating:
            dock.setWindowFlags(Qt.WindowType.Window)
            dock.show()

    def _on_node_selected(self, node_id: str):
        self.property_panel.show_node(node_id)
        self.layers_dock.select_node(node_id)
        if node_id:
            self.property_dock.setVisible(True)
            self.property_dock.raise_()
        # Selecting nothing deliberately does NOT auto-hide the dock --
        # if you pinned it open to compare a couple of nodes, clicking
        # empty canvas shouldn't yank it away mid-comparison.

    def _add_node_center(self, node_type: str):
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self.scene.add_node(node_type, center - QPointF(88, 40))

    def _add_node_at(self, node_type: str, scene_pos: QPointF):
        self.scene.add_node(node_type, scene_pos - QPointF(88, 20))

    def _on_unbind(self, node_id: str, prop_key: str):
        self.scene.disconnect_prop(node_id, prop_key)
        self.property_panel.show_node(node_id)

    def _select_node_from_layers(self, node_id: str):
        item = self.scene.node_items.get(node_id)
        if item is None:
            return
        self.scene.clearSelection()
        item.setSelected(True)
        self.property_panel.show_node(node_id)
        self.property_dock.setVisible(True)
        self.property_dock.raise_()

    def _on_layers_changed(self):
        for node_id in list(self.scene.node_items.keys()):
            self.scene.apply_lock_state(node_id)
        self._on_graph_changed()

    def _on_graph_changed(self):
        self.preview_panel.notify_graph_changed(self.project)
        self.layers_dock.refresh()
        self.project_changed.emit()

    def _on_name_edited(self):
        self.project.name = self.name_edit.text().strip() or "Untitled HUD"
        self._on_graph_changed()

    def load_project(self, project: Project):
        self.preview_controller.stop()
        self.project = project
        self.project.ensure_canvas_node()
        self.name_edit.setText(self.project.name)
        self.scene.project = self.project
        self.scene.rebuild_from_project()
        self.property_panel.project = self.project
        self.property_panel.show_node("")
        self.property_dock.hide()
        self.preview_panel.set_project_getter(lambda: self.project)
        self.layers_dock.project = self.project
        self.layers_dock.refresh()

    def new_project(self):
        self.load_project(_starter_project())

    def select_canvas_node(self):
        self.property_panel.show_node(CANVAS_NODE_ID)
        self.property_dock.setVisible(True)
        self.property_dock.raise_()
