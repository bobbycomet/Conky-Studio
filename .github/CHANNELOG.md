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

_No other visual nodes were affected; every other gauge/readout
generator (Arc Gauge, Segmented Gauge, Bar, Text, etc.)
was audited and already displays the real bound value correctly. The
Reactor Gauge's `value` input already accepted any numeric source
(percent, celsius, or plain number); the bug was purely in how that
value was rendered, not in what sources it could bind to.
