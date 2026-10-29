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
import subprocess
import time

from PyQt6.QtCore import QObject, QProcess, QProcessEnvironment, pyqtSignal

from conkystudio.model.theme_meta import THEME_META_FILENAME, ThemeMeta


def _lock_name_candidates(theme_path: str) -> list[str]:
    folder = os.path.basename(os.path.abspath(theme_path))
    names = [folder]
    meta_path = os.path.join(theme_path, THEME_META_FILENAME)
    if os.path.isfile(meta_path):
        try:
            meta = ThemeMeta.load(meta_path)
            if meta.name and meta.name not in names:
                names.append(meta.name)
        except Exception:
            pass
    out = []
    for n in names:
        lock = "".join(ch if ch.isalnum() else "-" for ch in n.lower()).strip("-") or "conky-studio-hud"
        if lock not in out:
            out.append(lock)
    return out


def _lock_file_for(theme_path: str) -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    return os.path.join(runtime, f"{_lock_name_candidates(theme_path)[0]}.pid")


def _pid_from_lock(theme_path: str) -> int | None:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    for lock_name in _lock_name_candidates(theme_path):
        lock = os.path.join(runtime, f"{lock_name}.pid")
        try:
            with open(lock, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if not raw:
                continue
            pid = int(raw)
            os.kill(pid, 0)
            return pid
        except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError, OSError):
            continue
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
    if re.search(r"^\s*xinerama_head\s*=", conf_text, re.M):
        return re.sub(
            r"^(\s*)xinerama_head\s*=\s*[^,\n]+,?\s*$",
            rf"\1xinerama_head = {int(head)},",
            conf_text,
            count=1,
            flags=re.M,
        )
    m = re.search(r"(conky\.config\s*=\s*\{)", conf_text)
    if m:
        insert_at = m.end()
        return (
            conf_text[:insert_at]
            + f"\n    xinerama_head = {int(head)},  -- injected by Conky Studio Manager pin\n"
            + conf_text[insert_at:]
        )
    return (
        f"-- Conky Studio pin: xinerama_head={head}\n"
        + conf_text
        + f"\n-- (could not locate conky.config table to inject xinerama_head)\n"
    )


def _find_conf_basenames(theme_path: str) -> list[str]:
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
    seen = set()
    out = []
    for n in names:
        base = os.path.basename(n)
        if base not in seen and os.path.isfile(os.path.join(theme_path, base)):
            seen.add(base)
            out.append(base)
    return out or (["conky.conf"] if os.path.isfile(os.path.join(theme_path, "conky.conf")) else [])


def _write_pinned_launch(theme_path: str, head: int) -> str | None:
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

    start_sh = os.path.join(theme_path, "start.sh")
    script_boot = ""
    if os.path.isfile(start_sh):
        script_boot = '''
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


def _clean_env() -> QProcessEnvironment:
    env = QProcessEnvironment.systemEnvironment()
    env.remove("LD_LIBRARY_PATH")
    env.remove("LD_PRELOAD")
    return env


def _kill_all_conky() -> None:
    """Kill every process whose executable name is exactly 'conky'.

    Do NOT use `pkill -f conky` — that matches 'conky-studio' and kills
    the AppImage itself.
    """
    for cmd in (
        ["pkill", "-x", "conky"],
        ["killall", "-q", "conky"],
    ):
        try:
            subprocess.run(cmd, capture_output=True, timeout=3)
        except Exception:
            pass


class ThemeProcessManager(QObject):
    log_line = pyqtSignal(str, str)
    state_changed = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pids: dict[str, int] = {}
        # Themes we successfully launched this session. Used so the Stop
        # button stays enabled even when a third-party start.sh never
        # writes the expected lock file.
        self._started: set[str] = set()

    def is_running(self, theme_path: str) -> bool:
        # If we started it this session, treat it as running so Stop is enabled.
        if theme_path in self._started:
            return True
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
        start_sh = os.path.join(theme_path, "start.sh")
        if not os.path.isfile(start_sh):
            self.log_line.emit(theme_path, "No start.sh found in this theme folder.")
            return
        os.chmod(start_sh, 0o755)

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

        self._pids.pop(theme_path, None)

        proc = QProcess()
        proc.setProgram(launch_path)
        proc.setArguments([])
        proc.setWorkingDirectory(theme_path)
        proc.setProcessEnvironment(_clean_env())

        ok = proc.startDetached()
        if not ok:
            self.log_line.emit(theme_path, "Failed to start theme (QProcess.startDetached returned false).")
            self.state_changed.emit(theme_path, False)
            return

        # Best-effort PID discovery (lock file or Qt)
        real_pid = None
        for _ in range(20):
            time.sleep(0.05)
            real_pid = _pid_from_lock(theme_path)
            if real_pid is not None:
                break
        if real_pid is None:
            real_pid = proc.processId() or 0
        if real_pid > 0:
            self._pids[theme_path] = real_pid

        # Mark as started this session so Stop is always enabled afterwards
        self._started.add(theme_path)
        self.state_changed.emit(theme_path, True)

    def stop(self, theme_path: str):
        """Stop the theme. Kills the tracked process group (if any) and
        every process named exactly 'conky'."""
        pid = _pid_from_lock(theme_path) or self._pids.pop(theme_path, None)
        self._pids.pop(theme_path, None)
        self._started.discard(theme_path)

        if pid is not None:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    pass

        # Safe: only exact process name "conky", never -f (would match conky-studio)
        _kill_all_conky()

        # Clean up lock files
        runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        for lock_name in _lock_name_candidates(theme_path):
            try:
                os.unlink(os.path.join(runtime, f"{lock_name}.pid"))
            except OSError:
                pass

        self.state_changed.emit(theme_path, False)

    def stop_all(self):
        for path in list(self._started) + list(self._pids.keys()):
            self.stop(path)
        self._started.clear()
        _kill_all_conky()

    def detach_all(self):
        self._pids.clear()
        # Keep _started so the UI still knows what was launched this session
        # if the user re-opens Manager after a brief leave; clear only on
        # explicit stop / stop_all.
