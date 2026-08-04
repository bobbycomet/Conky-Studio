"""
The Store tab. Two sources:

  1. Community — static index.json (see store/client.py). Index URL is editable.
  2. OpenDesktop / Pling live OCS API search + install.

Ships pointed at a placeholder community URL since that repo may not exist yet;
the OCS side works against Pling/openDesktop immediately.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QTextEdit, QSplitter,
    QTabWidget, QComboBox, QTextBrowser, QFrame, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices

from conkystudio.store import client as store_client
from conkystudio.store.ocs_client import (
    OcsClient, OcsContent, OcsError, OcsRateLimited, provider_base,
)
from conkystudio.store.ocs_handler import install_content


# ===========================================================================
# Community (static index.json)
# ===========================================================================

class _FetchThread(QThread):
    done = pyqtSignal(object, str)   # StoreIndex or None, error message

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url

    def run(self):
        try:
            index = store_client.fetch_index(self.url)
            self.done.emit(index, "")
        except store_client.StoreError as e:
            self.done.emit(None, str(e))


class _InstallThread(QThread):
    done = pyqtSignal(object)

    def __init__(self, entry, parent=None):
        super().__init__(parent)
        self.entry = entry

    def run(self):
        result = store_client.download_and_install(self.entry)
        self.done.emit(result)


class CommunityPanel(QWidget):
    """Existing community catalogue UI (index URL + list + install)."""

    theme_installed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.index = None
        self._fetch_thread = None
        self._install_thread = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        heading = QLabel("Community Store")
        heading.setProperty("role", "heading")
        outer.addWidget(heading)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("Index URL"))
        self.url_edit = QLineEdit(store_client.DEFAULT_INDEX_URL)
        url_row.addWidget(self.url_edit, 1)
        fetch_btn = QPushButton("Browse")
        fetch_btn.setObjectName("primary")
        fetch_btn.clicked.connect(self._fetch)
        url_row.addWidget(fetch_btn)
        outer.addLayout(url_row)

        note = QLabel(
            "No community repo is configured yet by default; point this at your own "
            "conky-studio-community-themes index.json once you're hosting one (see the README's "
            "Community Store section for the repo layout + CI validation template)."
        )
        note.setProperty("role", "caption")
        note.setWordWrap(True)
        outer.addWidget(note)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.list_widget)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        self.detail_view = QTextEdit()
        self.detail_view.setReadOnly(True)
        detail_layout.addWidget(self.detail_view, 1)
        self.install_btn = QPushButton("Install")
        self.install_btn.setObjectName("primary")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self._install_selected)
        detail_layout.addWidget(self.install_btn)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _fetch(self):
        self.list_widget.clear()
        self.detail_view.setPlainText("Fetching\u2026")
        self._fetch_thread = _FetchThread(self.url_edit.text().strip())
        self._fetch_thread.done.connect(self._on_fetched)
        self._fetch_thread.start()

    def _on_fetched(self, index, error: str):
        if error:
            self.detail_view.setPlainText(f"Couldn't load store index:\n{error}")
            return
        self.index = index
        self.list_widget.clear()
        for entry in index.themes:
            item = QListWidgetItem(f"{entry.name}  \u00b7  v{entry.version}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list_widget.addItem(item)
        self.detail_view.setPlainText(
            f"{len(index.themes)} theme(s) available." if index.themes else "No themes listed yet."
        )

    def _on_selection_changed(self, *_args):
        item = self.list_widget.currentItem()
        if item is None:
            self.install_btn.setEnabled(False)
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        self.detail_view.setPlainText(
            f"{entry.name}\nby {entry.author or 'unknown'}  \u00b7  v{entry.version}\n"
            f"tags: {', '.join(entry.tags) if entry.tags else '(none)'}\n\n{entry.description}"
        )
        self.install_btn.setEnabled(True)

    def _install_selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        self.install_btn.setEnabled(False)
        self.install_btn.setText("Installing\u2026")
        self._install_thread = _InstallThread(entry)
        self._install_thread.done.connect(self._on_installed)
        self._install_thread.start()

    def _on_installed(self, result):
        self.install_btn.setEnabled(True)
        self.install_btn.setText("Install")
        if result.success:
            QMessageBox.information(self, "Installed", result.message)
            self.theme_installed.emit()
        else:
            QMessageBox.warning(self, "Install failed", result.message)


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
    Community catalogue + OpenDesktop/Pling.
    Emit theme_installed so MainWindow can refresh the Manager tab.
    """

    theme_installed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.community = CommunityPanel()
        self.ocs = OcsPanel()
        self.tabs.addTab(self.community, "Community")
        self.tabs.addTab(self.ocs, "OpenDesktop / Pling")

        self.community.theme_installed.connect(self.theme_installed.emit)
        self.ocs.theme_installed.connect(self.theme_installed.emit)

        layout.addWidget(self.tabs)
        # Show OCS first so the new feature is visible
        self.tabs.setCurrentWidget(self.ocs)

