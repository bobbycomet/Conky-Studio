"""
One-shot hardware/session diagnostic, run on demand from the Studio's
Hardware panel (and by codegen/builder.py to resolve Canvas's
window_type == "auto" into a real own_window_type). Everything here is
read-only detection; it never writes a config, it just informs one.

Wayland reality check (aligned with Conky's upstream docs): Conky draws
as a background overlay on Wayland only on compositors that implement
wlr-layer-shell -- wlroots-based ones (Sway, Hyprland, Wayfire, labwc,
river, ...), KDE Plasma on Wayland, and Mir-based ones. GNOME's Mutter
does NOT implement it, so Conky cannot run as a desktop overlay under
GNOME Wayland (an X11 session or a different DE is the fix -- not a
config tweak). Distro packages also don't all compile Wayland support
in; some stock packages remain X11-only.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Optional

# Desktop tokens that usually mean layer-shell is available (substring match
# on XDG_CURRENT_DESKTOP / DESKTOP_SESSION, lowercased).
LAYER_SHELL_DESKTOPS = {
    "sway", "hyprland", "wayfire", "kde", "plasma", "kde-plasma",
    "labwc", "river", "mir", "niri", "mangowc", "waybox",
}
# Tokens that usually mean Mutter / no layer-shell for Conky overlays.
NO_LAYER_SHELL_DESKTOPS = {
    "gnome", "gnome-wayland", "ubuntu", "unity", "budgie",
}

# Known phrases from Conky / start.sh stderr → user-facing guidance.
_LOG_DIAGNOSTICS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"wlr-layer-shell|layer-shell-unstable|doesn't support wlr-layer", re.I),
        "Conky reports the compositor lacks wlr-layer-shell. Desktop overlays need a "
        "layer-shell compositor (Plasma Wayland, Sway, Hyprland, …) or an X11 session. "
        "GNOME Mutter Wayland cannot host Conky as an overlay.",
    ),
    (
        re.compile(r"No protocol specified|cannot open display|Unable to open display", re.I),
        "Conky could not open a display. Check DISPLAY / WAYLAND_DISPLAY and that you "
        "are not launching from a context without a graphical session.",
    ),
    (
        re.compile(r"conky:\s*unable to|error while loading|cannot open shared object", re.I),
        "Conky failed to load a library or resource. Check the full log line and that "
        "dependencies for your Conky package are installed.",
    ),
    (
        re.compile(r"X11|xlib|XOpenDisplay", re.I),
        "Log mentions X11/Xlib. On a pure Wayland session an X11-only Conky may be "
        "using XWayland or failing to anchor. Prefer a Wayland-enabled Conky build "
        "(`conky -v` should mention Wayland).",
    ),
    (
        re.compile(r"Permission denied|not found \(.*start\.sh|No such file", re.I),
        "Launcher or script path problem. Ensure start.sh is executable and paths "
        "inside the theme folder still exist.",
    ),
]


@dataclass
class SessionInfo:
    display_server: str = "unknown"   # "x11" | "wayland" | "unknown"
    desktop: str = ""                  # best-effort $XDG_CURRENT_DESKTOP / $DESKTOP_SESSION
    layer_shell_likely_supported: bool = False
    conky_has_wayland_build: bool = False
    recommended_window_type: str = "normal"
    warning: str = ""                  # primary one-line / short warning for conf comments
    # Structured guidance for UI
    severity: str = "ok"               # "ok" | "info" | "warn" | "block"
    title: str = ""
    guidance: list[str] = field(default_factory=list)
    overlay_likely: bool = True        # False when we believe desktop HUDs will fail


@dataclass
class GpuInfo:
    vendor: str = "none"   # "nvidia" | "amd" | "intel" | "none"
    detail: str = ""


@dataclass
class HardwareReport:
    session: SessionInfo = field(default_factory=SessionInfo)
    gpu: GpuInfo = field(default_factory=GpuInfo)
    net_iface: str = ""
    cpu_sensor_found: bool = False
    disk_devices: list = field(default_factory=list)
    conky_installed: bool = False
    conky_version: str = ""
    lm_sensors_installed: bool = False
    notes: list = field(default_factory=list)
    conky_path: str = ""


def _run(cmd: list, *, timeout: float = 3.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def _run_both(cmd: list, *, timeout: float = 3.0) -> tuple[str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.stdout or "", p.stderr or ""
    except Exception:
        return "", ""


def detect_session() -> SessionInfo:
    info = SessionInfo()
    session_type = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    if not session_type:
        session_type = (
            "wayland" if os.environ.get("WAYLAND_DISPLAY")
            else ("x11" if os.environ.get("DISPLAY") else "")
        )
    info.display_server = session_type or "unknown"

    desktop_raw = (
        os.environ.get("XDG_CURRENT_DESKTOP")
        or os.environ.get("DESKTOP_SESSION")
        or ""
    )
    desktop = desktop_raw.lower().replace(":", ";")
    info.desktop = desktop_raw

    conky_path = shutil.which("conky")
    conky_version_out = _run([conky_path, "-v"]) if conky_path else ""
    info.conky_has_wayland_build = "wayland" in conky_version_out.lower()

    tokens = {t.strip() for t in re.split(r"[;:,\s]+", desktop) if t.strip()}

    def _any_token(names: set[str]) -> bool:
        for t in tokens:
            for n in names:
                if n in t or t in n:
                    return True
        # Also substring-search the whole string for hyprland-style single tokens
        return any(n in desktop for n in names)

    is_plasma = _any_token({"kde", "plasma", "kde-plasma"})
    is_gnome_family = _any_token(NO_LAYER_SHELL_DESKTOPS) and not is_plasma
    is_layer_shell_de = _any_token(LAYER_SHELL_DESKTOPS)

    if info.display_server == "x11":
        info.recommended_window_type = "normal"
        info.layer_shell_likely_supported = False
        info.overlay_likely = True
        info.severity = "ok"
        info.title = "X11 session"
        info.guidance = [
            "X11 is the most predictable environment for Conky desktop HUDs.",
            "Window type auto resolves to normal with standard undecorated/below hints.",
        ]
        if not conky_path:
            info.severity = "block"
            info.title = "Conky not found"
            info.overlay_likely = False
            info.warning = "Conky is not installed (or not on PATH). Live Preview and built themes need `conky`."
            info.guidance = [
                "Install Conky from your distro packages, then confirm `conky -v` works in a terminal.",
            ]

    elif info.display_server == "wayland":
        info.layer_shell_likely_supported = is_layer_shell_de and not is_gnome_family
        info.recommended_window_type = _wayland_default_window_type(
            is_plasma=is_plasma,
            layer_shell=info.layer_shell_likely_supported,
        )

        if not conky_path:
            info.severity = "block"
            info.overlay_likely = False
            info.title = "Conky not found"
            info.warning = "Conky is not installed (or not on PATH)."
            info.guidance = [
                "Install a Conky package that includes Wayland support if possible.",
                "Confirm with: conky -v   (output should mention Wayland on this session).",
            ]

        elif is_gnome_family:
            info.severity = "block"
            info.overlay_likely = False
            info.title = "GNOME / Mutter Wayland — overlays not supported"
            info.warning = (
                f"Wayland session on GNOME/Mutter-style desktop ('{desktop_raw or 'unknown'}'). "
                "Mutter does not implement wlr-layer-shell, so Conky cannot draw as a desktop "
                "overlay here — switch to an X11 session (if available) or a layer-shell "
                "compositor (Plasma Wayland, Sway, Hyprland, …)."
            )
            info.guidance = [
                "This is a compositor limitation, not a Conky Studio setting.",
                "If your distro still offers “GNOME on Xorg”, use that session for HUDs.",
                "Or use Plasma Wayland, Sway, Hyprland, Wayfire, labwc, river, etc.",
                "Changing own_window_type will not unlock Mutter overlays.",
            ]

        elif not info.conky_has_wayland_build:
            info.severity = "warn"
            info.overlay_likely = False
            info.title = "Wayland session, but Conky looks X11-only"
            info.warning = (
                "Wayland session detected, but `conky -v` does not report Wayland support — "
                "this binary was likely packaged X11-only. The HUD may only work under "
                "XWayland or may not anchor correctly. Install/build Conky with Wayland enabled."
            )
            info.guidance = [
                "Run: conky -v   and look for Wayland in the feature list.",
                "On some distros the default package is X11-only; search for a wayland-enabled package or build from source.",
                "X11 session remains the reliable fallback.",
            ]

        elif not info.layer_shell_likely_supported:
            info.severity = "warn"
            info.overlay_likely = False
            info.title = "Wayland desktop not recognized as layer-shell"
            info.warning = (
                f"Wayland session on '{desktop_raw or 'unknown'}' — could not confirm layer-shell "
                "support. Conky overlays need wlr-layer-shell (or equivalent). If the HUD is blank, "
                "try Plasma/Sway/Hyprland or an X11 session."
            )
            info.guidance = [
                "Supported targets typically include: Sway, Hyprland, Wayfire, labwc, river, Plasma Wayland.",
                "If you know your compositor supports layer-shell, you can still try Live Preview and read the log.",
            ]

        else:
            info.severity = "ok"
            info.overlay_likely = True
            info.title = "Wayland + layer-shell likely OK"
            info.guidance = [
                f"Desktop looks layer-shell capable ({desktop_raw or 'unknown'}).",
                "Conky reports Wayland support. Overlays should work; if not, check Live Preview log.",
                f"Window type auto → {info.recommended_window_type}.",
            ]

    else:
        info.severity = "warn"
        info.overlay_likely = False
        info.title = "Unknown display server"
        info.warning = "Could not determine X11 vs Wayland. Set XDG_SESSION_TYPE or run from a graphical session."
        info.guidance = ["Start Conky Studio from a desktop session, not a bare TTY."]
        info.recommended_window_type = "normal"

    return info


def _wayland_default_window_type(*, is_plasma: bool, layer_shell: bool) -> str:
    """Session-specific default when Canvas window_type is 'auto'."""
    # Plasma Wayland: 'normal' with undecorated/below hints is the validated path.
    # 'desktop' can hide on desktop click on some Plasma versions.
    if is_plasma:
        return "normal"
    if layer_shell:
        return "normal"
    return "normal"


def detect_gpu() -> GpuInfo:
    if shutil.which("nvidia-smi"):
        out = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]).strip()
        if out:
            return GpuInfo(vendor="nvidia", detail=out.splitlines()[0])
    for card in _glob_drm_cards():
        vendor_path = f"{card}/vendor"
        if os.path.isfile(vendor_path):
            try:
                with open(vendor_path) as f:
                    vid = f.read().strip()
                if vid == "0x1002":
                    return GpuInfo(vendor="amd", detail=card)
                if vid == "0x8086":
                    return GpuInfo(vendor="intel", detail=card)
            except OSError:
                continue
    return GpuInfo(vendor="none")


def _glob_drm_cards() -> list:
    base = "/sys/class/drm"
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        if name.startswith("card") and "-" not in name:
            out.append(f"{base}/{name}/device")
    return out


def detect_net_iface() -> str:
    try:
        out = _run(["ip", "route"])
        for line in out.splitlines():
            if line.startswith("default"):
                parts = line.split()
                if "dev" in parts:
                    return parts[parts.index("dev") + 1]
    except Exception:
        pass
    return ""


def detect_cpu_sensor() -> bool:
    return shutil.which("sensors") is not None


def detect_disk_devices() -> list:
    devices = []
    base = "/sys/block"
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if name.startswith(("sd", "nvme", "hd")):
                devices.append(f"/dev/{name}")
    return devices


def run_full_report() -> HardwareReport:
    report = HardwareReport()
    report.session = detect_session()
    report.gpu = detect_gpu()
    report.net_iface = detect_net_iface()
    report.cpu_sensor_found = detect_cpu_sensor()
    report.disk_devices = detect_disk_devices()
    report.lm_sensors_installed = detect_cpu_sensor()

    conky_path = shutil.which("conky") or ""
    report.conky_path = conky_path
    report.conky_installed = bool(conky_path)
    if conky_path:
        out = _run([conky_path, "-v"])
        report.conky_version = out.splitlines()[0] if out else ""

    if not report.conky_installed:
        report.notes.append(
            "Conky isn't installed (or not on PATH) — Build & Live Preview need it. "
            "Install your distro's conky package, then re-check this report."
        )
    if not report.lm_sensors_installed:
        report.notes.append(
            "lm-sensors isn't installed — CPU temperature sources will read blank until "
            "sensors is available (e.g. install lm-sensors and run sensors-detect)."
        )
    if report.gpu.vendor == "none":
        report.notes.append(
            "No GPU vendor detected — GPU utilization/temperature/VRAM sources may read 0 "
            "on this machine (harmless while designing)."
        )
    if report.session.warning:
        report.notes.append(report.session.warning)
    for g in report.session.guidance:
        if g not in report.notes:
            report.notes.append(g)
    return report


def format_hardware_report(report: HardwareReport | None = None) -> str:
    """Human-readable multi-section report for Hardware & Session dialog."""
    r = report or run_full_report()
    s = r.session
    lines = [
        "=== Session ===",
        f"Display server:              {s.display_server}",
        f"Desktop / compositor:        {s.desktop or '(unknown)'}",
        f"Overlay likely to work:      {'yes' if s.overlay_likely else 'NO'}",
        f"Layer-shell likely:          {s.layer_shell_likely_supported}",
        f"Severity:                    {s.severity}" + (f" — {s.title}" if s.title else ""),
        f"Recommended window type:     {s.recommended_window_type}",
        "",
        "=== Conky ===",
        f"Installed:                   {r.conky_installed}  ({r.conky_path or 'n/a'})",
        f"Version line:                {r.conky_version or 'n/a'}",
        f"Wayland in `conky -v`:       {s.conky_has_wayland_build}",
        "",
        "=== Hardware hints ===",
        f"lm-sensors:                  {r.lm_sensors_installed}",
        f"GPU vendor:                  {r.gpu.vendor}  {r.gpu.detail}",
        f"Default net iface:           {r.net_iface or '(not detected)'}",
        f"Disk devices:                {', '.join(r.disk_devices) or '(none found)'}",
        "",
    ]
    if s.guidance:
        lines.append("=== What to do ===")
        for g in s.guidance:
            lines.append(f"  • {g}")
        lines.append("")
    other = [n for n in (r.notes or []) if n not in s.guidance and n != s.warning]
    if s.warning and s.warning not in (s.guidance or []):
        lines.append("=== Primary warning ===")
        lines.append(f"  • {s.warning}")
        lines.append("")
    if other:
        lines.append("=== Other notes ===")
        for n in other:
            lines.append(f"  • {n}")
        lines.append("")
    lines.append(
        "Docs: wiki Compatibility page — X11 is most reliable; "
        "GNOME Wayland cannot host Conky desktop overlays."
    )
    return "\n".join(lines)


def resolve_window_type(canvas_window_type: str, session: SessionInfo | None = None) -> str:
    """Canvas node's window_type ('auto'|'normal'|'desktop'|'dock') -> the
    literal own_window_type conky_conf_gen should write."""
    if canvas_window_type != "auto":
        return canvas_window_type if canvas_window_type in ("normal", "desktop", "dock") else "normal"
    session = session or detect_session()
    wt = session.recommended_window_type or "normal"
    return wt if wt in ("normal", "desktop", "dock") else "normal"


def session_preflight() -> tuple[str, SessionInfo]:
    """
    Returns (severity, session) for UI gates before Live Preview / Start.
    severity: ok | info | warn | block
    """
    session = detect_session()
    return session.severity, session


def diagnose_log_line(line: str) -> Optional[str]:
    """Map a Conky/start.sh log line to extra user guidance, if known."""
    if not line or not line.strip():
        return None
    for pattern, advice in _LOG_DIAGNOSTICS:
        if pattern.search(line):
            return advice
    return None


def diagnose_log_text(text: str) -> list[str]:
    """Unique guidance strings for a multi-line log blob."""
    seen: list[str] = []
    for line in (text or "").splitlines():
        tip = diagnose_log_line(line)
        if tip and tip not in seen:
            seen.append(tip)
    return seen

