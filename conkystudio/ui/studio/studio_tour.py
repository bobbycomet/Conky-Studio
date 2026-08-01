"""Interactive 'Learn Studio' guided tour — always available from Help.

Dimmed overlay with a *transparent hole* over the target widget so the
highlight stays visible (not blacked out). Step card is scrollable and
can be launched any number of times.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, QEvent
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QRegion
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy,
)


@dataclass
class TourStep:
    title: str
    body: str
    # Callable returning a QWidget to spotlight, or None for centered intro/outro
    target: Optional[Callable[[], Optional[QWidget]]] = None


class _SpotlightOverlay(QWidget):
    """Full-window dimmer with a transparent hole around the target.

    Uses a QRegion mask so the hole is *actually* see-through (the target
    widget under the overlay remains visible). Painting a "clear" rect on
    top of a filled overlay often just shows black on many platforms.
    """

    HOLE_PAD = 8

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        # We need mouse events on the dimmed area so clicks don't hit the UI
        # underneath, but the *hole* is outside this widget's mask so clicks
        # there pass through to the target naturally.
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._hole = QRect()
        self.hide()

    def set_hole(self, rect: QRect):
        """rect is in this overlay's coordinate system (same as parent)."""
        self._hole = QRect(rect) if rect is not None else QRect()
        self._apply_mask()
        self.update()

    def _apply_mask(self):
        """Dimmed region = full window minus padded hole → hole is transparent."""
        full = QRegion(self.rect())
        if self._hole.isValid() and not self._hole.isNull() and self.rect().intersects(self._hole):
            padded = self._hole.adjusted(
                -self.HOLE_PAD, -self.HOLE_PAD, self.HOLE_PAD, self.HOLE_PAD
            )
            # Keep hole inside overlay bounds
            padded = padded.intersected(self.rect().adjusted(0, 0, 0, 0))
            if padded.isValid() and not padded.isEmpty():
                full = full.subtracted(QRegion(padded, QRegion.RegionType.Rectangle))
        self.setMask(full)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_mask()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Only the masked (non-hole) region receives paint — fill with dim.
        p.fillRect(event.rect(), QColor(0, 0, 0, 150))
        # Optional accent ring drawn just outside the hole on the dim side
        if self._hole.isValid() and not self._hole.isNull():
            ring = self._hole.adjusted(
                -self.HOLE_PAD, -self.HOLE_PAD, self.HOLE_PAD, self.HOLE_PAD
            )
            p.setPen(QColor(79, 209, 197, 220))  # teal accent
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(ring)


class _StepCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tourCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(460)
        self.setMaximumHeight(340)
        self.setStyleSheet(
            "#tourCard {"
            "  background: #1e2430;"
            "  border: 1px solid #3a4558;"
            "  border-radius: 10px;"
            "}"
            "#tourCard QLabel { color: #e8ecf4; }"
            "#tourCard QLabel[role='heading'] { font-size: 15px; font-weight: 600; }"
            "#tourCard QLabel[role='caption'] { color: #9aa3b5; font-size: 12px; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(8)

        self.title = QLabel()
        self.title.setProperty("role", "heading")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)

        self.progress = QLabel()
        self.progress.setProperty("role", "caption")
        layout.addWidget(self.progress)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(110)
        scroll.setMaximumHeight(190)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        scroll.setWidget(self.body)
        layout.addWidget(scroll, 1)

        row = QHBoxLayout()
        self.skip_btn = QPushButton("Skip tour")
        self.back_btn = QPushButton("Back")
        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("primary")
        row.addWidget(self.skip_btn)
        row.addStretch(1)
        row.addWidget(self.back_btn)
        row.addWidget(self.next_btn)
        layout.addLayout(row)


