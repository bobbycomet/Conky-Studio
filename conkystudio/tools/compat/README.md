# Compatibility test suite

Portable (run anywhere, no display):
- `python tools/compat/apprun_matrix.py path/to/AppRun` - the AppRun platform/glibc/no-display decision logic over 20 environments, with real sockets standing in for compositors.
- `python tools/compat/session_matrix.py out.json tools/compat/session_golden.json` - runs `detect_session()` over 864 scenarios (session type x desktop x display vars x Conky variant) and diffs against the golden file. Any difference after a code change must be intentional; regenerate the golden file only then.
- `HARNESS_LUA=lupa.lua51 python tools/plugin_harness.py plugins.json` (also `lupa.luajit21`, `lupa.lua53`, `lupa.lua54`) - plugin check on each Lua runtime.

- `python tools/compat/deps_matrix.py` - missing-package detection over 23 distro fixtures (Debian/Fedora/Arch/openSUSE/Void families, derivatives, immutable systems, Conky without Lua-Cairo), the generated install commands, and the safety properties of the root helper (it refuses anything but allowlisted requirement keys).
- `python tools/compat/autostart_matrix.py` - "Start at login": 13 awkward theme names (spaces, `$`, quotes, backticks, unicode, `%`, ...) are written, validated with `desktop-file-validate`, and the generated launcher is actually executed.
- `QT_QPA_PLATFORM=offscreen python tools/compat/ui_deps_autostart_test.py out.png` - the Missing-packages dialog and popup rules, and the Manager's Start-at-login control, offscreen, with a screenshot montage.
- `tools/compat/distro_check.sh Conky-Studio-x86_64.AppImage` - run on any real distro (Arch, Fedora, openSUSE...); prints os-release, glibc, Conky's Lua-Cairo status and Conky Studio's own JSON dependency report. Needs no display.

Lab scripts (`lab/`, need a display, `conky-all`, `xdotool`, `imagemagick`; paths such as `/opt/themes`, `/opt/fuzz`, `/build` are the lab's - edit them):
- `gen_themes.py` / `gen_fuzz.py` - build 15 test themes (7 presets x Simple/Showcase + a kitchen sink with every visual) and 109 single-source scenarios (every native data source x every option and hostile values).
- `run_conky_themes.sh` / `run_conky_fuzz.sh` - run them in REAL Conky and report crashes, Lua errors and whether anything was drawn. Includes a negative control (a deliberately broken draw hook) which must fail.
- `xorg_up.sh` + `dummy.conf` - Xorg with the dummy driver: a real 32-bit ARGB visual. **Do not use Xvfb for Conky**: Conky segfaults on Xvfb's visuals, which looks like an app bug but is not.
- `launch_x11.sh`, `launch_x11_wm.sh`, `launch_wayland.sh`, `launch_edge_cases.sh` - launch the AppImage's AppRun under Xvfb / several WMs / headless Sway, Weston, labwc / awkward environments.
- `shape_options.py`, `option_audit.py`, `star_styles.py`, `cpu_clamp_unit.py` - built-in shape options on every Lua runtime, an "option does nothing" audit, star style renders, CPU-count parsing.

Lab gotchas learned the hard way: mount `/sys` (Conky segfaults without `/sys/devices/system/cpu/present`); never `pkill -f` a pattern that appears in your own command line; Conky needs a depth-24 X server with a 32-bit ARGB visual.
