"""
Bottom dock: Live Preview controls. The HUD itself appears as Conky's
own real window (own_window / layer-shell, same as it would standalone)
rather than embedded in a widget -- embedding a foreign X11 window
inside Qt is possible but brittle across window managers, and would be
outright impossible under Wayland layer-shell, so a real separate window
next to the Studio is both the simplest and the most portable choice.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from conkystudio.preview.live_preview import LivePreviewController
from conkystudio.hardware import discovery


class PreviewPanel(QWidget):
    def __init__(self, controller: LivePreviewController, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._seen_log_tips: set[str] = set()

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

    def set_project_getter(self, fn):
        """fn() -> Project -- called lazily so Start always uses the
        current in-memory project, not a stale snapshot."""
        self._project_getter = fn

    def _on_start(self):
        if not self._project_getter:
            return
        if not self._session_allows_start():
            return
        self._seen_log_tips.clear()
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

