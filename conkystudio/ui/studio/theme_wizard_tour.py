"""
Theme Wizard tour.

Same "floating card + thin highlight ring, nothing dimmed" approach as
studio_tour.StudioTour, but scoped to the ThemeWizardDialog itself rather
than the main Studio window. Launched from the dialog's "Take the tour"
button, which only appears once the user has actively picked a category
(see ThemeWizardDialog._on_category_chosen) -- so this tour is always
about a HUD the person has actually started building, not a cold dialog.

Reuses _HighlightRing / _TourCard from studio_tour.py rather than
duplicating that Qt painting code.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QRect, QPoint, QTimer
from PyQt6.QtWidgets import QWidget

from conkystudio.ui.studio.studio_tour import _HighlightRing, _TourCard


@dataclass
class _Step:
    title: str
    body: str
    # Optional callable returning a QWidget to highlight (or None).
    target: object = None  # () -> QWidget | None


class ThemeWizardTour:
    """Guided walkthrough of the Theme Wizard dialog's own controls.

    API used by ThemeWizardDialog:
        tour = ThemeWizardTour(dialog)
        tour.start()

    `dialog` is the ThemeWizardDialog instance. It doubles as both the
    overlay host (ring/card are parented to it, since the dialog is its
    own top-level window) and the source of target widgets, via the same
    getattr(name) pattern StudioTour uses against its studio_tab.
    """

    def __init__(self, dialog):
        self.dialog = dialog
        self._ring: _HighlightRing | None = None
        self._card: _TourCard | None = None
        self._index = 0
        self._steps: list[_Step] = []
        self._active = False

    def start(self):
        """Begin (or restart) the tour."""
        self._build_steps()
        self._index = 0
        self._active = True
        self._ensure_ui()
        # Defer one tick so the dialog has settled before we measure geometry.
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
        d = self.dialog

        def _w(name: str):
            return lambda: getattr(d, name, None)

        self._steps = [
            _Step(
                "Theme Wizard is a learning tool",
                "This builds a starter node graph so you can learn Studio — not a finished "
                "theme ready to export as-is. Expect to rename the project (no spaces — use "
                "hyphens like Minimal-HUD), rewire nodes, and fix sensor poll modes. That "
                "editing is intentional.",
                target=None,
            ),
            _Step(
                "Category",
                "Pick the visual style. Each one sets its own accent colours, font, and layout — "
                "Sci-Fi and Cyberpunk lean on glow and flourish, Minimal and Terminal stay flat "
                "and quiet. The full guided tour pre-selects Minimal + Showcase for a dense "
                "learning graph.",
                target=_w("cat_box"),
            ),
            _Step(
                "Resolution",
                "Match this to your monitor. The generated layout fills the whole canvas at this "
                "size, so panel positions and chrome are sized proportionally to it.",
                target=_w("res_combo"),
            ),
            _Step(
                "Panels",
                "Choose which data panels to include -- CPU, GPU, weather, music, and so on. A "
                "panel is skipped automatically if its underlying data source isn't available.",
                target=_w("panel_box"),
            ),
            _Step(
                "Extras",
                "Chrome, status LEDs, history graphs, glow, gradients, and more -- optional "
                "flourishes layered on top of the core panels. Complexity below resets these to "
                "sensible per-tier defaults, but you can still fine-tune any of them by hand.",
                target=_w("opt_box"),
            ),
            _Step(
                "Complexity",
                "Simple keeps just the theme's signature element. Full adds framing chrome and a "
                "real Source → Logic → Visual demo chain (a smoothed value gating a warning LED). "
                "Showcase adds every animated flourish -- orbit fields, a per-core CPU strip, a "
                "live process table, a footer ticker.",
                target=_w("tier_box"),
            ),
            _Step(
                "Create, then edit in Studio",
                "Hit Create to drop the graph onto the Studio canvas. Sensor nodes default to "
                "execi so you can see that mode first-hand; switch GPU/temp/fan sources to "
                "Background daemon for zero-stutter HUDs. Reopen this tour anytime a category "
                "is picked, or run Help → Take the Full Tour for Wizard → Studio → Manager → Store.",
                target=None,
            ),
        ]

    def _ensure_ui(self):
        host = self.dialog
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
        top_left = widget.mapTo(self.dialog, QPoint(0, 0))
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
        host = self.dialog.rect()
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

