"""
Application-level OCS / ocs:// wiring for Conky Studio.

- parse + install ocs:// links
- optional single-instance forward (QLocalServer)
- helpers for MainWindow / StoreTab
"""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Callable, Optional

from conkystudio.store.ocs_client import DEFAULT_PROVIDERS, OcsClient, OcsContent, OcsError, provider_base
from conkystudio.store.ocs_install import InstallResult, install_from_ocs_url, install_from_url
from conkystudio.store.ocs_url import OcsUrlError, build_ocs_url, parse_ocs_url

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

LOCAL_SERVER_NAME = "conky-studio-ocs-v1"


def is_ocs_url(s: str) -> bool:
    s = (s or "").strip().lower()
    return s.startswith("ocs://") or s.startswith("ocss://")


def handle_ocs_url(
    url: str,
    *,
    parent: Optional["QWidget"] = None,
    theme_name: str = "",
    progress: Optional[Callable[[str], None]] = None,
    on_done: Optional[Callable[[InstallResult], None]] = None,
) -> InstallResult:
    """
    Parse an ocs:// URL, download, and install. Shows a message box if parent is set.
    """
    try:
        result = install_from_ocs_url(url, theme_name=theme_name, progress=progress)
    except OcsUrlError as e:
        result = InstallResult(False, str(e))
    except Exception as e:
        result = InstallResult(False, f"OCS install failed: {e}")

    if parent is not None:
        try:
            from PyQt6.QtWidgets import QMessageBox
            if result.success:
                QMessageBox.information(parent, "OCS install", result.message)
            else:
                QMessageBox.warning(parent, "OCS install", result.message)
        except Exception:
            pass

    if on_done:
        on_done(result)
    return result


def install_content(
    content: OcsContent,
    *,
    download_index: int = 0,
    parent: Optional["QWidget"] = None,
    progress: Optional[Callable[[str], None]] = None,
) -> InstallResult:
    if not content.downloads:
        result = InstallResult(False, "No download links on this item.")
    else:
        idx = max(0, min(download_index, len(content.downloads) - 1))
        dl = content.downloads[idx]
        result = install_from_url(
            dl.url,
            filename=dl.name,
            install_type="conky",
            theme_name=content.name,
            progress=progress,
        )
    if parent is not None:
        try:
            from PyQt6.QtWidgets import QMessageBox
            if result.success:
                QMessageBox.information(parent, "Install", result.message)
            else:
                QMessageBox.warning(parent, "Install", result.message)
        except Exception:
            pass
    return result


# ---------------------------------------------------------------------------
# Single-instance: forward ocs:// to a running Conky Studio
# ---------------------------------------------------------------------------

def try_forward_to_running_instance(url: str) -> bool:
    """
    If another Conky Studio is listening on LOCAL_SERVER_NAME, send the URL and
    return True (caller should exit). Otherwise return False.
    """
    try:
        from PyQt6.QtNetwork import QLocalSocket
    except ImportError:
        return False

    sock = QLocalSocket()
    sock.connectToServer(LOCAL_SERVER_NAME)
    if not sock.waitForConnected(250):
        return False
    payload = (url.strip() + "\n").encode("utf-8")
    sock.write(payload)
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


class OcsLocalServer:
    """
    Listen for ocs:// payloads from secondary instances.
    Call start() once from MainWindow; connect url_received to handle_ocs_url.
    """

    def __init__(self, on_url: Callable[[str], None]):
        self._on_url = on_url
        self._server = None

    def start(self) -> bool:
        try:
            from PyQt6.QtNetwork import QLocalServer
        except ImportError:
            return False

        QLocalServer.removeServer(LOCAL_SERVER_NAME)
        server = QLocalServer()
        if not server.listen(LOCAL_SERVER_NAME):
            return False
        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def _on_connection(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._read(s))

    def _read(self, sock) -> None:
        data = bytes(sock.readAll()).decode("utf-8", errors="replace").strip()
        sock.disconnectFromServer()
        if data and is_ocs_url(data):
            self._on_url(data)


def consume_argv_ocs_urls(argv: Optional[list] = None) -> list[str]:
    """Return ocs:// URLs found on the command line."""
    args = argv if argv is not None else sys.argv[1:]
    return [a for a in args if is_ocs_url(a)]


# ---------------------------------------------------------------------------
# Desktop file snippet helpers (for packaging docs)
# ---------------------------------------------------------------------------

DESKTOP_MIME_LINES = """\
MimeType=x-scheme-handler/ocs;x-scheme-handler/ocss;
"""

REGISTER_SCHEME_SH = """\
#!/bin/sh
# Register Conky Studio as handler for ocs:// and ocss://
APP_DESKTOP="${1:-conky-studio.desktop}"
xdg-mime default "$APP_DESKTOP" x-scheme-handler/ocs
xdg-mime default "$APP_DESKTOP" x-scheme-handler/ocss
update-desktop-database "${XDG_DATA_HOME:-$HOME/.local/share}/applications" 2>/dev/null || true
echo "Registered $APP_DESKTOP for ocs:// and ocss://"
"""
