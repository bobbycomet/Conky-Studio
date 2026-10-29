"""
Left-hand dock: every registered node type, grouped into collapsible
category sections -- a full-width clickable header box, not a tiny
tree-branch triangle -- each holding a subcategory -> node tree, filtered
by the Simple/Complex toggle and a search box that matches across every
section at once and auto-expands whatever matched. Dragging a leaf item
onto the canvas creates a node there.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QLineEdit,
    QButtonGroup, QRadioButton, QHBoxLayout, QToolButton, QScrollArea, QSizePolicy,
    QFrame,
)
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter, QDrag
from PyQt6.QtCore import Qt, QMimeData, QByteArray, pyqtSignal

from conkystudio.theme import PALETTE
from conkystudio.nodes import registry
from conkystudio.ui.studio.node_canvas import NODE_MIME_TYPE

_CATEGORY_LABELS = [
    ("source", "Data Sources"), ("logic", "Logic"), ("visual", "Visuals"),
    ("canvas_ext", "Canvas Extensions"),
]
_NODE_TYPE_ROLE = Qt.ItemDataRole.UserRole


def _swatch_icon(hex_color: str) -> QIcon:
    pix = QPixmap(12, 12)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(hex_color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, 12, 12)
    p.end()
    return QIcon(pix)


class _DraggableTree(QTreeWidget):
    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None or item.data(0, _NODE_TYPE_ROLE) is None:
            return  # a subcategory header, not a draggable leaf
        node_type = item.data(0, _NODE_TYPE_ROLE)
        mime = QMimeData()
        mime.setData(NODE_MIME_TYPE, QByteArray(node_type.encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class _CollapsibleSection(QWidget):
    """A full-width clickable header that expands/collapses its body --
    a sleeker, easier-to-hit alternative to a QTreeWidget's tiny
    branch-arrow for a whole top-level category."""

    toggled = pyqtSignal(bool)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toggle_btn = QToolButton()
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(False)  # start collapsed; expand on click
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setStyleSheet(f"""
            QToolButton {{
                background: {PALETTE['raised']};
                border: 1px solid {PALETTE['border_strong']};
                border-radius: 6px;
                padding: 7px 10px;
                text-align: left;
                font-weight: 600;
                color: {PALETTE['text']};
            }}
            QToolButton:hover {{
                border-color: {PALETTE['teal']};
            }}
            QToolButton:checked {{
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }}
        """)
        self.toggle_btn.clicked.connect(self._on_clicked)
        layout.addWidget(self.toggle_btn)

        self.content = QWidget()
        self.content.setStyleSheet(
            f"background: {PALETTE['inset']}; border: 1px solid {PALETTE['border_strong']}; "
            f"border-top: none; border-bottom-left-radius: 6px; border-bottom-right-radius: 6px;"
        )
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(2, 2, 2, 2)
        self.content_layout.setSpacing(0)
        layout.addWidget(self.content)
        self.content.setVisible(False)  # matches start-collapsed header

    def _on_clicked(self):
        self.set_expanded(self.toggle_btn.isChecked())

    def set_expanded(self, expanded: bool):
        self.toggle_btn.setChecked(expanded)
        self.toggle_btn.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)
        self.toggled.emit(expanded)

    def is_expanded(self) -> bool:
        return self.toggle_btn.isChecked()

    def set_body(self, widget: QWidget):
        self.content_layout.addWidget(widget)


class PalettePanel(QWidget):
    node_type_activated = pyqtSignal(str)   # double-click -> add at a default canvas position

    def __init__(self, parent=None):
        super().__init__(parent)
        self._simple_mode = True
        self._sections: dict[str, _CollapsibleSection] = {}
        self._trees: dict[str, _DraggableTree] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        heading = QLabel("Nodes")
        heading.setProperty("role", "heading")
        layout.addWidget(heading)

        mode_row = QHBoxLayout()
        self.simple_radio = QRadioButton("Simple")
        self.complex_radio = QRadioButton("Complex")
        self.simple_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.simple_radio)
        group.addButton(self.complex_radio)
        self.simple_radio.toggled.connect(self._refresh)
        mode_row.addWidget(self.simple_radio)
        mode_row.addWidget(self.complex_radio)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search nodes\u2026")
        self.search.textChanged.connect(self._refresh)
        layout.addWidget(self.search)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._sections_container = QWidget()
        self._sections_layout = QVBoxLayout(self._sections_container)
        self._sections_layout.setContentsMargins(0, 0, 0, 0)
        self._sections_layout.setSpacing(6)
        self._sections_layout.addStretch(1)
        self.scroll.setWidget(self._sections_container)
        layout.addWidget(self.scroll, 1)

        for category, cat_label in _CATEGORY_LABELS:
            section = _CollapsibleSection(cat_label)
            tree = _DraggableTree()
            tree.setHeaderHidden(True)
            tree.setDragEnabled(True)
            tree.setIndentation(14)
            tree.setFrameShape(QTreeWidget.Shape.NoFrame)
            tree.itemDoubleClicked.connect(self._on_double_click)
            tree.itemExpanded.connect(lambda _it, t=tree: self._resize_tree_to_contents(t))
            tree.itemCollapsed.connect(lambda _it, t=tree: self._resize_tree_to_contents(t))
            section.set_body(tree)
            self._sections_layout.insertWidget(self._sections_layout.count() - 1, section)
            self._sections[category] = section
            self._trees[category] = tree

        hint = QLabel("Drag a node onto the canvas, or double-click to drop it in the middle. "
                       "Click a category header to expand or collapse it. Shift+click-drag on "
                       "empty canvas to box-select; plain drag pans.")
        hint.setProperty("role", "caption")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._refresh()

    def _refresh(self, *_args):
        self._simple_mode = self.simple_radio.isChecked()
        query = self.search.text().strip().lower()

        for category, cat_label in _CATEGORY_LABELS:
            section = self._sections[category]
            tree = self._trees[category]
            tree.clear()

            specs = registry.by_category(category)
            if self._simple_mode:
                specs = [s for s in specs if s.simple_mode]
            if query:
                specs = [s for s in specs if query in s.label.lower() or query in s.type.lower()
                          or query in s.subcategory.lower()]

            section.setVisible(bool(specs))
            if not specs:
                continue

            by_sub: dict[str, list] = {}
            for spec in specs:
                by_sub.setdefault(spec.subcategory or "Other", []).append(spec)

            # Alphabetical within every subcategory (built-ins + plugins).
            for subcat_key in by_sub:
                by_sub[subcat_key].sort(
                    key=lambda s: ((s.label or s.type or "").lower(), (s.type or "").lower())
                )

            # Prefer registry subcategory order, then any extra keys (e.g. Plugins)
            # sorted alphabetically so plugin packs still appear in a stable place.
            ordered_subcats = list(registry.subcategories_in(category))
            seen = set(ordered_subcats)
            extras = sorted(k for k in by_sub if k not in seen)
            ordered_subcats.extend(extras)

            for subcat in ordered_subcats:
                if subcat not in by_sub:
                    continue
                sub_item = QTreeWidgetItem([subcat])
                sub_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                sub_item.setForeground(0, QColor("#9aa2ad"))
                tree.addTopLevelItem(sub_item)
                for spec in by_sub[subcat]:
                    leaf = QTreeWidgetItem([spec.label])
                    leaf.setIcon(0, _swatch_icon(spec.color))
                    leaf.setData(0, _NODE_TYPE_ROLE, spec.type)
                    leaf.setToolTip(0, spec.description)
                    leaf.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled)
                    sub_item.addChild(leaf)
                sub_item.setExpanded(bool(query))  # collapsed by default; search expands matches

            # A hit expands its whole section so search results are
            # visible without an extra click; otherwise a section keeps
            # whatever open/closed state the user last left it in.
            if query:
                section.set_expanded(True)

            self._resize_tree_to_contents(tree)

    @staticmethod
    def _resize_tree_to_contents(tree: QTreeWidget):
        """Size each category tree to its visible rows, but CAP the height.

        Uncapped setFixedHeight() made the Nodes dock (and thus the whole
        main window) demand hundreds of pixels of vertical space. Qt then
        reported a large minimumSizeHint, so the resize cursor appeared but
        the window refused to shrink vertically.
        """
        row_h = tree.sizeHintForRow(0) if tree.topLevelItemCount() else 20
        row_h = row_h if row_h and row_h > 0 else 20

        def count_visible(item: QTreeWidgetItem) -> int:
            n = 1
            if item.isExpanded():
                for i in range(item.childCount()):
                    n += count_visible(item.child(i))
            return n

        rows = sum(count_visible(tree.topLevelItem(i)) for i in range(tree.topLevelItemCount()))
        content_h = rows * row_h + tree.frameWidth() * 2 + 4
        max_h = 220
        min_h = 48
        h = max(min_h, min(content_h, max_h))
        tree.setMinimumHeight(min_h)
        tree.setMaximumHeight(max_h)
        tree.setFixedHeight(h)
        tree.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if content_h > max_h
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def _on_double_click(self, item: QTreeWidgetItem, _column: int):
        node_type = item.data(0, _NODE_TYPE_ROLE)
        if node_type:
            self.node_type_activated.emit(node_type)

