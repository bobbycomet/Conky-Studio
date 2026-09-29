"""
The Store tab. Two sources:

  1. Theme Vault — manifest.json + $ref'd Themes/*.json (see store/theme_vault.py
     and theme-vault/THEME_SCHEMA.md). This IS the Community Store: Install
     actually downloads and installs, via store/theme_vault_install.py --
     GitHub entries come from the repo's latest Release, Pling/openDesktop
     entries are handed off to the (unchanged) OCS pipeline below. Hosts with
     no generic download path (GitLab, KDE Store, GNOME Look, XFCE Look,
     Other) fall back to "Get it ↗", which just opens the link.
  2. OpenDesktop / Pling live OCS API search + install, via store/ocs_install.py.
     Unchanged -- this is also what Theme Vault entries hosted on Pling/
     openDesktop are routed through under the hood.

store/client.py + store/index_schema.py (the older sha256-verified
download-and-install pipeline for a static index.json) are superseded by
Theme Vault + theme_vault_install.py for this tab.
"""
from __future__ import annotations

import base64

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter,
    QTabWidget, QComboBox, QTextBrowser, QFrame, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices

from conkystudio.store import theme_vault
from conkystudio.store.theme_vault_install import install_theme_vault_entry
from conkystudio.store.ocs_client import (
    OcsClient, OcsContent, OcsError, OcsRateLimited, provider_base,
)
from conkystudio.store.ocs_handler import install_content

# Hosts theme_vault_install.py actually knows how to fetch. Everything else
# only gets the "Get it ↗" link-out button.
INSTALLABLE_HOSTS = ("GitHub", "Pling", "openDesktop")

THEME_VAULT_STORE_URL = "https://bobbycomet.github.io/Conky-Studio-Theme-Community-Store/#/"


# ===========================================================================
# Theme Vault (manifest.json + $ref'd Themes/*.json)
# ===========================================================================

class _ThemeVaultFetchThread(QThread):
    done = pyqtSignal(list, str)  # list[ThemeVaultEntry], error message

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            entries = theme_vault.fetch_manifest(self.url)
            self.done.emit(entries, "")
        except theme_vault.ThemeVaultError as e:
            self.done.emit([], str(e))


class _ThemeVaultDetailThread(QThread):
    """Fetch one entry's preview image + README off the UI thread."""

    done = pyqtSignal(object, object, str, str)  # entry, preview_bytes|None, readme_text, readme_error

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry

    def run(self):
        preview_bytes = theme_vault.fetch_preview_bytes(self.entry)
        readme_text, readme_error = "", ""
        try:
            readme_text = theme_vault.fetch_readme(self.entry)
        except theme_vault.ThemeVaultError as e:
            readme_error = str(e)
        self.done.emit(self.entry, preview_bytes, readme_text, readme_error)


class _ThemeVaultInstallWorker(QThread):
    finished_ok = pyqtSignal(object)  # InstallResult
    finished_err = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry

    def run(self):
        try:
            result = install_theme_vault_entry(
                self.entry,
                progress=lambda m: self.progress.emit(m),
            )
            self.finished_ok.emit(result)
        except Exception as e:
            self.finished_err.emit(str(e))


