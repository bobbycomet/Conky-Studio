"""
"Missing packages" dialog -- shown as a one-time popup at startup (when something is
missing) and always available from Tools -> Missing packages.

It never installs anything by itself: it shows the exact terminal command, lets you copy
it, and -- only if you click -- can run it through pkexec (polkit's graphical admin prompt).
"""
from __future__ import annotations

import os
import shlex

from PyQt6.QtCore import Qt, QObject, QProcess, QProcessEnvironment, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from conkystudio.hardware import deps


def clean_env() -> QProcessEnvironment:
    """The AppImage's bootloader points LD_LIBRARY_PATH at its own libs; strip it so pkexec,
    sh and the package manager load the system's libraries (same reason live_preview does)."""
    env = QProcessEnvironment.systemEnvironment()
    for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.remove(k)
    return env


class DepsCheckWorker(QThread):
    """Runs the (subprocess-based) package check off the UI thread so a slow `conky --version`
    can never freeze the window at startup. Keep a reference until `done` fires."""
    done = pyqtSignal(object)            # DepsReport, or None if detection failed

    def run(self):
        try:
            self.done.emit(deps.build_report())
        except Exception:
            self.done.emit(None)


class DependenciesDialog(QDialog):
    def __init__(self, report: "deps.DepsReport | None" = None, popup: bool = False, parent=None):
        super().__init__(parent)
        self.report = report or deps.build_report()
        self.popup = popup
        self.dont_ask_again = False
        self._proc: QProcess | None = None
        self.setWindowTitle("Missing packages" if popup else "Packages Conky Studio uses")
        self.setMinimumWidth(720)

        root = QVBoxLayout(self)
        self.intro = QLabel()
        self.intro.setWordWrap(True)
        self.intro.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(self.intro)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Package", "What it is for", "Status"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 300)
        self.tree.setColumnWidth(1, 250)
        self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.itemChanged.connect(self._update_command)
        root.addWidget(self.tree)

        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setProperty("role", "caption")
        root.addWidget(self.notes)

        self.cmd_label = QLabel("Command to run in a terminal:")
        root.addWidget(self.cmd_label)
        self.cmd_box = QPlainTextEdit()
        self.cmd_box.setReadOnly(True)
        mono = QFont("monospace"); mono.setStyleHint(QFont.StyleHint.Monospace)
        self.cmd_box.setFont(mono)
        self.cmd_box.setMaximumHeight(64)
        root.addWidget(self.cmd_box)

        row = QHBoxLayout()
        self.copy_btn = QPushButton("Copy command")
        self.copy_btn.setObjectName("primary")
        self.copy_btn.clicked.connect(self._copy)
        self.auto_btn = QPushButton("Install automatically\u2026")
        self.auto_btn.clicked.connect(self._install_auto)
        self.recheck_btn = QPushButton("Recheck")
        self.recheck_btn.clicked.connect(self._recheck)
        row.addWidget(self.copy_btn); row.addWidget(self.auto_btn); row.addStretch(1); row.addWidget(self.recheck_btn)
        root.addLayout(row)

        self.helper_box = QGroupBox("Optional: admin helper (polkit)")
        hl = QVBoxLayout(self.helper_box)
        self.helper_text = QLabel()
        self.helper_text.setWordWrap(True)
        self.helper_text.setProperty("role", "caption")
        hl.addWidget(self.helper_text)
        hrow = QHBoxLayout()
        self.helper_install_btn = QPushButton("Set up admin helper\u2026")
        self.helper_install_btn.clicked.connect(self._helper_setup)
        self.helper_remove_btn = QPushButton("Remove admin helper\u2026")
        self.helper_remove_btn.clicked.connect(self._helper_remove)
        hrow.addWidget(self.helper_install_btn); hrow.addWidget(self.helper_remove_btn); hrow.addStretch(1)
        hl.addLayout(hrow)
        root.addWidget(self.helper_box)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        self.log.setVisible(False)
        root.addWidget(self.log)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        if popup:
            self.later_btn = QPushButton("Not now")
            self.later_btn.clicked.connect(self.reject)
            self.never_btn = QPushButton("Don't ask again")
            self.never_btn.setToolTip("You can always get these commands later from Tools \u2192 Missing packages.")
            self.never_btn.clicked.connect(self._never)
            bottom.addWidget(self.later_btn); bottom.addWidget(self.never_btn)
        else:
            close = QPushButton("Close"); close.clicked.connect(self.accept)
            bottom.addWidget(close)
        root.addLayout(bottom)

        self._populate()

    # ---- content -----------------------------------------------------------
    def _populate(self) -> None:
        r = self.report
        distro = r.pretty_name or r.distro_id or "this system"
        miss_req, miss_rec = r.missing_required, r.missing_recommended
        if r.missing:
            self.intro.setText(
                f"Looks like you are on <b>{distro}</b>, but you are missing packages, and that will "
                "limit your experience on Conky Studio.<br><br>"
                "Would you like the commands to copy and paste into your terminal?")
        else:
            self.intro.setText(f"<b>{distro}</b>: everything Conky Studio needs is installed. \u2713")

        self.tree.blockSignals(True)
        self.tree.clear()
        for it in r.items:
            status = {"ok": "installed \u2713", "missing": "missing", "no-cairo": "installed, but no Lua-Cairo",
                      "unknown": "installed (version unreadable)"}[it.state]
            row = QTreeWidgetItem([it.label + ("  (required)" if it.level == "required" else ""), it.purpose, status])
            row.setData(0, Qt.ItemDataRole.UserRole, it.key)
            if it.needs_install and it.packages:
                row.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                row.setCheckState(0, Qt.CheckState.Checked)
                if it.level == "required":
                    row.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            else:
                row.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if not it.needs_install:
                for c in range(3):
                    row.setForeground(c, self.palette().mid())
            self.tree.addTopLevelItem(row)
        self.tree.blockSignals(False)

        self.notes.setText("\n".join(r.notes))
        self.notes.setVisible(bool(r.notes))
        self.tree.setVisible(True)
        rows = max(1, self.tree.topLevelItemCount())
        row_h = self.tree.sizeHintForRow(0) if rows else 24
        self.tree.setFixedHeight(self.tree.header().height() + rows * max(row_h, 26) + 10)
        self._update_command()
        self._update_helper_box()
        self.layout().activate()
        self.adjustSize()

    def _selected_keys(self) -> list:
        keys = []
        for i in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(i)
            if row.flags() & Qt.ItemFlag.ItemIsUserCheckable and row.checkState(0) == Qt.CheckState.Checked:
                keys.append(row.data(0, Qt.ItemDataRole.UserRole))
        return keys

    def _update_command(self, *_a) -> None:
        keys = self._selected_keys()
        cmd = self.report.command(set(keys)) if keys else ""
        has_missing = bool(self.report.missing)
        self.cmd_label.setVisible(has_missing)
        self.cmd_box.setVisible(has_missing)
        self.copy_btn.setVisible(has_missing)
        if has_missing:
            self.cmd_box.setPlainText(cmd or "(No single command is known for this system \u2014 see the notes above.)")
        self.copy_btn.setEnabled(bool(cmd))
        can_auto = self.report.can_auto_install and bool(cmd) and self._proc is None
        self.auto_btn.setVisible(has_missing)
        self.auto_btn.setEnabled(can_auto)
        if not self.report.can_auto_install:
            why = ("this system is image-based/immutable" if self.report.immutable else
                   "pkexec (polkit) was not found" if self.report.family in deps.INSTALLABLE_FAMILIES else
                   "automatic install is not available for this distribution")
            self.auto_btn.setToolTip(f"Not available: {why}. Use the copied command in a terminal instead.")
        else:
            self.auto_btn.setToolTip("Asks for your password through the system's graphical prompt (pkexec).")

    def _update_helper_box(self) -> None:
        r = self.report
        show = (not self.popup) and r.family in deps.INSTALLABLE_FAMILIES and not r.immutable and (r.pkexec or r.is_root)
        self.helper_box.setVisible(show)
        if not show:
            return
        if r.helper_installed:
            state = "installed" + (" (an older version \u2014 re-run setup to update it)" if r.helper_outdated else "")
        else:
            state = "not installed"
        self.helper_text.setText(
            "Without it, \u201cInstall automatically\u201d asks pkexec to run a fixed installer once. With it, a small "
            "root-owned script plus a polkit policy (two plain files) give a clearer prompt and one approval per "
            "session. It can only install this fixed list of packages, and removing it is one click.\n"
            f"Files: {deps.HELPER_PATH}  and  {deps.POLICY_PATH}\nStatus: {state}.")
        self.helper_install_btn.setText("Update admin helper\u2026" if r.helper_installed else "Set up admin helper\u2026")
        self.helper_remove_btn.setEnabled(r.helper_installed)

    # ---- actions -----------------------------------------------------------
    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.cmd_box.toPlainText())
        self.copy_btn.setText("Copied \u2713")

    def _never(self) -> None:
        self.dont_ask_again = True
        self.reject()

    def _recheck(self) -> None:
        self.report = deps.build_report()
        self._populate()

    def _confirm(self, title: str, argv: list, extra: str = "") -> bool:
        shown = " ".join(shlex.quote(a) if len(a) < 80 else "<installer script>" for a in argv)
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(f"{extra}\n\nThis will run (you will be asked for your password):\n{shown}")
        box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        return box.exec() == QMessageBox.StandardButton.Ok

    def _install_auto(self) -> None:
        keys = self._selected_keys()
        if not keys:
            return
        try:
            argv = deps.install_argv(keys, use_helper=self.report.helper_installed and not self.report.helper_outdated,
                                     is_root=self.report.is_root)
        except ValueError as exc:
            QMessageBox.warning(self, "Install", str(exc)); return
        if self._confirm("Install packages", argv, "Install: " + ", ".join(keys)):
            self._run(argv, "Installing\u2026")

    def _helper_setup(self) -> None:
        argv = deps.helper_setup_argv(self.report.is_root)
        if self._confirm("Set up admin helper", argv,
                         f"Creates two plain files:\n  {deps.HELPER_PATH}\n  {deps.POLICY_PATH}"):
            self._run(argv, "Setting up the admin helper\u2026")

    def _helper_remove(self) -> None:
        argv = deps.helper_remove_argv(self.report.is_root)
        if self._confirm("Remove admin helper", argv, "Deletes the two helper files; nothing else changes."):
            self._run(argv, "Removing the admin helper\u2026")

    def _run(self, argv: list, title: str) -> None:
        self.log.setVisible(True)
        self.log.setPlainText(title + "\n")
        for b in (self.auto_btn, self.helper_install_btn, self.helper_remove_btn, self.recheck_btn):
            b.setEnabled(False)
        p = QProcess(self)
        p.setProcessEnvironment(clean_env())
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        p.readyRead.connect(lambda: self.log.appendPlainText(bytes(p.readAll()).decode("utf-8", "replace").rstrip()))
        p.errorOccurred.connect(lambda _e: self.log.appendPlainText(f"[could not start {argv[0]}: {p.errorString()}]"))
        p.finished.connect(self._run_finished)
        self._proc = p
        p.start(argv[0], argv[1:])

    def _run_finished(self, code: int, _status) -> None:
        self._proc = None
        self.log.appendPlainText("\nDone." if code == 0 else f"\nFinished with exit code {code}.")
        if code in (126, 127):
            self.log.appendPlainText("(pkexec was dismissed, has no authentication agent, or the command was not found.)")
        self._recheck()
