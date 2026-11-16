"""
Bottom dock: Live Preview controls. The HUD itself appears as Conky's
own real window (own_window / layer-shell, same as it would standalone)
rather than embedded in a widget -- embedding a foreign X11 window
inside Qt is possible but brittle across window managers, and would be
outright impossible under Wayland layer-shell, so a real separate window
next to the Studio is both the simplest and the most portable choice.

Multi-window: a combo lets you pick which window conf the preview process
runs when the project has more than one entry in Project.windows.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QMessageBox, QComboBox,
)
from PyQt6.QtCore import Qt

from conkystudio.preview.live_preview import LivePreviewController
from conkystudio.hardware import discovery


class PreviewPanel(QWidget):
    def __init__(self, controller: LivePreviewController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._seen_log_tips: set[str] = set()
        self._suppress_window_combo = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        row = QHBoxLayout()
        heading = QLabel("Live Preview")
        heading.setProperty("role", "heading")
        row.addWidget(heading)
        row.addStretch(1)

        self.status = QLabel("Stopped")
        self.status.setProperty("role", "caption")
        row.addWidget(self.status)

        self.start_btn = QPushButton("\u25b6 Start")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self._on_start)
        row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("\u25a0 Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop)
        row.addWidget(self.stop_btn)
        layout.addLayout(row)

        # Window selector (visible when project has >1 window, or always
        # so single-window projects still show "Main (primary)").
        win_row = QHBoxLayout()
        win_row.addWidget(QLabel("Window"))
        self.window_combo = QComboBox()
        self.window_combo.setMinimumWidth(180)
        self.window_combo.setToolTip(
            "Which Conky window conf Live Preview runs. "
            "Add windows in the Windows dock for multi-monitor layouts."
        )
        self.window_combo.currentIndexChanged.connect(self._on_window_combo)
        win_row.addWidget(self.window_combo, 1)
        layout.addLayout(win_row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(110)
        self.log.setPlaceholderText(
            "Conky log output appears here. Known errors are annotated with [hint] lines."
        )
        layout.addWidget(self.log)

        self._project_getter = None

        controller.started.connect(self._on_started)
        controller.stopped.connect(self._on_stopped)
        controller.log_line.connect(self._on_log_line)
        controller.build_warning.connect(self._on_warnings)

        # Seed with a single default entry until a project is attached
        self._suppress_window_combo = True
        self.window_combo.addItem("Main (primary)", "primary")
        self._suppress_window_combo = False

    def set_project_getter(self, fn):
        """fn() -> Project -- called lazily so Start always uses the
        current in-memory project, not a stale snapshot."""
        self._project_getter = fn
        if fn:
            try:
                self.refresh_window_selector(fn())
            except Exception:
                pass

    def refresh_window_selector(self, project=None):
        """Rebuild the window combo from project.windows / controller helper."""
        if project is None and self._project_getter:
            try:
                project = self._project_getter()
            except Exception:
                project = None

        choices = self.controller.list_preview_windows(project)
        current = self.controller.preview_window_id or "primary"

        self._suppress_window_combo = True
        self.window_combo.clear()
        select_idx = 0
        for i, (wid, label) in enumerate(choices):
            self.window_combo.addItem(label, wid)
            if wid == current or (current in ("", "primary") and i == 0):
                select_idx = i
        if self.window_combo.count() == 0:
            self.window_combo.addItem("Main (primary)", "primary")
        self.window_combo.setCurrentIndex(select_idx)
        self._suppress_window_combo = False

        # Keep combo useful even for one window (shows primary label)
        self.window_combo.setEnabled(True)

    def set_selected_window(self, window_id: str):
        """Programmatic selection (e.g. from Windows panel Preview button)."""
        wid = window_id or "primary"
        self._suppress_window_combo = True
        idx = self.window_combo.findData(wid)
        if idx < 0 and wid not in ("", "primary"):
            # Maybe list is stale — try primary fallback label match
            idx = 0
        if idx >= 0:
            self.window_combo.setCurrentIndex(idx)
        self._suppress_window_combo = False
        self.controller.set_preview_window(wid)

    def _on_window_combo(self, *_args):
        if self._suppress_window_combo:
            return
        wid = self.window_combo.currentData()
        if wid is None:
            wid = "primary"
        self.controller.set_preview_window(str(wid))

    def _on_start(self):
        if not self._project_getter:
            return
        if not self._session_allows_start():
            return
        self._seen_log_tips.clear()
        # Ensure combo selection is applied before start
        wid = self.window_combo.currentData()
        if wid is not None:
            self.controller.set_preview_window(str(wid))
        self.controller.start(self._project_getter())

    def _session_allows_start(self) -> bool:
        """Preflight: block or warn based on session detection."""
        severity, session = discovery.session_preflight()
        if severity == "ok":
            return True

        body = session.warning or session.title or "Session may not support Conky overlays."
        if session.guidance:
            body += "\n\n" + "\n".join(f"• {g}" for g in session.guidance)
        body += "\n\nOpen Tools → Hardware & Session for the full report."

        if severity == "block":
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle(session.title or "Session warning")
            box.setText(body)
            start_anyway = box.addButton("Start anyway", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            return box.clickedButton() is start_anyway

        # warn / info — non-blocking notice in log + optional continue
        self.log.appendPlainText(f"[session] {session.title or severity}")
        if session.warning:
            self.log.appendPlainText(f"[session] {session.warning}")
        for g in session.guidance[:4]:
            self.log.appendPlainText(f"[session] • {g}")
        if severity == "warn":
            reply = QMessageBox.warning(
                self,
                session.title or "Session warning",
                body + "\n\nContinue with Live Preview?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            return reply == QMessageBox.StandardButton.Yes
        return True

    def _on_stop(self):
        self.controller.stop()

    def _on_started(self):
        self.status.setText("Running")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def _on_stopped(self):
        self.status.setText("Stopped")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _on_log_line(self, line: str):
        self.log.appendPlainText(line)
        tip = discovery.diagnose_log_line(line)
        if tip and tip not in self._seen_log_tips:
            self._seen_log_tips.add(tip)
            self.log.appendPlainText(f"[hint] {tip}")

    def _on_warnings(self, warnings: list):
        for w in warnings:
            self.log.appendPlainText(f"[build] {w}")
            for tip in discovery.diagnose_log_text(w):
                if tip not in self._seen_log_tips:
                    self._seen_log_tips.add(tip)
                    self.log.appendPlainText(f"[hint] {tip}")

    def notify_graph_changed(self, project):
        if self.controller.is_running:
            self.controller.request_update(project)
        # Keep selector labels in sync if windows were renamed via other paths
        self.refresh_window_selector(project)

