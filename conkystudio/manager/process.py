"""
"The manager executes the theme's start.sh. The previous Conky instance
is stopped cleanly if necessary." start.sh already contains its own
single-instance PID-file lock (see codegen/start_sh_gen.py), so
launching a second theme -- or the same one twice -- is already safe at
the shell level; ThemeProcessManager mostly exists to give the Manager
tab a handle for Start/Stop and a running indicator.

Monitor pinning: theme.json may carry "monitor": "DP-1" (or primary/auto).
When a concrete output is set, we write pinned conf copies under
.runtime-cache/ with xinerama_head injected and launch a thin pin start
script so third-party and Studio themes can be placed on a chosen head
without rebuilding.
"""
from __future__ import annotations

import os
import re
import signal
import stat

from PyQt6.QtCore import QObject, QProcess, pyqtSignal

from conkystudio.model.theme_meta import THEME_META_FILENAME, ThemeMeta


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


def _load_theme_monitor(theme_path: str) -> str:
    meta_path = os.path.join(theme_path, THEME_META_FILENAME)
    if not os.path.isfile(meta_path):
        return "auto"
    try:
        meta = ThemeMeta.load(meta_path)
        return (meta.monitor or "auto").strip() or "auto"
    except Exception:
        return "auto"


def _resolve_xinerama_head(monitor_name: str) -> tuple[int | None, str]:
    """Return (0-based head index or None, note)."""
    try:
        from conkystudio.hardware import discovery
        mons = discovery.detect_monitors()
        resolved = discovery.resolve_monitor_name(monitor_name, mons)
        if not resolved or resolved in ("", "auto"):
            return None, f"monitor '{monitor_name}' unresolved — using default placement"
        for idx, m in enumerate(mons):
            if m.name == resolved and m.name not in ("", "auto"):
                return idx, f"pinned to {m.summary()} (xinerama_head={idx})"
        return None, f"monitor '{monitor_name}' not in current output list"
    except Exception as exc:
        return None, f"monitor resolve failed: {exc}"


def _inject_xinerama_head(conf_text: str, head: int) -> str:
    """Insert or replace xinerama_head inside a conky.config = { ... } block."""
    # Replace existing assignment
    if re.search(r"^\s*xinerama_head\s*=", conf_text, re.M):
        return re.sub(
            r"^(\s*)xinerama_head\s*=\s*[^,\n]+,?\s*$",
            rf"\1xinerama_head = {int(head)},",
            conf_text,
            count=1,
            flags=re.M,
        )
    # Insert after conky.config = {
    m = re.search(r"(conky\.config\s*=\s*\{)", conf_text)
    if m:
        insert_at = m.end()
        return (
            conf_text[:insert_at]
            + f"\n    xinerama_head = {int(head)},  -- injected by Conky Studio Manager pin\n"
            + conf_text[insert_at:]
        )
    # Fallback: prepend a minimal note (unlikely for real confs)
    return (
        f"-- Conky Studio pin: xinerama_head={head}\n"
        + conf_text
        + f"\n-- (could not locate conky.config table to inject xinerama_head)\n"
    )


