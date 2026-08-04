"""
Update checker -- compares this build's version against the latest
GitHub release and surfaces it two ways: a silent check at startup
(only ever speaks up if there's actually something new -- it should
never interrupt someone mid-build to say "you're up to date"), and an
on-demand Help -> Check for Updates... which always reports something,
found or not.

Hits the GitHub Releases API rather than probing the versioned AppImage
URL directly (https://github.com/bobbycomet/Conky-Studio/releases/
download/v1.0.0/Conky-Studio-x86_64.AppImage is *this* version's asset,
not a moving target) -- the API's "latest" endpoint is what actually
answers "is there something newer", and also hands back that same
AppImage asset's URL for whatever the newest tag turns out to be.

Runs on a background QThread so a slow or unreachable network never
stalls app startup or blocks the UI thread -- same reasoning as why
plugins.loader's remote manifest fetch is opt-in rather than automatic
at launch.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

# Bump this on every release -- it's the only thing that needs updating
# in this file when Conky Studio itself ships a new version.
APP_VERSION = "1.0.7.0"

GITHUB_REPO = "bobbycomet/Conky-Studio"
RELEASES_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
APPIMAGE_ASSET_NAME = "Conky-Studio-x86_64.AppImage"


@dataclass
class UpdateCheckResult:
    checked_ok: bool
    update_available: bool = False
    current_version: str = APP_VERSION
    latest_version: Optional[str] = None
    download_url: str = RELEASES_PAGE_URL
    error: Optional[str] = None


def _parse_version(v: str) -> tuple:
    """'v1.2.3' / '1.2.3' -> (1, 2, 3). A release tag that isn't a plain
    dotted-numeric version (e.g. a pre-release codename) falls back to
    (0,) so the check just reports "nothing newer" instead of crashing
    on a tag it can't parse."""
    v = (v or "").strip()
    if v[:1] in ("v", "V"):
        v = v[1:]
    parts = []
    for chunk in v.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) or (0,)


def check_for_update(timeout: float = 6.0) -> UpdateCheckResult:
    """Synchronous network call -- always run this off the UI thread
    (see UpdateCheckWorker below), never directly from a slot."""
    try:
        req = urllib.request.Request(
            RELEASES_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Conky-Studio-UpdateCheck",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as e:
        return UpdateCheckResult(checked_ok=False, error=str(e))

    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    latest = _parse_version(tag)
    current = _parse_version(APP_VERSION)

    download_url = RELEASES_PAGE_URL
    for asset in (data.get("assets") or []):
        if asset.get("name") == APPIMAGE_ASSET_NAME and asset.get("browser_download_url"):
            download_url = asset["browser_download_url"]
            break

    return UpdateCheckResult(
        checked_ok=True,
        update_available=latest > current,
        current_version=APP_VERSION,
        latest_version=(tag[1:] if tag[:1] in ("v", "V") else tag) or None,
        download_url=download_url,
    )


class UpdateCheckWorker(QThread):
    """Thin QThread wrapper so check_for_update() never runs on the UI
    thread. Keep a reference to the worker alive on whatever owns it
    (e.g. self._update_worker on MainWindow) until finished_check fires --
    PyQt does not keep a QThread alive on your behalf."""

    finished_check = pyqtSignal(object)  # UpdateCheckResult

    def run(self):
        self.finished_check.emit(check_for_update())
