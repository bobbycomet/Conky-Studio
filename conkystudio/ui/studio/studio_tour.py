"""
Interactive "Learn Studio" guided tour.

Help → Learn Studio constructs StudioTour(main_window, studio_tab) once and
calls .start() whenever the user wants a walkthrough. Safe to re-run.

Design note: we intentionally do NOT dim/black out the whole window. Full-
window translucent overlays with a "cut-out hole" fail on many Qt styles
(CompositionMode_Clear paints solid black over docks). Instead the tour
uses a floating card + a thin highlight ring drawn only around the target.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, QRect, QPoint, QTimer
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFrame,
    QTabWidget,
)


@dataclass
class _Step:
    title: str
    body: str
    # Optional callable returning a QWidget to highlight (or None).
    target: object = None  # () -> QWidget | None


class _HighlightRing(QWidget):
    """Thin blue ring around the target. Mouse-transparent, no dimming."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(56, 139, 253), 3)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 8, 8)
        # soft outer glow
        pen2 = QPen(QColor(56, 139, 253, 80), 6)
        p.setPen(pen2)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)
        p.end()


class _TourCard(QFrame):
    # Fixed width; height grows with wrapped body text via preferred_height().
    CARD_WIDTH = 400
    _H_MARGINS = 28  # left + right layout margins (14 each)
    _V_EXTRA = 44    # top/bottom margins + spacing between rows + buffer

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tourCard")
        self.setStyleSheet(
            "#tourCard {"
            "  background: #1c2128;"
            "  border: 1px solid #388bfd;"
            "  border-radius: 10px;"
            "}"
            "#tourCard QLabel[role='heading'] { color: #e6edf3; font-size: 14px; font-weight: 600; }"
            "#tourCard QLabel[role='body'] { color: #adbac7; font-size: 12px; }"
            "#tourCard QLabel[role='caption'] { color: #768390; font-size: 11px; }"
        )
        self.setFixedWidth(self.CARD_WIDTH)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        self.title = QLabel()
        self.title.setProperty("role", "heading")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.body = QLabel()
        self.body.setProperty("role", "body")
        self.body.setWordWrap(True)
        self.body.setMinimumHeight(48)
        lay.addWidget(self.body)
        self.progress = QLabel()
        self.progress.setProperty("role", "caption")
        lay.addWidget(self.progress)
        row = QHBoxLayout()
        self.back_btn = QPushButton("Back")
        self.skip_btn = QPushButton("Skip tour")
        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("primary")
        row.addWidget(self.back_btn)
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        row.addWidget(self.next_btn)
        lay.addLayout(row)

    def preferred_height(self) -> int:
        """Height that fits current title + fully wrapped body at CARD_WIDTH."""
        inner_w = self.CARD_WIDTH - self._H_MARGINS
        title_h = max(self.title.heightForWidth(inner_w), self.title.sizeHint().height())
        body_h = max(self.body.heightForWidth(inner_w), 48)
        prog_h = max(self.progress.sizeHint().height(), 16)
        btn_h = max(self.next_btn.sizeHint().height(), 28)
        return int(title_h + body_h + prog_h + btn_h + self._V_EXTRA)


