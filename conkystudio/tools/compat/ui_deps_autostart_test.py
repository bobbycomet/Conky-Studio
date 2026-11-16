#!/usr/bin/env python3
"""Offscreen UI tests: DependenciesDialog, popup frequency rules, Manager 'Start at login'."""
import os, sys, tempfile, json
HOME = tempfile.mkdtemp(prefix="uitest-home-"); os.environ.update(HOME=HOME, XDG_CONFIG_HOME=HOME + "/.config", QT_QPA_PLATFORM="offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMessageBox
app = QApplication([])
from conkystudio.theme import build_qss; app.setStyleSheet(build_qss())
from conkystudio.hardware import deps
REAL_BUILD = deps.build_report
from conkystudio.ui.deps_dialog import DependenciesDialog
from conkystudio import settings
fails = []
def check(n, c, d=""):
    if not c: fails.append(f"{n}: {d}")

def rep(osr, have=(), probe="", exists=lambda p: False, pk=True, helper=(False, False)):
    return REAL_BUILD(os_release=osr, which=lambda b: f"/usr/bin/{b}" if (b in have or (b == "pkexec" and pk)) else None,
                             conky_probe=lambda p: probe, exists=exists, euid=1000, helper=helper)
CAIRO = "Lua bindings:\n  * Cairo\n"
cases = {
 "ubuntu_nothing": rep({"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Ubuntu 24.04 LTS"}),
 "ubuntu_std":     rep({"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Ubuntu 24.04 LTS"}, have=("conky", "curl"), probe="X11:\n * Xinerama\n"),
 "arch_nocairo":   rep({"ID": "arch", "PRETTY_NAME": "Arch Linux"}, have=("conky", "curl", "sensors", "playerctl", "smartctl"), probe="X11:\n * Xinerama\n"),
 "fedora_atomic":  rep({"ID": "fedora", "VARIANT_ID": "silverblue", "PRETTY_NAME": "Fedora Linux 43 (Silverblue)"}, exists=lambda p: p == "/run/ostree-booted"),
 "all_ok":         rep({"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "Ubuntu 24.04 LTS"}, have=("conky", "curl", "sensors", "playerctl", "smartctl"), probe=CAIRO, helper=(True, False)),
}
shots = {}
for name, r in cases.items():
    for popup in (True, False):
        if name == "all_ok" and popup: continue
        d = DependenciesDialog(r, popup=popup); d.show(); app.processEvents()
        shots[f"{name}{'_popup' if popup else ''}"] = d.grab()
        t = d.intro.text()
        check(f"[{name}/{popup}] intro mentions distro", (r.pretty_name in t))
        if r.missing:
            check(f"[{name}/{popup}] intro matches requested wording", "you are missing packages" in t and "limit your experience on Conky Studio" in t and "copy and paste into your terminal" in t, t[:80])
        else:
            check(f"[{name}] all-ok text", "everything Conky Studio needs is installed" in t)
        check(f"[{name}/{popup}] popup buttons", hasattr(d, "never_btn") == popup)
        if r.missing and r.command():
            check(f"[{name}] command shown", r.command() in d.cmd_box.toPlainText(), d.cmd_box.toPlainText())
            check(f"[{name}] copy enabled", d.copy_btn.isEnabled())
        if name == "arch_nocairo": check("arch no-cairo: no command, copy disabled, note shown", not d.copy_btn.isEnabled() and "Lua-Cairo" in d.notes.text())
        if name == "fedora_atomic": check("immutable: auto-install disabled with reason", not d.auto_btn.isEnabled() and "immutable" in d.auto_btn.toolTip(), d.auto_btn.toolTip())
        if name == "ubuntu_nothing": check("auto-install enabled (pkexec present)", d.auto_btn.isEnabled())
        if name == "all_ok": check("all-ok hides command area; helper section only in Tools version", not d.cmd_box.isVisible() and d.helper_box.isVisible() and "installed" in d.helper_text.text())
        if popup: check(f"[{name}] popup hides the helper section", not d.helper_box.isVisible())
        check(f"[{name}/{popup}] package list shows every row (no scrollbar)", d.tree.height() >= d.tree.topLevelItemCount() * 26)
        d.close()
# arch, Conky lacks Cairo AND other tools missing: command covers only what we can name (never conky)
r2 = rep({"ID": "arch", "PRETTY_NAME": "Arch Linux"}, have=("conky",), probe="X11:\n * Xinerama\n")
check("arch no-cairo + missing extras: command excludes conky", r2.command().startswith("sudo pacman -S --needed curl lm_sensors") and " conky" not in r2.command().replace("curl", ""), r2.command())
# unticking a recommended package shrinks the command
d = DependenciesDialog(cases["ubuntu_nothing"], popup=True); before = d.cmd_box.toPlainText()
for i in range(d.tree.topLevelItemCount()):
    row = d.tree.topLevelItem(i)
    if row.data(0, 0x100) == "playerctl": row.setCheckState(0, Qt.CheckState.Unchecked)
after = d.cmd_box.toPlainText()
check("untick removes package from command", "playerctl" in before and "playerctl" not in after and "conky-all" in after, after)
# never_btn sets the flag
d._never(); check("don't-ask-again flag", d.dont_ask_again)

# ---- popup frequency rules (MainWindow._maybe_show_deps_popup) ----
from conkystudio.ui import main_window as MW
shown = []
class FakeDlg:
    next_never = False
    def __init__(self, report, popup=False, parent=None): self.report = report; self.dont_ask_again = False
    def exec(self): shown.append(self.report.signature); self.dont_ask_again = FakeDlg.next_never
MW.DependenciesDialog = FakeDlg
class FakeSB:  # statusBar stub
    def showMessage(self, *a, **k): pass
class Fake: 
    statusBar = lambda self: FakeSB()
fake = Fake(); call = lambda: MW.MainWindow._handle_deps_report(fake, deps.build_report())
def with_report(r):
    deps.build_report = lambda *a, **k: r
settings.set_bool("deps/suppress_popup", False); settings.set_str("deps/last_prompted", "")
with_report(cases["ubuntu_nothing"]); call(); call()
check("required missing: shown on every launch", len(shown) == 2, shown)
FakeDlg.next_never = True; call(); FakeDlg.next_never = False
check("'Don't ask again' stored", settings.get_bool("deps/suppress_popup") and len(shown) == 3)
n = len(shown); call(); check("suppressed: not shown again", len(shown) == n)
settings.set_bool("deps/suppress_popup", False); settings.set_str("deps/last_prompted", ""); shown.clear()
rec_only = rep({"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "U"}, have=("conky",), probe=CAIRO)
with_report(rec_only); call(); call(); call()
check("optional-only: shown once, then never nags", len(shown) == 1, shown)
rec_other = rep({"ID": "ubuntu", "ID_LIKE": "debian", "PRETTY_NAME": "U"}, have=("conky", "curl"), probe=CAIRO)
with_report(rec_other); call(); check("optional-only: a different missing set is announced once", len(shown) == 2, shown)
shown.clear(); with_report(cases["all_ok"]); call(); check("nothing missing: silent", not shown)
MW.MainWindow._handle_deps_report(fake, None); check("failed detection (None) never breaks startup", not shown)
# the startup check is threaded and honours the env switch
started = []
class FakeWorker:
    def __init__(self, parent=None): self.done = type("S", (), {"connect": lambda s, f: None})()
    def start(self): started.append(1)
MW.DepsCheckWorker = FakeWorker
class Fake2:
    _handle_deps_report = lambda self, r: None
f2 = Fake2(); MW.MainWindow._maybe_show_deps_popup(f2); check("startup check uses a worker thread", started == [1] and hasattr(f2, "_deps_worker"))
os.environ["CONKY_STUDIO_NO_DEPS_POPUP"] = "1"; MW.MainWindow._maybe_show_deps_popup(Fake2()); check("env switch skips the check entirely", started == [1]); del os.environ["CONKY_STUDIO_NO_DEPS_POPUP"]

# ---- Manager: Start at login ----
th = os.path.join(HOME, ".config", "conky", "My Theme"); os.makedirs(th)
open(th + "/start.sh", "w").write("#!/bin/sh\ntrue\n"); os.chmod(th + "/start.sh", 0o755); open(th + "/conky.conf", "w").write("conky.config={}\nconky.text=[[]]\n")
json.dump({"name": "My Theme"}, open(th + "/theme.json", "w"))
nost = os.path.join(HOME, ".config", "conky", "NoStart"); os.makedirs(nost); open(nost + "/conky.conf", "w").write("x")
from conkystudio.ui.manager_tab import ManagerTab
from conkystudio.manager import autostart as A
tab = ManagerTab(); tab.show(); tab.refresh(); app.processEvents()
def select(path):
    for i in range(tab.list_widget.count()):
        if tab.list_widget.item(i).data(0x100) == path: tab.list_widget.setCurrentRow(i); app.processEvents(); return True
check("manager lists test theme", select(th))
check("checkbox enabled for theme with start.sh", tab.autostart_chk.isEnabled() and not tab.autostart_chk.isChecked())
tab.autostart_delay.setValue(7); tab.autostart_chk.setChecked(True); app.processEvents()
check("toggle on creates entry + launcher", A.is_enabled(th) and os.path.isfile(A.script_path(th)) and A.configured_delay(th) == 7)
tab.autostart_delay.setValue(11); check("changing delay rewrites launcher", A.configured_delay(th) == 11 and "sleep 11" in open(A.script_path(th)).read())
select(nost); check("theme without start.sh: control disabled", not tab.autostart_chk.isEnabled())
select(th); check("state restored on reselect", tab.autostart_chk.isChecked() and tab.autostart_delay.value() == 11)
tab.autostart_chk.setChecked(False); check("toggle off removes both files", not A.is_enabled(th) and not os.path.exists(A.script_path(th)))
tab.autostart_chk.setChecked(True); QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
tab._uninstall_selected(); check("uninstall removes the autostart entry too", not os.path.exists(A.entry_path(th)) and not os.path.exists(A.script_path(th)) and not os.path.isdir(th))
shots["manager"] = tab.grab()

# montage of screenshots
from PyQt6.QtGui import QImage, QPainter, QColor
keys = ["ubuntu_nothing_popup", "ubuntu_std", "arch_nocairo_popup", "fedora_atomic", "all_ok"]
imgs = [shots[k].toImage() for k in keys]; W = max(i.width() for i in imgs); 
out = QImage(W * 2 + 30, sum(sorted([i.height() for i in imgs])[::-1][::2]) + 40, QImage.Format.Format_ARGB32); out.fill(QColor("#0b0d10"))
p = QPainter(out); y = [10, 10]
for n, im in enumerate(imgs): c = n % 2; p.drawImage(10 + c * (W + 10), y[c], im); y[c] += im.height() + 10
p.end(); out.save(sys.argv[1] if len(sys.argv) > 1 else "/tmp/deps_dialogs.png"); shots["manager"].save("/tmp/manager_tab.png")
print(f"{'FAIL' if fails else 'PASS'}: {len(fails)} failure(s)"); [print("  -", f) for f in fails]; sys.exit(1 if fails else 0)
