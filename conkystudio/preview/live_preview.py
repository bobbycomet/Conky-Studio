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
import traceback

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from conkystudio.model.project import Project
from conkystudio.codegen import builder

DEBOUNCE_MS = 350
# Gap between the old conky process actually dying and launching the new
# one. Conky's own-window setup does an X round trip against the display
# right at startup; if that happens before the window manager has caught
# up with the previous window's teardown, Conky can be handed a stale
# window ID and die with a BadWindow X error (SIGABRT) instead of just
# drawing normally. See _kill_process / _rebuild_and_restart.
RESTART_SETTLE_MS = 150
# How long to let Conky exit on its own after SIGTERM (so it runs its
# normal X shutdown path / XDestroyWindow) before we escalate to SIGKILL.
GRACEFUL_STOP_MS = 800


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
        # True whenever WE are the ones tearing the process down (restart
        # or stop). _on_process_finished uses this -- separately from
        # self._running -- to tell "we killed this on purpose, mid-restart"
        # apart from "conky exited/crashed on its own". Without this, a
        # normal debounced restart raced its own finished() signal into
        # thinking Conky had crashed and flipped started/stopped twice
        # per rebuild.
        self._expected_exit = False
        # Which window conf to preview when the project has several.
        # "" / "primary" → conky.conf; otherwise a window id → conky_<id>.conf
        self.preview_window_id: str = "primary"

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
        """Tear down the current conky process, letting it exit on its own
        first so it runs its normal X shutdown path (XDestroyWindow /
        XCloseDisplay) instead of being yanked out from under the X server
        with SIGKILL. A hard-killed conky's window can outlive the process
        just long enough (from the window manager's point of view) that the
        *next* conky's own-window startup queries a window ID that's about
        to vanish -- that's the BadWindow / X_GetProperty crash. Escalating
        to kill() only if terminate() doesn't work keeps that race rare
        instead of routine."""
        if self._process is None:
            return
        self._expected_exit = True
        proc, self._process = self._process, None
        proc.terminate()
        if not proc.waitForFinished(GRACEFUL_STOP_MS):
            proc.kill()
            proc.waitForFinished(1000)
        self._expected_exit = False

    def _rebuild_and_restart(self):
        """Kill whatever's running now, then defer the actual rebuild+
        relaunch to the next event loop turn. The delay isn't just
        cosmetic: it gives the window manager / X server a moment to fully
        process the previous window's teardown before the new conky
        process does its own-window X round trip on startup. Doing the
        relaunch synchronously right after the kill is what caused the
        BadWindow crash."""
        if self._pending_project is None:
            return
        self._kill_process()
        QTimer.singleShot(RESTART_SETTLE_MS, self._do_rebuild_and_restart)

    def _do_rebuild_and_restart(self):
        if self._pending_project is None:
            return

        try:
            # Keep windows list coherent before codegen
            if hasattr(self._pending_project, "ensure_windows"):
                self._pending_project.ensure_windows()
            result = builder.build_project(self._pending_project, self._dir)
        except Exception as exc:
            # Surface build failures in the preview log instead of killing the UI
            self.log_line.emit(f"[build error] {exc}")
            for line in traceback.format_exc().strip().splitlines()[-12:]:
                self.log_line.emit(line)
            self._running = False
            self.stopped.emit()
            return

        if result.warnings:
            self.build_warning.emit(result.warnings)

        self._prime_daemon_caches()

        conf_path = self._resolve_preview_conf()
        if not os.path.isfile(conf_path):
            self.log_line.emit(f"[build error] conf not found: {conf_path}")
            self._running = False
            self.stopped.emit()
            return

        self._process = QProcess(self)
        self._process.setWorkingDirectory(self._dir)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.finished.connect(self._on_process_finished)
        self._process.start("conky", ["-c", conf_path])
        if not self._process.waitForStarted(3000):
            err = self._process.errorString() if self._process else "unknown"
            self.log_line.emit(f"[preview] failed to start conky: {err}")
            self._running = False
            self.stopped.emit()
            return
        self.started.emit()

    def _on_process_finished(self, exit_code: int, _status):
        # Ignore finished() firing for a process WE just told to stop as
        # part of a restart/stop -- that's expected, not a crash, and
        # _kill_process() already owns clearing self._process for it.
        if self._expected_exit:
            return
        # Conky exited on its own (crash or user closed the window)
        if self._running:
            self.log_line.emit(f"[preview] conky exited (code {exit_code})")
            self._running = False
            self._process = None
            self.stopped.emit()

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

    def set_preview_window(self, window_id: str):
        """Select which window to show in Live Preview (multi-monitor projects)."""
        self.preview_window_id = window_id or "primary"
        if self._running and self._pending_project is not None:
            self._timer.start(DEBOUNCE_MS)

    def list_preview_windows(self, project: Project | None = None) -> list[tuple[str, str]]:
        """[(window_id, label), ...] for a preview window selector combo."""
        p = project or self._pending_project
        if p is None:
            return [("primary", "Main")]
        wins = p.enabled_windows() if hasattr(p, "enabled_windows") else []
        if not wins:
            return [("primary", "Main")]
        primary = p.primary_window() if hasattr(p, "primary_window") else wins[0]
        out = []
        for w in sorted(wins, key=lambda x: (x.z, x.id)):
            label = w.name or w.id
            mon = getattr(w, "monitor", "auto") or "auto"
            if mon not in ("auto", "primary"):
                label = f"{label} @ {mon}"
            if w.id == primary.id:
                label = f"{label} (primary)"
            out.append((w.id, label))
        return out

    def _resolve_preview_conf(self) -> str:
        """Pick conky.conf path for the selected preview window."""
        wid = self.preview_window_id or "primary"
        primary_path = os.path.join(self._dir, "conky.conf")
        if wid in ("", "primary"):
            return primary_path
        # Match builder naming: conky_<safe_id>.conf
        safe = "".join(ch if ch.isalnum() else "_" for ch in wid).strip("_") or "extra"
        candidate = os.path.join(self._dir, f"conky_{safe}.conf")
        if os.path.isfile(candidate):
            return candidate
        # Fallback: if only one conf exists, use it
        if os.path.isfile(primary_path):
            return primary_path
        return candidate

    def cleanup(self):
        self.stop()
        shutil.rmtree(self._dir, ignore_errors=True)