class StudioTour(QWidget):
    """Owns overlay + card; parent should be the main window."""

    def __init__(self, main_window, studio_tab, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.studio_tab = studio_tab
        self._index = 0
        self._steps: list[TourStep] = []

        self.overlay = _SpotlightOverlay(main_window)
        self.card = _StepCard(main_window)
        self.card.skip_btn.clicked.connect(self.stop)
        self.card.back_btn.clicked.connect(self._back)
        self.card.next_btn.clicked.connect(self._next)
        self.card.hide()
        self.overlay.hide()

        main_window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.main_window and self.overlay.isVisible():
            if event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
                self._layout_step()
        return super().eventFilter(obj, event)

    def _resolve_attr(self, *names: str) -> Optional[Callable[[], Optional[QWidget]]]:
        st = self.studio_tab

        def getter(path=names):
            for name in path:
                obj = getattr(st, name, None)
                if isinstance(obj, QWidget):
                    return obj
            return None

        return getter

    def _build_steps(self) -> list[TourStep]:
        return [
            TourStep(
                "Welcome to Studio",
                "This short tour highlights the main parts of the Studio tab. "
                "You can run it again anytime from Help → Learn Studio.\n\n"
                "The highlighted area stays visible; the rest of the window is dimmed.",
            ),
            TourStep(
                "HUD name",
                "Rename your HUD here before Build & Install. The name becomes the folder under "
                "~/.config/conky/. Leaving a generic name makes finished themes hard to tell apart in Manager.",
                target=self._resolve_attr("name_edit", "hud_name", "name_field"),
            ),
            TourStep(
                "Nodes palette",
                "Sources, Logic, and Visuals live here. Drag a node onto the canvas, or double-click "
                "to add it. Plugins appear in their own sections after you load them from Tools → Plugins.",
                target=self._resolve_attr("palette", "palette_panel"),
            ),
            TourStep(
                "Canvas",
                "This is the node graph — not the desktop HUD. Pan empty space, Ctrl+scroll to zoom, "
                "Shift+drag to multi-select. Connect output sockets (right) to bindable inputs (left).\n\n"
                "Select the Canvas node to set width/height (workable resolution) and alignment on screen.",
                target=self._resolve_attr("canvas", "node_canvas", "view"),
            ),
            TourStep(
                "Properties",
                "Whatever is selected shows its fields here. Bindable rows accept wires; otherwise the "
                "constant value is used. Colours, fonts, sizes, and thresholds are all edited in this panel.",
                target=self._resolve_attr("property_panel", "properties"),
            ),
            TourStep(
                "Layers",
                "Visual nodes only. Drag to change draw order, use the eye to hide (skipped in codegen), "
                "and lock to prevent accidental moves.",
                target=self._resolve_attr("layers_dock", "layers", "layers_panel"),
            ),
            TourStep(
                "Live Preview",
                "Start runs a real Conky process on the same files Build would write — not a mockup. "
                "Stop ends that process. Watch the log for errors; session warnings may appear first on Start.",
                target=self._resolve_attr("preview_panel", "preview"),
            ),
            TourStep(
                "You’re ready",
                "Try: Source (CPU %) → Visual (Arc gauge) → Start preview → Project → Build & Install.\n\n"
                "Help → Getting Started has a longer written guide. Help → Support opens Discord and YouTube.\n\n"
                "You can replay this tour whenever you need a refresher.",
            ),
        ]

    def start(self):
        self._steps = self._build_steps()
        self._index = 0
        try:
            self.main_window.tabs.setCurrentWidget(self.studio_tab)
        except Exception:
            pass
        self.overlay.setGeometry(self.main_window.rect())
        self.overlay.show()
        self.overlay.raise_()
        self.card.show()
        self.card.raise_()
        self._show_step()

    def stop(self):
        self.overlay.hide()
        self.overlay.set_hole(QRect())
        self.card.hide()
        self._index = 0

    def _back(self):
        if self._index > 0:
            self._index -= 1
            self._show_step()

    def _next(self):
        if self._index >= len(self._steps) - 1:
            self.stop()
            return
        self._index += 1
        self._show_step()

    def _show_step(self):
        if not self._steps:
            self.stop()
            return
        step = self._steps[self._index]
        n = len(self._steps)
        self.card.title.setText(step.title)
        self.card.progress.setText(f"Step {self._index + 1} of {n}")
        self.card.body.setText(step.body)
        self.card.back_btn.setEnabled(self._index > 0)
        self.card.next_btn.setText("Finish" if self._index >= n - 1 else "Next")
        QTimer.singleShot(0, self._layout_step)

    def _layout_step(self):
        self.overlay.setGeometry(self.main_window.rect())
        step = self._steps[self._index] if self._steps else None
        hole = QRect()
        target = None
        if step and step.target:
            try:
                target = step.target()
            except Exception:
                target = None
        if target is not None and target.isVisible():
            top_left = target.mapTo(self.main_window, QPoint(0, 0))
            hole = QRect(top_left, target.size())
        self.overlay.set_hole(hole)

        cw = self.card.width()
        ch = max(self.card.sizeHint().height(), 230)
        mw, mh = self.main_window.width(), self.main_window.height()
        if hole.isValid() and not hole.isNull():
            x = min(max(hole.left(), 12), max(12, mw - cw - 12))
            y = hole.bottom() + 20
            if y + ch > mh - 12:
                y = max(12, hole.top() - ch - 20)
            if y < 12:
                y = 12
        else:
            x = max(12, (mw - cw) // 2)
            y = max(12, (mh - ch) // 3)
        self.card.setGeometry(x, y, cw, min(ch, max(180, mh - y - 12)))
        self.overlay.raise_()
        self.card.raise_()