class ThemeVaultPanel(QWidget):
    """
    The Community Store: browse the Theme Vault catalog and install directly.
    "Install" downloads and installs for GitHub/Pling/openDesktop entries
    (see theme_vault_install.py); anything else falls back to "Get it ↗",
    which just opens the theme's actual home in the system browser.
    """

    theme_installed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries: list = []
        self._selected = None
        self._fetch_thread = None
        self._detail_thread = None
        self._install_thread = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        heading = QLabel("Theme Vault")
        heading.setProperty("role", "heading")
        outer.addWidget(heading)

        blurb = QLabel(
            "Themes from GitHub, Pling, KDE Store, openDesktop, and more. Install downloads and "
            "sets up the theme under ~/.config/conky/ for GitHub, Pling, and openDesktop entries; "
            "other hosts open in your browser instead since there's no generic way to fetch from them."
        )
        blurb.setProperty("role", "caption")
        blurb.setWordWrap(True)
        outer.addWidget(blurb)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Catalog"))
        self.catalog_box = QComboBox()
        self.catalog_box.addItem("Official pack", "official")
        self.catalog_box.addItem("Community pack", "community")
        self.catalog_box.currentIndexChanged.connect(self._on_catalog_changed)
        bar.addWidget(self.catalog_box)

        self.url_edit = QLineEdit(theme_vault.DEFAULT_CATALOGS["official"])
        bar.addWidget(self.url_edit, 1)

        fetch_btn = QPushButton("Browse")
        fetch_btn.setObjectName("primary")
        fetch_btn.clicked.connect(self._fetch)
        bar.addWidget(fetch_btn)

        visit_store_btn = QPushButton("Visit Store \u2197")
        visit_store_btn.setToolTip("Open the Theme Vault website in your browser")
        visit_store_btn.clicked.connect(self._open_store_website)
        bar.addWidget(visit_store_btn)
        outer.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.list_widget)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.detail_view = QTextBrowser()
        self.detail_view.setOpenExternalLinks(True)
        detail_layout.addWidget(self.detail_view, 1)

        btn_row = QHBoxLayout()
        self.install_btn = QPushButton("Install")
        self.install_btn.setObjectName("primary")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self._install)
        btn_row.addWidget(self.install_btn)

        self.get_btn = QPushButton("Get it \u2197")
        self.get_btn.setEnabled(False)
        self.get_btn.clicked.connect(self._open_link)
        btn_row.addWidget(self.get_btn)
        btn_row.addStretch(1)
        detail_layout.addLayout(btn_row)

        self.status = QLabel("")
        self.status.setProperty("role", "caption")
        self.status.setWordWrap(True)
        detail_layout.addWidget(self.status)

        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _on_catalog_changed(self, _idx):
        key = self.catalog_box.currentData()
        if key in theme_vault.DEFAULT_CATALOGS:
            self.url_edit.setText(theme_vault.DEFAULT_CATALOGS[key])
            self._fetch()

    def _open_store_website(self):
        QDesktopServices.openUrl(QUrl(THEME_VAULT_STORE_URL))

    def _fetch(self):
        self.list_widget.clear()
        self.detail_view.setHtml("<p>Fetching\u2026</p>")
        self.get_btn.setEnabled(False)
        self._fetch_thread = _ThemeVaultFetchThread(self.url_edit.text().strip())
        self._fetch_thread.done.connect(self._on_fetched)
        self._fetch_thread.start()

    def _on_fetched(self, entries: list, error: str):
        if error:
            self.detail_view.setHtml(f"<p>Couldn't load Theme Vault:<br>{_esc(error)}</p>")
            return
        self.entries = entries
        self.list_widget.clear()
        for entry in entries:
            label = entry.display_name
            if entry.author:
                label += f"  \u00b7  {entry.author}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(f"{entry.host} \u00b7 {entry.description[:200]}")
            self.list_widget.addItem(item)
        self.detail_view.setHtml(
            f"<p>{len(entries)} theme(s) available.</p>" if entries else "<p>No themes listed yet.</p>"
        )

    def _on_selection_changed(self, *_args):
        item = self.list_widget.currentItem()
        if item is None:
            self.install_btn.setEnabled(False)
            self.get_btn.setEnabled(False)
            self._selected = None
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        self._selected = entry
        self.status.setText("")

        installable = bool(entry.link) and entry.host in INSTALLABLE_HOSTS
        self.install_btn.setEnabled(installable)
        self.install_btn.setText(f"Install from {entry.host}" if installable else "Install")
        if not installable:
            self.install_btn.setToolTip(
                f"Theme Vault can't auto-install from {entry.host or 'this host'} -- use \"Get it ↗\" instead."
            )
        else:
            self.install_btn.setToolTip("")

        self.get_btn.setEnabled(bool(entry.link))
        self.get_btn.setText(f"Get it on {entry.host} \u2197" if entry.host else "Get it \u2197")
        self.detail_view.setHtml(self._render_summary(entry) + "<p><i>Loading preview and README\u2026</i></p>")
        self._detail_thread = _ThemeVaultDetailThread(entry)
        self._detail_thread.done.connect(self._on_detail_loaded)
        self._detail_thread.start()

    def _render_summary(self, entry) -> str:
        meta_bits = [f"Author: {_esc(entry.author or 'unattributed')}"]
        if entry.version:
            meta_bits.append(f"Version: {_esc(entry.version)}")
        meta_bits.append(f"Host: {_esc(entry.host)}")
        if entry.resolution:
            meta_bits.append(f"Built for: {_esc(entry.resolution)}")
        if entry.conky_version:
            meta_bits.append(f"Conky: {_esc(entry.conky_version)}")
        if entry.license:
            meta_bits.append(f"License: {_esc(entry.license)}")

        tags_html = " ".join(f"<code>{_esc(t)}</code>" for t in entry.tags)

        plugins_html = ""
        if entry.plugins:
            chips = " ".join(f"<code>{_esc(p)}</code>" for p in entry.plugins)
            plugins_html = (
                f"<p><b>Uses these plugins:</b><br>{chips}<br>"
                f"<i>Install these from Node Vault before trying this theme.</i></p>"
            )

        return (
            f"<h3>{_esc(entry.display_name)}</h3>"
            f"<p>{' &nbsp;|&nbsp; '.join(meta_bits)}</p>"
            f"{'<p>' + tags_html + '</p>' if tags_html else ''}"
            f"<p>{_esc(entry.description)}</p>"
            f"{plugins_html}"
        )

    def _on_detail_loaded(self, entry, preview_bytes, readme_text, readme_error):
        if entry is not self._selected:
            return  # selection moved on while this was in flight
        preview_html = ""
        if preview_bytes:
            b64 = base64.b64encode(preview_bytes).decode("ascii")
            preview_html = f'<p><img src="data:image/png;base64,{b64}" width="320"/></p>'
        if readme_error:
            readme_html = (
                f"<p>Couldn't load the README ({_esc(readme_error)}). "
                f"<a href=\"{_esc(entry.readme_url)}\">Open it directly</a></p>"
            )
        else:
            readme_html = theme_vault.render_readme_html(readme_text)

        self.detail_view.setHtml(
            self._render_summary(entry) + preview_html + "<hr/><h3>README</h3>" + readme_html
        )

    def _open_link(self):
        if self._selected and self._selected.link:
            QDesktopServices.openUrl(QUrl(self._selected.link))

    def _install(self):
        if not self._selected:
            return
        entry = self._selected
        self.install_btn.setEnabled(False)
        self.get_btn.setEnabled(False)
        self.status.setText(f"Installing '{entry.display_name}'\u2026")
        self._install_thread = _ThemeVaultInstallWorker(entry)
        self._install_thread.progress.connect(self.status.setText)
        self._install_thread.finished_ok.connect(self._on_install_ok)
        self._install_thread.finished_err.connect(self._on_install_err)
        self._install_thread.start()

    def _on_install_ok(self, result):
        self.get_btn.setEnabled(bool(self._selected and self._selected.link))
        self.install_btn.setEnabled(bool(
            self._selected and self._selected.link and self._selected.host in INSTALLABLE_HOSTS
        ))
        self.status.setText(result.message)
        if result.success:
            QMessageBox.information(
                self, "Installed",
                f"{result.message}\n\nSwitch to the Manager tab to launch it.",
            )
            self.theme_installed.emit()
        else:
            QMessageBox.warning(self, "Install failed", result.message)

    def _on_install_err(self, err: str):
        self.get_btn.setEnabled(bool(self._selected and self._selected.link))
        self.install_btn.setEnabled(bool(
            self._selected and self._selected.link and self._selected.host in INSTALLABLE_HOSTS
        ))
        self.status.setText(err)
        QMessageBox.warning(self, "Install failed", err)