class StudioTour:
    """Guided walkthrough of the Studio tab.

    API used by MainWindow:
        tour = StudioTour(main_window, studio_tab, parent=main_window)
        tour.start()
    """

    def __init__(self, main_window, studio_tab, parent=None):
        self.main = main_window
        self.studio = studio_tab
        self._parent = parent or main_window
        self._ring: _HighlightRing | None = None
        self._card: _TourCard | None = None
        self._index = 0
        self._steps: list[_Step] = []
        self._active = False

    def start(self):
        """Begin (or restart) the tour. Switches to the Studio tab first."""
        try:
            if hasattr(self.main, "tabs") and isinstance(self.main.tabs, QTabWidget):
                self.main.tabs.setCurrentWidget(self.studio)
        except Exception:
            pass

        self._build_steps()
        self._index = 0
        self._active = True
        self._ensure_ui()
        # Defer one tick so docks finish showing before we measure geometry
        QTimer.singleShot(30, self._show_step)

    def stop(self):
        self._active = False
        if self._ring is not None:
            self._ring.hide()
            self._ring.deleteLater()
            self._ring = None
        if self._card is not None:
            self._card.hide()
            self._card.deleteLater()
            self._card = None

    # ------------------------------------------------------------------
    def _build_steps(self):
        s = self.studio

        def _w(name: str):
            return lambda: getattr(s, name, None)

        self._steps = [
            _Step(
                "Welcome to the Studio",
                "Design Conky HUDs as a node graph. Each step points at one area. "
                "Press Next to continue, or Skip tour anytime. Panels stay fully visible — "
                "nothing is dimmed. For Wizard → Studio → Manager → Store in one pass, use "
                "Help → Take the Full Tour.",
                target=None,
            ),
            _Step(
                "Palette — Sources",
                "Sources are your data.\n"
                "• Native (teal): CPU %, RAM, disk, network, uptime, battery — Conky "
                "variables, no extra process.\n"
                "• Sensors (amber): CPU/GPU temp, GPU util, fan RPM, disk temp.\n"
                "• Weather / Media / Network / Custom: scripts (curl, playerctl, …).\n"
                "Palette subcategories group them (System, Sensors, Weather, Media, …).",
                target=_w("palette"),
            ),
            _Step(
                "Palette — Logic",
                "Logic sits between sources and visuals: Smooth (EMA), Hysteresis, "
                "Threshold, Math, Map Range, String Format, Enum Map, and more. Quiet "
                "noisy sensors, gate LEDs, or format text before a visual reads the value.",
                target=_w("palette"),
            ),
            _Step(
                "Palette — Visuals (overview)",
                "What appears on the desktop:\n"
                "• Gauges & Bars — arc, bar, needle, segmented, LED, reactor\n"
                "• Graphs — history, sparkline, multi-series, radar, top table, core strip\n"
                "• Text — labels, flip cards\n"
                "• Effects — glow, spiral, matrix rain, orbit, equalizer, fan, vinyl\n"
                "• Shapes / Icons / Advanced — rectangles, lines, weather icons, Custom Lua\n"
                "Overview only — open a node’s Properties help for detail.",
                target=_w("palette"),
            ),
            _Step(
                "Sensor poll mode: daemon vs execi",
                "GPU util, temps, and fan RPM are scripted sensors. Theme Wizard graphs "
                "default those to Simple (execi) so you can see stutter or blank values "
                "first-hand.\n\n"
                "For a smooth HUD: select each Sensors-subcategory source → Polling mode → "
                "Background daemon (zero-stutter). Daemon writes a cache from start.sh; "
                "Lua only reads and never blocks the draw.",
                target=_w("property_panel"),
            ),
            _Step(
                "Theme names — no spaces",
                "Names like “Minimal HUD” break install folders and start.sh lock files. "
                "Use hyphens: Minimal-HUD, reactor-core, my-desk.\n\n"
                "Rename before Build & Install. Spaces are a common first-run error — fix "
                "the name before treating a blank screen as a graphics bug.",
                target=None,
            ),
            _Step(
                "Canvas",
                "Wire outputs into inputs by dragging between ports. "
                "Data flows Source → (optional Logic) → Visual. "
                "Select a node to edit its properties on the right.",
                target=_w("view"),
            ),
            _Step(
                "Layers",
                "Reorder draw order, lock nodes, and jump to a node by clicking its row. "
                "Tabified with Properties and Windows on the right.",
                target=_w("layers_dock"),
            ),
            _Step(
                "Properties",
                "When a node is selected, its fields appear here — position, colours, "
                "poll mode, gradients, blend. Canvas / window geometry still lives on the "
                "Canvas node at the top of the graph.",
                target=_w("property_panel"),
            ),
            _Step(
                "Windows / Monitors",
                "Add extra Conky windows for multi-monitor layouts. "
                "Each window can pin to a different output (xrandr / wlr-randr). "
                "Single-monitor projects keep one auto window.",
                target=_w("windows_panel"),
            ),
            _Step(
                "Live Preview",
                "Start runs a real Conky process against a scratch build of your graph. "
                "Use the Window combo to preview a specific monitor conf when you have several.",
                target=_w("preview_panel"),
            ),
            _Step(
                "Position Stage",
                "Drag visual proxies on a plane the size of your Conky window to place them quickly. "
                "X/Y spinboxes in Properties remain for pixel-perfect tweaks. "
                "Snap and Fit help alignment. Live Preview can stay on while you drag; "
                "the HUD updates when you release the mouse.",
                target=_w("position_stage"),
            ),
            _Step(
                "Save project vs Build",
                "• Project → Save Project… writes a .json graph you can reopen and edit.\n"
                "• Project → Build to Folder… / Build & Install exports real Conky files "
                "(conky.conf, render.lua, scripts/, start.sh) under ~/.config/conky/<Name>.\n\n"
                "Save while learning. Build when you want Manager to Start the HUD. "
                "Re-building overwrites generated files from the current graph.",
                target=None,
            ),
            _Step(
                "You're set",
                "Re-open this tour anytime from Help → Learn Studio. "
                "For Theme Wizard + Manager + Store in one pass: Help → Take the Full Tour.",
                target=None,
            ),
        ]

    def _ensure_ui(self):
        host = self.main
        if self._ring is None:
            self._ring = _HighlightRing(host)
        if self._card is None:
            self._card = _TourCard(host)
            self._card.next_btn.clicked.connect(self._next)
            self._card.back_btn.clicked.connect(self._back)
            self._card.skip_btn.clicked.connect(self.stop)

    def _target_widget(self) -> QWidget | None:
        if not self._steps or self._index >= len(self._steps):
            return None
        step = self._steps[self._index]
        if step.target is None:
            return None
        try:
            w = step.target() if callable(step.target) else step.target
            return w if isinstance(w, QWidget) else None
        except Exception:
            return None

    def _global_rect(self, widget: QWidget) -> QRect:
        top_left = widget.mapTo(self.main, QPoint(0, 0))
        return QRect(top_left, widget.size())

    def _show_step(self):
        if not self._active or self._card is None:
            return
        if self._index < 0 or self._index >= len(self._steps):
            self.stop()
            return

        step = self._steps[self._index]
        self._card.title.setText(step.title)
        self._card.body.setText(step.body)
        self._card.progress.setText(f"Step {self._index + 1} of {len(self._steps)}")
        self._card.back_btn.setEnabled(self._index > 0)
        self._card.next_btn.setText("Finish" if self._index == len(self._steps) - 1 else "Next")

        # Raise relevant docks so highlights are visible
        try:
            if step.title.startswith("Layers") and hasattr(self.studio, "layers_dock_widget"):
                self.studio.layers_dock_widget.setVisible(True)
                self.studio.layers_dock_widget.raise_()
            elif step.title.startswith("Properties") and hasattr(self.studio, "property_dock"):
                self.studio.property_dock.setVisible(True)
                self.studio.property_dock.raise_()
            elif step.title.startswith("Windows") and hasattr(self.studio, "windows_dock"):
                self.studio.windows_dock.setVisible(True)
                self.studio.windows_dock.raise_()
            elif step.title.startswith("Live Preview") and hasattr(self.studio, "preview_dock"):
                self.studio.preview_dock.setVisible(True)
                self.studio.preview_dock.raise_()
            elif step.title.startswith("Position Stage") and hasattr(self.studio, "position_stage_dock"):
                self.studio.position_stage_dock.setVisible(True)
                self.studio.position_stage_dock.raise_()
        except Exception:
            pass

        target = self._target_widget()
        if self._ring is not None:
            if target is not None and target.isVisible():
                r = self._global_rect(target).adjusted(-4, -4, 4, 4)
                self._ring.setGeometry(r)
                self._ring.show()
                self._ring.raise_()
            else:
                self._ring.hide()

        self._position_card(target)
        self._card.show()
        self._card.raise_()

    def _position_card(self, target: QWidget | None):
        if self._card is None:
            return
        margin = 16
        card_w = self._card.CARD_WIDTH
        # Measure after text is set so the wrapped body is not clipped.
        inner_w = card_w - self._card._H_MARGINS
        self._card.body.setMinimumHeight(max(48, self._card.body.heightForWidth(inner_w)))
        card_h = max(self._card.preferred_height(), 160)
        host = self.main.rect()
        max_h = max(160, host.height() - 2 * margin)
        card_h = min(card_h, max_h)

        if target is not None and target.isVisible():
            tr = self._global_rect(target)
            x = tr.right() + margin
            y = tr.top()
            if x + card_w > host.right() - margin:
                x = tr.left() - card_w - margin
            if x < margin:
                x = max(margin, (host.width() - card_w) // 2)
                y = tr.bottom() + margin
            if y + card_h > host.bottom() - margin:
                y = max(margin, host.bottom() - card_h - margin)
            if y < margin:
                y = margin
        else:
            x = max(margin, (host.width() - card_w) // 2)
            y = max(margin, (host.height() - card_h) // 3)

        self._card.setGeometry(int(x), int(y), card_w, card_h)

    def _next(self):
        if self._index >= len(self._steps) - 1:
            self.stop()
            return
        self._index += 1
        self._show_step()

    def _back(self):
        if self._index <= 0:
            return
        self._index -= 1
        self._show_step()



