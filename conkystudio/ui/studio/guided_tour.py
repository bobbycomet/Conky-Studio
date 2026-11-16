"""
Full-app guided tour: Theme Wizard → Studio → Manager → Store.

Help → Take the Full Tour opens this. Individual "Learn Studio" /
"Learn Theme Wizard" menus remain for partial walkthroughs.

Flow
----
1. Theme Wizard opens pre-set to Minimal + Showcase. Steps explain that
   wizard output is a *learning scaffold*, not a finished export — the
   user is expected to rewire, rename, and fix things in Studio.
2. On Create (or Skip with a blank Minimal Showcase project), Studio
   loads and the Studio phase covers palette categories/subcategories,
   daemon vs execi sensors, theme naming rules (no spaces), then the
   usual canvas / properties / preview walkthrough.
3. Manager tab: install roots, Start/Stop, theme.json, save vs build.
4. Store tab: Theme Vault (link-out) vs OpenDesktop/Pling (install).

Reuses the same floating card + highlight ring as StudioTour so the
UI language stays consistent and nothing is dimmed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from PyQt6.QtCore import QTimer, QRect, QPoint
from PyQt6.QtWidgets import QWidget, QTabWidget

from conkystudio.ui.studio.studio_tour import _HighlightRing, _TourCard


@dataclass
class _Step:
    title: str
    body: str
    target: object = None  # () -> QWidget | None
    # Optional side-effect before the step is shown (switch tab, raise dock, …).
    on_enter: Optional[Callable[[], None]] = None
    phase: str = ""  # "wizard" | "studio" | "manager" | "store" | ""


class GuidedTour:
    """End-to-end Conky Studio walkthrough.

    API used by MainWindow:
        tour = GuidedTour(main_window)
        tour.start()
    """

    def __init__(self, main_window, parent=None):
        self.main = main_window
        self.studio = main_window.studio_tab
        self.manager = main_window.manager_tab
        self.store = main_window.store_tab
        self._parent = parent or main_window
        self._ring: _HighlightRing | None = None
        self._card: _TourCard | None = None
        self._index = 0
        self._steps: list[_Step] = []
        self._active = False
        self._wizard_dialog = None
        self._wizard_tour_active = False

    # ------------------------------------------------------------------
    def start(self):
        """Begin (or restart) the full tour at the Theme Wizard phase."""
        self.stop()
        self._active = True
        self._index = 0
        self._open_wizard_phase()

    def stop(self):
        self._active = False
        self._wizard_tour_active = False
        if self._ring is not None:
            self._ring.hide()
            self._ring.deleteLater()
            self._ring = None
        if self._card is not None:
            self._card.hide()
            self._card.deleteLater()
            self._card = None
        # Leave any open wizard alone — user may still Create from it.

    # ------------------------------------------------------------------
    # Phase 1 — Theme Wizard (modal dialog with its own card overlay)
    # ------------------------------------------------------------------
    def _open_wizard_phase(self):
        from conkystudio.ui.studio.theme_wizard import ThemeWizardDialog

        dialog = ThemeWizardDialog(self.main)
        self._wizard_dialog = dialog
        try:
            dialog.prepare_for_guided_tour()
        except Exception:
            # Older dialog without helper — best-effort radio selection.
            self._fallback_select_minimal_showcase(dialog)

        # Run the wizard-scoped tour first; when it finishes (or user
        # Creates), continue into Studio.
        from conkystudio.ui.studio.theme_wizard_tour import ThemeWizardTour

        wizard_tour = ThemeWizardTour(dialog)
        # Use the guided-tour step list (learning-tool messaging) instead
        # of the short default ThemeWizardTour steps.
        wizard_tour._build_steps = lambda: self._apply_wizard_steps(wizard_tour)
        self._wizard_tour_active = True

        original_stop = wizard_tour.stop

        def _on_wizard_tour_stop():
            original_stop()
            # If the dialog is still open the user can still hit Create;
            # we only auto-advance when they close/create.

        wizard_tour.stop = _on_wizard_tour_stop  # type: ignore[method-assign]
        dialog._guided_tour = wizard_tour

        QTimer.singleShot(50, wizard_tour.start)

        accepted = dialog.exec()
        self._wizard_dialog = None
        self._wizard_tour_active = False

        if not self._active:
            return

        if accepted and dialog.result_project is not None:
            project = dialog.result_project
            # Enforce a space-free default name so the tour can demonstrate
            # the rule without leaving a broken install folder.
            try:
                if " " in (project.name or ""):
                    project.name = (project.name or "Minimal-HUD").replace(" ", "-")
            except Exception:
                pass
            self.main.studio_tab.load_project(project)
            self.main.current_project_path = None
            self.main.tabs.setCurrentWidget(self.studio)
            self.main.statusBar().showMessage(
                f"Tour project loaded: {project.name} — continue with Studio steps"
            )
        else:
            # User cancelled Create — still continue the tour on whatever
            # is already in Studio (or a blank canvas).
            self.main.tabs.setCurrentWidget(self.studio)

        self._build_main_window_steps()
        self._index = 0
        self._ensure_ui()
        QTimer.singleShot(40, self._show_step)

    def _fallback_select_minimal_showcase(self, dialog):
        try:
            for btn in dialog.category_group.buttons():
                if btn.text() == "Minimal":
                    btn.setChecked(True)
                    dialog._on_category_chosen(btn)
                    break
            for btn in dialog.tier_group.buttons():
                if btn.text() == "Showcase":
                    btn.setChecked(True)
                    dialog._on_tier_changed(btn)
                    break
        except Exception:
            pass

    def _apply_wizard_steps(self, wizard_tour):
        d = wizard_tour.dialog

        def _w(name: str):
            return lambda: getattr(d, name, None)

        wizard_tour._steps = [
            _Step(
                "Theme Wizard is a learning tool",
                "This wizard builds a starter node graph so you can learn Studio — "
                "it is not a finished theme ready to export as-is. Expect to rename the "
                "project, move nodes, change poll modes, and rewire edges. That editing "
                "is the point of the tour.",
                target=None,
            ),
            _Step(
                "Minimal + Showcase (tour default)",
                "For this walkthrough we pre-select Minimal (clean glass layout) and "
                "Showcase complexity (chrome, LEDs, graphs, core strip, process table, "
                "signature flourish). You can change these later; the tour only needs a "
                "dense graph to point at real nodes.",
                target=_w("cat_box"),
            ),
            _Step(
                "Category & resolution",
                "Category picks colours, fonts, and layout personality. Resolution should "
                "match the monitor you will pin the HUD to — the wizard places panels "
                "across the full canvas at that size.",
                target=_w("res_combo"),
            ),
            _Step(
                "Panels",
                "Toggle which data blocks to include (CPU, GPU, weather, music, …). "
                "A panel is skipped automatically if its source node type is missing "
                "from this install.",
                target=_w("panel_box"),
            ),
            _Step(
                "Extras & complexity",
                "Extras layer chrome, LEDs, graphs, gradients, and flourishes. Complexity "
                "resets those checkboxes to Simple / Full / Showcase defaults — Showcase "
                "turns almost everything on so the Studio phase has more to show.",
                target=_w("tier_box"),
            ),
            _Step(
                "Create, then edit in Studio",
                "Hit Create to drop the graph onto the Studio canvas. Next steps cover "
                "node categories, a deliberate sensor poll-mode gotcha, and naming rules "
                "before Manager and Store.",
                target=None,
            ),
        ]

    # ------------------------------------------------------------------
    # Phases 2–4 — Studio, Manager, Store (main window overlay)
    # ------------------------------------------------------------------
    def _build_main_window_steps(self):
        s = self.studio
        main = self.main

        def _studio(name: str):
            return lambda: getattr(s, name, None)

        def _goto_studio():
            try:
                main.tabs.setCurrentWidget(self.studio)
            except Exception:
                pass

        def _goto_manager():
            try:
                main.tabs.setCurrentWidget(self.manager)
            except Exception:
                pass

        def _goto_store():
            try:
                main.tabs.setCurrentWidget(self.store)
            except Exception:
                pass

        def _raise_dock(title_prefix: str):
            def _fn():
                _goto_studio()
                try:
                    if title_prefix.startswith("Layers") and hasattr(s, "layers_dock_widget"):
                        s.layers_dock_widget.setVisible(True)
                        s.layers_dock_widget.raise_()
                    elif title_prefix.startswith("Properties") and hasattr(s, "property_dock"):
                        s.property_dock.setVisible(True)
                        s.property_dock.raise_()
                    elif title_prefix.startswith("Windows") and hasattr(s, "windows_dock"):
                        s.windows_dock.setVisible(True)
                        s.windows_dock.raise_()
                    elif title_prefix.startswith("Live Preview") and hasattr(s, "preview_dock"):
                        s.preview_dock.setVisible(True)
                        s.preview_dock.raise_()
                    elif title_prefix.startswith("Position") and hasattr(s, "position_stage_dock"):
                        s.position_stage_dock.setVisible(True)
                        s.position_stage_dock.raise_()
                except Exception:
                    pass
            return _fn

        self._steps = [
            # ---- Studio intro ----
            _Step(
                "Studio — your node graph",
                "Everything the wizard created is editable here. Sources feed Logic "
                "(optional), which feeds Visuals. Drag between ports to wire; select a "
                "node to edit properties on the right.",
                target=_studio("view"),
                on_enter=_goto_studio,
                phase="studio",
            ),
            _Step(
                "Palette — Sources",
                "Sources are sensors and system reads.\n"
                "• Native (teal): CPU %, RAM, disk, network, uptime, battery — free "
                "Conky variables, no scripts.\n"
                "• Sensors (amber): CPU/GPU temp, GPU util, fan RPM, disk temp — need "
                "lm-sensors / nvidia-smi / smartctl.\n"
                "• Weather / Media / Network / Custom: external scripts (curl, playerctl, …).\n"
                "Subcategories in the palette group them: System, Sensors, Weather, Media, …",
                target=_studio("palette"),
                on_enter=_goto_studio,
                phase="studio",
            ),
            _Step(
                "Palette — Logic",
                "Logic sits between sources and visuals: Smooth (EMA), Hysteresis, "
                "Threshold, Math, Map Range, String Format, Enum Map, and more. Use them "
                "to quiet noisy sensors, gate LEDs, or format text. Output is still a "
                "value another node can wire into.",
                target=_studio("palette"),
                on_enter=_goto_studio,
                phase="studio",
            ),
            _Step(
                "Palette — Visuals (overview)",
                "What you see on the desktop:\n"
                "• Gauges & Bars — arc, bar, needle, segmented, LED, reactor\n"
                "• Graphs — history, sparkline, multi-series, radar chart, top table\n"
                "• Text — labels, flip cards\n"
                "• Effects — glow, spiral, matrix rain, orbit, equalizer, fan, vinyl\n"
                "• Shapes — rectangle, lines, brackets, crosshair\n"
                "• Icons & Images — PNG/SVG, weather icons, album art\n"
                "• Advanced — Custom Lua\n"
                "This is an overview only; open a node’s Properties help text for detail.",
                target=_studio("palette"),
                on_enter=_goto_studio,
                phase="studio",
            ),
            _Step(
                "Sensor poll mode: daemon vs execi",
                "GPU util, GPU/CPU/disk temp, and fan RPM are scripted sensors. "
                "Wizard themes deliberately default those to Simple (execi) so you can "
                "see stutter or blank values first-hand on a high-FPS HUD.\n\n"
                "For a smooth desktop HUD, select each Sensors-subcategory source and "
                "set Polling mode → Background daemon (zero-stutter). Daemon writes a "
                "cache file from start.sh; Lua only reads, never blocks the draw.",
                target=_studio("property_panel"),
                on_enter=_raise_dock("Properties"),
                phase="studio",
            ),
            _Step(
                "Theme names — no spaces",
                "Names like “Minimal HUD” break install paths and start.sh lock files. "
                "Use hyphens instead: Minimal-HUD, reactor-core, my-desk.\n\n"
                "Rename under Project → Save / the project name field before "
                "Build & Install. Spaces are a common first-run error; fix the name "
                "before you treat a blank screen as a graphics bug.",
                target=None,
                on_enter=_goto_studio,
                phase="studio",
            ),
            _Step(
                "Canvas & wiring",
                "Drag from an output port to an input port. Data flows "
                "Source → (optional Logic) → Visual. Unwired bindable properties use "
                "the constant in the property panel.",
                target=_studio("view"),
                on_enter=_goto_studio,
                phase="studio",
            ),
            _Step(
                "Layers",
                "Draw order, lock, and jump-to-node. Tabified with Properties and "
                "Windows on the right dock stack.",
                target=_studio("layers_dock"),
                on_enter=_raise_dock("Layers"),
                phase="studio",
            ),
            _Step(
                "Properties",
                "Selected node’s fields: position, colours, ranges, poll mode, gradients, "
                "blend mode. The Canvas node at the top of the graph holds window size, "
                "FPS, and alignment.",
                target=_studio("property_panel"),
                on_enter=_raise_dock("Properties"),
                phase="studio",
            ),
            _Step(
                "Windows / Monitors",
                "Extra Conky windows for multi-monitor layouts. Pin each to an output "
                "when needed. Single-monitor projects keep one auto window.",
                target=_studio("windows_panel"),
                on_enter=_raise_dock("Windows"),
                phase="studio",
            ),
            _Step(
                "Live Preview",
                "Start runs a real Conky against a scratch build of your graph — not a "
                "mock. Use it to verify poll modes and layout before installing.",
                target=_studio("preview_panel"),
                on_enter=_raise_dock("Live Preview"),
                phase="studio",
            ),
            _Step(
                "Position Stage",
                "Drag visual proxies on a plane the size of your Conky window. Fine-tune "
                "with X/Y in Properties. Live Preview can stay on; the HUD updates when "
                "you release the mouse.",
                target=_studio("position_stage"),
                on_enter=_raise_dock("Position"),
                phase="studio",
            ),
            _Step(
                "Save project vs Build",
                "• Project → Save Project… writes a .json graph you can reopen and edit "
                "(your working document).\n"
                "• Project → Build to Folder… / Build & Install exports real Conky files "
                "(conky.conf, render.lua, scripts/, start.sh) under ~/.config/conky/"
                "<Name>.\n\n"
                "Save often while learning. Build when you want Manager to Start the HUD. "
                "Re-building overwrites generated files from the current graph.",
                target=None,
                on_enter=_goto_studio,
                phase="studio",
            ),
            # ---- Manager ----
            _Step(
                "Manager tab",
                "Lists themes already under ~/.config/conky and ~/.conky. Start / Stop "
                "run each theme’s start.sh (same files you could launch by hand). Conky "
                "Studio does not need to stay open for an installed HUD to keep running.",
                target=None,
                on_enter=_goto_manager,
                phase="manager",
            ),
            _Step(
                "Install, export, metadata",
                "Drop a .zip / .tar.gz on the install area, or use Export .zip / Duplicate / "
                "Uninstall on the selected theme. Generate or edit theme.json and README "
                "from the detail pane so the library shows a proper name and description.",
                target=None,
                on_enter=_goto_manager,
                phase="manager",
            ),
            # ---- Store ----
            _Step(
                "Store — Theme Vault",
                "Catalog of community themes. Link-out only: open the host (GitHub, Pling, …) "
                "in your browser. Nothing is downloaded from here automatically — read the "
                "README on the host first.",
                target=None,
                on_enter=_goto_store,
                phase="store",
            ),
            _Step(
                "Store — OpenDesktop / Pling",
                "Live OCS search that can Install into ~/.config/conky/. After install, "
                "switch to Manager and hit Start. Prefer themes you trust; scripts run "
                "on your machine like any other Conky theme.",
                target=None,
                on_enter=_goto_store,
                phase="store",
            ),
            _Step(
                "You're set",
                "Full tour complete. Re-run anytime from Help → Take the Full Tour. "
                "Partial tours: Learn Theme Wizard, Learn Studio. "
                "Rename with hyphens, set sensor nodes to daemon when you want zero "
                "stutter, Save the .json while editing, Build & Install when ready for "
                "Manager.",
                target=None,
                on_enter=_goto_studio,
                phase="",
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
        if step.on_enter is not None:
            try:
                step.on_enter()
            except Exception:
                pass

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
            try:
                self.main.statusBar().showMessage("Full tour finished — Help → Take the Full Tour to run again")
            except Exception:
                pass
            return
        self._index += 1
        self._show_step()

    def _back(self):
        if self._index <= 0:
            return
        self._index -= 1
        self._show_step()
 
