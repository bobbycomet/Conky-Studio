"""
Talks to whatever static index.json a community repo publishes (see
store/index_schema.py + packaging/community-repo-template/index.json for
the exact shape, and README's "Community Store" section for how to point
this at a real repo once one exists). Deliberately just urllib + a
dataclass parse -- no dependency on a specific host, so this isn't
locked to GitHub if a Pling/OpenDesktop-style OCS backend gets added
later (see store/opendesktop.py stub).
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.request
import urllib.error

from conkystudio.store.index_schema import StoreIndex
from conkystudio.manager import installer

DEFAULT_INDEX_URL = "https://raw.githubusercontent.com/bobbycomet/Conky-Studio/main/store.json"
REQUEST_TIMEOUT = 10


class StoreError(Exception):
    pass


def fetch_index(index_url: str = DEFAULT_INDEX_URL) -> StoreIndex:
    try:
        with urllib.request.urlopen(index_url, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise StoreError(f"Couldn't reach the store index: {e}") from e
    except json.JSONDecodeError as e:
        raise StoreError(f"Store index wasn't valid JSON: {e}") from e
    return StoreIndex.from_dict(data)


def _sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def download_and_install(entry, install_root: str = installer.DEFAULT_INSTALL_ROOT):
    if not entry.download_url:
        return installer.InstallResult(False, message="This entry has no download_url.")

    suffix = ".zip" if entry.download_url.endswith(".zip") else ".tar.gz"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = tmp.name
    try:
        try:
            urllib.request.urlretrieve(entry.download_url, tmp_path)
        except urllib.error.URLError as e:
            return installer.InstallResult(False, message=f"Download failed: {e}")

        if entry.sha256:
            actual = _sha256_of(tmp_path)
            if actual.lower() != entry.sha256.lower():
                return installer.InstallResult(
                    False, message=f"Checksum mismatch for '{entry.name}' -- expected {entry.sha256[:12]}\u2026, "
                                    f"got {actual[:12]}\u2026. Not installing a file that doesn't match what the "
                                    f"store index said to expect."
                )
        return installer.install_theme_archive(tmp_path, install_root)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
