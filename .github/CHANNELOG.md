# Changelog

## Released

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


## Released

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