# ===========================================================================
# OpenDesktop / Pling (OCS)
# ===========================================================================

class _OcsSearchWorker(QThread):
    finished_ok = pyqtSignal(list)
    finished_err = pyqtSignal(str)

    def __init__(self, base_url: str, query: str, pagesize: int = 30, parent=None):
        super().__init__(parent)
        self.base_url = base_url
        self.query = query
        self.pagesize = pagesize

    def run(self):
        try:
            client = OcsClient(self.base_url)
            hits = client.search(query=self.query or "conky", pagesize=self.pagesize)
            self.finished_ok.emit(hits)
        except OcsRateLimited as e:
            self.finished_err.emit(f"Rate limited: {e}")
        except OcsError as e:
            self.finished_err.emit(str(e))
        except Exception as e:
            self.finished_err.emit(f"Unexpected error: {e}")


class _OcsDetailWorker(QThread):
    finished_ok = pyqtSignal(object)
    finished_err = pyqtSignal(str)

    def __init__(self, base_url: str, content_id: str, parent=None):
        super().__init__(parent)
        self.base_url = base_url
        self.content_id = content_id

    def run(self):
        try:
            client = OcsClient(self.base_url)
            self.finished_ok.emit(client.get(self.content_id))
        except OcsError as e:
            self.finished_err.emit(str(e))
        except Exception as e:
            self.finished_err.emit(f"Unexpected error: {e}")


