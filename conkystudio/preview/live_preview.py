"""
Live preview = the real Conky binary, pointed at a scratch build of the
current project, restarted on a debounce timer as the graph changes.
This is deliberately NOT a from-scratch Cairo simulation living inside
Qt -- rendering the actual generated conky.conf + render.lua is the only
way "what you see in the Studio" and "what start.sh produces" can never
drift apart, and it's the same validation approach used while building
this app (see the Xvfb + import screenshot test in the build notes).

Scope choice: the preview runs Conky directly rather than through the
generated start.sh, so it never leaves a background `while true; do
sleep N; done` polling loop running after you close the Studio. Daemon-
mode sources (weather, sensors in "background daemon" polling mode) get
one fresh synchronous poll per rebuild instead of their own live loop --
good enough to see real values while designing; execi-mode sources poll
themselves continuously the same as they would standalone, no special
handling needed.
"""
from __future__ import annotations

import os
import shutil
import tempfile

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from conkystudio.model.project import Project
from conkystudio.codegen import builder

DEBOUNCE_MS = 350


class LivePreviewController(QObject):
    started = pyqtSignal()
    stopped = pyqtSignal()
    log_line = pyqtSignal(str)
    build_warning = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dir = tempfile.mkdtemp(prefix="conky-studio-preview-")
        self._process: QProcess | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._rebuild_and_restart)
        self._pending_project: Project | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def request_update(self, project: Project):
        """Called on every graph_changed -- schedules a debounced restart
        rather than rebuilding immediately, so dragging a slider doesn't
        relaunch Conky on every intermediate value."""
        self._pending_project = project
        if self._running:
            self._timer.start(DEBOUNCE_MS)

    def start(self, project: Project):
        self._pending_project = project
        self._running = True
        self._rebuild_and_restart()

    def stop(self):
        self._running = False
        self._timer.stop()
        self._kill_process()
        self.stopped.emit()

    def _kill_process(self):
        if self._process is not None:
            self._process.kill()
            self._process.waitForFinished(1000)
            self._process = None

    def _rebuild_and_restart(self):
        if self._pending_project is None:
            return
        self._kill_process()

        result = builder.build_project(self._pending_project, self._dir)
        if result.warnings:
            self.build_warning.emit(result.warnings)

        self._prime_daemon_caches()

        self._process = QProcess(self)
        self._process.setWorkingDirectory(self._dir)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.start("conky", ["-c", os.path.join(self._dir, "conky.conf")])
        self.started.emit()

    def _prime_daemon_caches(self):
        """One synchronous run of every daemon-mode family script so the
        preview shows real numbers immediately instead of blanks until
        the next scheduled poll (there is no scheduled poll in preview
        mode -- see module docstring)."""
        scripts_dir = os.path.join(self._dir, "scripts")
        if not os.path.isdir(scripts_dir):
            return
        for name in os.listdir(scripts_dir):
            path = os.path.join(scripts_dir, name)
            if not os.access(path, os.X_OK):
                continue
            proc = QProcess()
            proc.start(path, [])
            proc.waitForFinished(4000)

    def _on_stderr(self):
        if self._process:
            data = bytes(self._process.readAllStandardError()).decode("utf-8", "replace")
            for line in data.splitlines():
                self.log_line.emit(line)

    def _on_stdout(self):
        if self._process:
            data = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
            for line in data.splitlines():
                self.log_line.emit(line)

    def cleanup(self):
        self.stop()
        shutil.rmtree(self._dir, ignore_errors=True)
