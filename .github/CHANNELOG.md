# Changelog

## Older build

## Version 1.0.1

### Fixed
- **Reactor Gauge (`visual.reactor_gauge`); incorrect value readout for non-percent sources.**
  The centre number always displayed the gauge's internal 0–100 fill
  percentage instead of the actual bound value. This was invisible for
  CPU/GPU percent sources (where the two happen to be nearly the same),
  but made the node look "locked" to CPU/GPU: binding it to Fan RPM,
  GPU Clock (MHz), Disk Temp, or any other non-percent numeric source
  produced a meaningless 0–100 number instead of the real reading.
  The readout now shows the raw bound value.

### Added
- **Reactor Gauge: new `value_suffix` property.**
  Lets the centre readout be labeled to match whatever source it's
  bound to (e.g. `%`, ` RPM`, ` MHz`, `°C`), the same way Arc Gauge and
  Segmented Gauge already work. Defaults to `%` to match prior behavior
  for existing projects.


## Older build

## 1.0.2

### Added
- **Update checker.** Conky Studio now checks GitHub for newer releases
  instead of you having to remember to look.
  - **Silent on startup** — runs automatically when the app launches, on
    a background thread so a slow or unreachable network never delays
    opening the window. It only ever says anything if a newer version
    actually exists; if you're already up to date, it stays quiet.
  - **On demand** — new **Help → Check for Updates…** menu action runs
    the same check manually and always reports a result (up to date,
    update found, or a network error), so it doubles as a connectivity
    sanity check.
  - When a newer version is found, a dialog shows the current vs.
    latest version and an **Open GitHub Release** button, along with:
    "Go to GitHub to get the new release, or if it is installed, use
    Griffin Updater to update to the new version."
  - Checks the GitHub Releases API (`/releases/latest`) rather than
    polling a fixed versioned download URL, so it always compares
    against whatever the newest published release actually is.

### New file
- `conkystudio/update_checker.py` — version comparison, the GitHub API
  call, and the background `QThread` worker. No UI code lives here;
  `main_window.py` owns the dialog and menu wiring.

_No other visual nodes were affected; every other gauge/readout
generator (Arc Gauge, Segmented Gauge, Bar, Text, etc.)
was audited and already displays the real bound value correctly. The
Reactor Gauge's `value` input already accepted any numeric source
(percent, celsius, or plain number); the bug was purely in how that
value was rendered, not in what sources it could bind to.

# Released

**v1.0.3 AppImage / AppRun improvements**

### 1. Flat layout with PyInstaller 6+
Added `--contents-directory .` to the PyInstaller call.  
PyInstaller 6+ nests support files (including Qt plugins) under `_internal/` by default. This flag restores the previous flat layout next to the executable so paths inside AppRun remain predictable.

### 2. Reliable Wayland with X11 fallback
- `QT_QPA_PLATFORM` is now set to `wayland;xcb` when `$WAYLAND_DISPLAY` is present. Qt tries Wayland first and silently falls back to XCB if needed.
- Plain X11 sessions still receive `xcb`.
- Existing user-set `QT_QPA_PLATFORM` is respected.
- Explicitly pin `QT_PLUGIN_PATH` and `QT_QPA_PLATFORM_PLUGIN_PATH` to avoid distro-level system Qt plugins that conflict with the bundled PyQt6.

Also added a build-time warning if `libqwayland.so` was not bundled by PyInstaller (without the plugin the Wayland path is effectively a no-op).

### 3. Self-installing desktop entry + icon (no appimaged required)
On every launch AppRun now:
- Checks whether `~/.local/share/applications/conky-studio.desktop` already points at the current AppImage.
- If not, installs a corrected `.desktop` file and the 256×256 icon into the appropriate XDG locations.
- Refreshes desktop/icon caches when the tools are available.

The process is idempotent and non-fatal; any failure still lets the application launch normally.

**Installation behaviour change**  
Instead of writing `Exec="$APPIMAGE"` (a transient path), the first run now:
- Copies the AppImage to `~/Applications/conky-studio.AppImage`.
- Points the desktop entry’s `Exec=` at that permanent location.

Details:
- Re-copies automatically when a newer AppImage is run (so shipping an update only requires launching the new file once).
- Detects when it is already running from the installed copy (`readlink -f` comparison) and skips the copy step to avoid loops.
- To fix an existing broken `.desktop` entry that points at a dead path: delete it once (`rm ~/.local/share/applications/conky-studio.desktop`) or simply launch the AppImage directly; the install logic will recreate a correct entry.