class _OcsInstallWorker(QThread):
    finished_ok = pyqtSignal(object)
    finished_err = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, content: OcsContent, parent=None):
        super().__init__(parent)
        self.content = content

    def run(self):
        try:
            result = install_content(
                self.content,
                progress=lambda m: self.progress.emit(m),
            )
            self.finished_ok.emit(result)
        except Exception as e:
            self.finished_err.emit(str(e))


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class OcsPanel(QWidget):
    """Live Pling / openDesktop browser via OCS."""

    theme_installed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results: list[OcsContent] = []
        self._selected: OcsContent | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        heading = QLabel("OpenDesktop / Pling")
        heading.setProperty("role", "heading")
        root.addWidget(heading)

        blurb = QLabel(
            "Search live content on Pling and openDesktop (OCS API). "
            "Install places themes under ~/.config/conky/, then use the Manager tab to launch them. "
            "Browser links using ocs:// also open here when Conky Studio is registered as the handler."
        )
        blurb.setProperty("role", "caption")
        blurb.setWordWrap(True)
        root.addWidget(blurb)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Provider"))
        self.provider = QComboBox()
        self.provider.addItem("Pling", "pling")
        self.provider.addItem("openDesktop", "opendesktop")
        self.provider.setMinimumWidth(140)
        bar.addWidget(self.provider)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search (default: conky)\u2026")
        self.search_edit.returnPressed.connect(self.run_search)
        bar.addWidget(self.search_edit, 1)

        self.search_btn = QPushButton("Search")
        self.search_btn.setObjectName("primary")
        self.search_btn.clicked.connect(self.run_search)
        bar.addWidget(self.search_btn)

        self.open_web_btn = QPushButton("Open website")
        self.open_web_btn.setToolTip("Open the provider in your browser")
        self.open_web_btn.clicked.connect(self._open_website)
        bar.addWidget(self.open_web_btn)
        root.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.itemSelectionChanged.connect(self._on_select)
        split.addWidget(self.list)

        right = QFrame()
        right.setFrameShape(QFrame.Shape.StyledPanel)
        right_l = QVBoxLayout(right)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        right_l.addWidget(self.detail, 1)

        btn_row = QHBoxLayout()
        self.install_btn = QPushButton("Install theme")
        self.install_btn.setObjectName("primary")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self._install)
        btn_row.addWidget(self.install_btn)

        self.page_btn = QPushButton("View on site")
        self.page_btn.setEnabled(False)
        self.page_btn.clicked.connect(self._open_detail_page)
        btn_row.addWidget(self.page_btn)
        btn_row.addStretch(1)
        right_l.addLayout(btn_row)
        split.addWidget(right)

        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        root.addWidget(split, 1)

        self.status = QLabel("Ready. press Search to browse Pling for “conky”.")
        self.status.setProperty("role", "caption")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def _base_url(self) -> str:
        return provider_base(self.provider.currentData() or "pling")

    def _set_busy(self, busy: bool, msg: str = ""):
        self.search_btn.setEnabled(not busy)
        self.search_edit.setEnabled(not busy)
        self.provider.setEnabled(not busy)
        if msg:
            self.status.setText(msg)

    def run_search(self):
        q = self.search_edit.text().strip() or "conky"
        self._set_busy(True, f"Searching for “{q}”\u2026")
        self.list.clear()
        self._results = []
        self._selected = None
        self.install_btn.setEnabled(False)
        self.page_btn.setEnabled(False)
        self.detail.clear()

        worker = _OcsSearchWorker(self._base_url(), q, parent=self)
        worker.finished_ok.connect(self._on_search_ok)
        worker.finished_err.connect(self._on_search_err)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_search_ok(self, hits: list):
        self._set_busy(False)
        self._results = list(hits)
        if not hits:
            self.status.setText("No results. Try another query or provider.")
            return
        for c in hits:
            label = c.name or f"#{c.id}"
            if c.author:
                label += f"  —  {c.author}"
            if c.looks_like_conky():
                label = "★ " + label
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            item.setToolTip(c.summary or (c.description[:200] if c.description else ""))
            self.list.addItem(item)
        self.status.setText(f"{len(hits)} result(s). ★ = mentions Conky in name/description.")

    def _on_search_err(self, err: str):
        self._set_busy(False, err)
        QMessageBox.warning(self, "OpenDesktop / Pling", err)

    def _on_select(self):
        items = self.list.selectedItems()
        if not items:
            self._selected = None
            self.install_btn.setEnabled(False)
            self.page_btn.setEnabled(False)
            return
        cid = items[0].data(Qt.ItemDataRole.UserRole)
        stub = next((x for x in self._results if x.id == cid), None)
        if stub:
            self.detail.setHtml(
                f"<h3>{_esc(stub.name)}</h3>"
                f"<p><i>{_esc(stub.summary or '')}</i></p>"
                f"<p>{_esc((stub.description or '')[:600])}</p>"
                f"<p>Loading download links\u2026</p>"
            )
        self._set_busy(True, "Loading details\u2026")
        worker = _OcsDetailWorker(self._base_url(), str(cid), parent=self)
        worker.finished_ok.connect(self._on_detail_ok)
        worker.finished_err.connect(self._on_detail_err)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_detail_ok(self, content: OcsContent):
        self._set_busy(False, "Ready.")
        self._selected = content
        self._results = [content if x.id == content.id else x for x in self._results]

        if content.downloads:
            dl_html = "<ul>" + "".join(
                f"<li>{_esc(d.name)} <small>({_esc(d.size)})</small></li>"
                for d in content.downloads
            ) + "</ul>"
        else:
            dl_html = "<p><b>No download links on this item.</b></p>"

        preview = ""
        if content.preview_url:
            preview = f'<p><img src="{_esc(content.preview_url)}" style="max-width:280px;"/></p>'

        self.detail.setHtml(
            f"<h3>{_esc(content.name)}</h3>{preview}"
            f"<p><i>{_esc(content.summary or '')}</i></p>"
            f"<p>{_esc(content.description or '')}</p>"
            f"<p>Author: {_esc(content.author)} &nbsp;|&nbsp; "
            f"Version: {_esc(content.version)} &nbsp;|&nbsp; Score: {_esc(content.score)}</p>"
            f"<p><b>Files</b></p>{dl_html}"
        )
        self.install_btn.setEnabled(bool(content.downloads))
        self.page_btn.setEnabled(True)

    def _on_detail_err(self, err: str):
        self._set_busy(False, err)
        self.detail.append(f"<p style='color:#c44'>{_esc(err)}</p>")

    def _install(self):
        if not self._selected or not self._selected.downloads:
            QMessageBox.warning(self, "Install", "No download links available.")
            return
        self._set_busy(True, "Installing\u2026")
        self.install_btn.setEnabled(False)
        worker = _OcsInstallWorker(self._selected, parent=self)
        worker.progress.connect(lambda m: self.status.setText(m))
        worker.finished_ok.connect(self._on_install_ok)
        worker.finished_err.connect(self._on_install_err)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_install_ok(self, result):
        self._set_busy(False)
        self.install_btn.setEnabled(bool(self._selected and self._selected.downloads))
        if result.success:
            self.status.setText(result.message)
            QMessageBox.information(
                self, "Installed",
                f"{result.message}\n\nSwitch to the Manager tab to launch it.",
            )
            self.theme_installed.emit()
        else:
            self.status.setText(result.message)
            QMessageBox.warning(self, "Install failed", result.message)

    def _on_install_err(self, err: str):
        self._set_busy(False)
        self.install_btn.setEnabled(bool(self._selected and self._selected.downloads))
        QMessageBox.warning(self, "Install failed", err)

    def _open_website(self):
        key = self.provider.currentData() or "pling"
        url = "https://www.pling.com/" if key == "pling" else "https://www.opendesktop.org/"
        QDesktopServices.openUrl(QUrl(url))

    def _open_detail_page(self):
        if not self._selected:
            return
        url = self._selected.detail_page
        if not url and self._selected.id:
            key = self.provider.currentData() or "pling"
            host = "www.pling.com" if key == "pling" else "www.opendesktop.org"
            url = f"https://{host}/p/{self._selected.id}/"
        if url:
            QDesktopServices.openUrl(QUrl(url))


# ===========================================================================
# Combined Store tab
# ===========================================================================

class StoreTab(QWidget):
    """
    Theme Vault (the Community Store -- browse + install) and OpenDesktop/
    Pling (live OCS search + install) side by side. Both panels can install,
    so both feed theme_installed for MainWindow to refresh the Manager tab.
    """

    theme_installed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.theme_vault = ThemeVaultPanel()
        self.ocs = OcsPanel()
        self.tabs.addTab(self.theme_vault, "Theme Vault")
        self.tabs.addTab(self.ocs, "OpenDesktop / Pling")

        self.theme_vault.theme_installed.connect(self.theme_installed.emit)
        self.ocs.theme_installed.connect(self.theme_installed.emit)

        layout.addWidget(self.tabs)
        # Theme Vault is the Community Store -- show it first.
        self.tabs.setCurrentWidget(self.theme_vault)
