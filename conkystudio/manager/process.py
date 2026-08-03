"""
"The manager executes the theme's start.sh. The previous Conky instance
is stopped cleanly if necessary." start.sh already contains its own
single-instance PID-file lock (see codegen/start_sh_gen.py), so
launching a second theme -- or the same one twice -- is already safe at
the shell level; ThemeProcessManager mostly exists to give the Manager
tab a handle for Start/Stop and a running indicator.
"""
from __future__ import annotations

import os
import signal

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


def _lock_file_for(theme_path: str) -> str:
    """Mirror the lock-name logic in start_sh_gen.build_start_sh."""
    name = os.path.basename(os.path.abspath(theme_path))
    lock_name = "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-") or "conky-studio-hud"
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return os.path.join(runtime, f"{lock_name}.pid")


def _pid_from_lock(theme_path: str) -> int | None:
    lock = _lock_file_for(theme_path)
    try:
        with open(lock, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return None
        pid = int(raw)
        # kill -0 == "does this pid exist?"
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError, OSError):
        return None


class ThemeProcessManager(QObject):
    log_line = pyqtSignal(str, str)        # theme_path, line  (kept for API compat; unused with startDetached)
    state_changed = pyqtSignal(str, bool)  # theme_path, is_running

    def __init__(self, parent=None):
        super().__init__(parent)
        # theme_path -> pid of the detached session leader (the start.sh after setsid)
        self._pids: dict[str, int] = {}

    def is_running(self, theme_path: str) -> bool:
        # Prefer the pid we started this session; fall back to the lock file
        # so a theme that was already running before Studio launched is detected.
        pid = self._pids.get(theme_path) or _pid_from_lock(theme_path)
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            self._pids.pop(theme_path, None)
            return False

    def start(self, theme_path: str):
        start_sh = os.path.join(theme_path, "start.sh")
        if not os.path.isfile(start_sh):
            self.log_line.emit(theme_path, "No start.sh found in this theme folder.")
            return
        os.chmod(start_sh, 0o755)

        # Session preflight notes (Manager has no modal; log only).
        try:
            from conkystudio.hardware import discovery
            severity, session = discovery.session_preflight()
            if severity in ("warn", "block") and session.warning:
                self.log_line.emit(theme_path, f"[session] {session.title or severity}: {session.warning}")
            for g in (session.guidance or [])[:3]:
                if severity in ("warn", "block"):
                    self.log_line.emit(theme_path, f"[session] • {g}")
        except Exception:
            pass

        # start.sh's own lock logic already kills any previous instance
        self._pids.pop(theme_path, None)

        # startDetached: the new process is NOT owned by any QProcess object,
        # so Qt will not terminate it when Studio exits.
        ok, pid = QProcess.startDetached(start_sh, [], theme_path)
        if not ok or pid <= 0:
            self.log_line.emit(theme_path, "Failed to start theme (QProcess.startDetached returned false).")
            self.state_changed.emit(theme_path, False)
            return

        self._pids[theme_path] = pid
        self.state_changed.emit(theme_path, True)

    def stop(self, theme_path: str):
        pid = self._pids.pop(theme_path, None) or _pid_from_lock(theme_path)
        if pid is None:
            self.state_changed.emit(theme_path, False)
            return

        try:
            # Match start.sh: kill the whole process group (Conky + poller loops)
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass

        # Best-effort cleanup of the lock file so is_running() is correct immediately
        try:
            os.unlink(_lock_file_for(theme_path))
        except OSError:
            pass

        self.state_changed.emit(theme_path, False)

    def stop_all(self):
        for path in list(self._pids.keys()):
            self.stop(path)
        # Also stop anything we didn't start but that left a lock file
        # (optional; omit if you prefer stop_all to only touch what this
        # session launched).

    def detach_all(self):
        """No-op with startDetached — processes are already independent.
        Kept so older closeEvent call sites remain valid."""
        self._pids.clear()