def _find_conf_basenames(theme_path: str) -> list[str]:
    """Conf files to pin: prefer theme.json windows[].conf, else conky*.conf."""
    meta_path = os.path.join(theme_path, THEME_META_FILENAME)
    names: list[str] = []
    if os.path.isfile(meta_path):
        try:
            import json
            with open(meta_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for w in data.get("windows") or []:
                if isinstance(w, dict) and w.get("enabled", True) and w.get("conf"):
                    names.append(str(w["conf"]))
        except Exception:
            pass
    if not names:
        preferred = ["conky.conf"]
        for name in sorted(os.listdir(theme_path)):
            if name.startswith("conky") and name.endswith(".conf"):
                if name not in preferred:
                    preferred.append(name)
        names = [n for n in preferred if os.path.isfile(os.path.join(theme_path, n))]
    # de-dupe preserve order
    seen = set()
    out = []
    for n in names:
        base = os.path.basename(n)
        if base not in seen and os.path.isfile(os.path.join(theme_path, base)):
            seen.add(base)
            out.append(base)
    return out or (["conky.conf"] if os.path.isfile(os.path.join(theme_path, "conky.conf")) else [])


def _write_pinned_launch(theme_path: str, head: int) -> str | None:
    """Write pinned confs + pin_start.sh under .runtime-cache. Return path to pin_start.sh."""
    confs = _find_conf_basenames(theme_path)
    if not confs:
        return None
    cache = os.path.join(theme_path, ".runtime-cache")
    os.makedirs(cache, exist_ok=True)
    pinned_basenames: list[str] = []
    for conf_name in confs:
        src = os.path.join(theme_path, conf_name)
        try:
            with open(src, "r", encoding="utf-8", errors="replace") as fh:
                body = fh.read()
        except OSError:
            continue
        pinned_name = f"pin_{conf_name}"
        dest = os.path.join(cache, pinned_name)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(_inject_xinerama_head(body, head))
        pinned_basenames.append(pinned_name)

    if not pinned_basenames:
        return None

    theme_name = os.path.basename(os.path.abspath(theme_path))
    lock_name = "".join(ch if ch.isalnum() else "-" for ch in theme_name.lower()).strip("-") or "conky-studio-hud"

    launch_lines = []
    for i, pb in enumerate(pinned_basenames):
        if i < len(pinned_basenames) - 1:
            launch_lines.append(f'conky -c "${{DIR}}/.runtime-cache/{pb}" &')
        else:
            launch_lines.append(f'exec conky -c "${{DIR}}/.runtime-cache/{pb}"')
    conky_launch = "\n".join(launch_lines)

    # Reuse daemon loops from existing start.sh when present (best-effort extract)
    loops_text = "# (daemon loops: run original start.sh scripts once)"
    start_sh = os.path.join(theme_path, "start.sh")
    script_boot = ""
    if os.path.isfile(start_sh):
        script_boot = '''
# One-shot run of scripts shipped with the theme (same idea as archive install)
if [[ -d "${DIR}/scripts" ]]; then
    for s in "${DIR}"/scripts/*.sh; do
        [[ -f "$s" ]] || continue
        chmod +x "$s" 2>/dev/null
        "$s" &
    done
fi
'''

    pin_start = os.path.join(cache, "pin_start.sh")
    content = f'''#!/usr/bin/env bash
# Auto-generated by Conky Studio Manager for monitor pin (xinerama_head={head}).
# Do not hand-edit; regenerated on each Start with a pinned monitor.

if [[ -z "$CONKY_STUDIO_REEXEC" ]]; then
    export CONKY_STUDIO_REEXEC=1
    exec setsid "$0" "$@"
fi

DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
LOCK_FILE="${{XDG_RUNTIME_DIR:-/tmp}}/{lock_name}.pid"

if [[ -f "$LOCK_FILE" ]]; then
    OLD_PID="$(cat "$LOCK_FILE" 2>/dev/null)"
    if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill -TERM -- "-$OLD_PID" 2>/dev/null
        sleep 0.4
        kill -KILL -- "-$OLD_PID" 2>/dev/null
    fi
fi
echo $$ > "$LOCK_FILE"

mkdir -p "${{DIR}}/.runtime-cache"
chmod +x "${{DIR}}"/scripts/*.sh 2>/dev/null

{script_boot}
{conky_launch}
'''
    with open(pin_start, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(pin_start, os.stat(pin_start).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return pin_start


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

    def start(self, theme_path: str, monitor: str | None = None):
        """Start theme. *monitor* overrides theme.json monitor when provided."""
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

        mon = (monitor if monitor is not None else _load_theme_monitor(theme_path)).strip() or "auto"
        launch_path = start_sh
        if mon not in ("", "auto", "primary"):
            head, note = _resolve_xinerama_head(mon)
            self.log_line.emit(theme_path, f"[monitor] {note}")
            if head is not None:
                pin_start = _write_pinned_launch(theme_path, head)
                if pin_start:
                    launch_path = pin_start
                    self.log_line.emit(
                        theme_path,
                        f"[monitor] launching pinned conf (xinerama_head={head})",
                    )
                else:
                    self.log_line.emit(theme_path, "[monitor] could not write pin conf — using default start.sh")
            else:
                self.log_line.emit(theme_path, "[monitor] pin skipped — using default start.sh")

        # start.sh's own lock logic already kills any previous instance
        self._pids.pop(theme_path, None)

        # startDetached: the new process is NOT owned by any QProcess object,
        # so Qt will not terminate it when Studio exits.
        ok, pid = QProcess.startDetached(launch_path, [], theme_path)
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
