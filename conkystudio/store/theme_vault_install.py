"""
Download-and-install pipeline for Theme Vault entries -- this IS the
Community Store's install path (store_tab.py's ThemeVaultPanel calls
install_theme_vault_entry() directly; see the Install button there).

Routing by entry.host:
  - "GitHub"                -> download from the repo's latest GitHub
                                Release. Prefers an attached release asset
                                (zip/tar.*); if the release has no assets,
                                falls back to the source archive for that
                                release's tag (still release-pinned, never
                                a guessed branch).
  - "Pling" / "openDesktop" -> UNCHANGED: hand off to ocs_client.py's OCS
                                client + ocs_handler.install_content(), by
                                extracting a content id out of the link.
  - anything else           -> no generic download path (GitLab, KDE Store,
                                GNOME Look, XFCE Look, Other all vary too much
                                to fetch generically) -- return a failure the
                                UI turns into "open link instead".

client.py + index_schema.py (the older sha256-verified download-and-install
pipeline for a static index.json) are superseded by this + theme_vault.py
for the Community Store tab.
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from conkystudio.store.theme_vault import ThemeVaultEntry
from conkystudio.store.ocs_client import OcsClient, OcsError, provider_base
from conkystudio.store.ocs_handler import install_content
from conkystudio.store.ocs_install import (
    DEFAULT_INSTALL_ROOT,
    InstallResult,
    ProgressCb,
    _ensure_start_sh,
    _extract,
    _find_theme_root,
    _log,
    _safe_name,
    download_file,
)

GITHUB_API_TIMEOUT = 15
GITHUB_API_USER_AGENT = "ConkyStudio/1.0 (ThemeVault)"
ARCHIVE_EXTS = (".zip", ".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tbz2", ".tar")


# ---------------------------------------------------------------------------
# GitHub -- via Releases, not a guessed branch
# ---------------------------------------------------------------------------

class _GitHubReleaseError(Exception):
    pass


def _github_owner_repo_subpath(link: str) -> Optional[tuple[str, str, str]]:
    """
    Parse a github.com URL into (owner, repo, subpath-within-repo).

    Handles a bare repo link (owner/repo) and a /tree/<branch>/<subpath>
    link (theme living in a subfolder of a bigger repo -- subpath is only
    used later to locate the theme inside a downloaded source archive,
    never to pick which branch/release to fetch).
    """
    try:
        p = urlparse(link)
    except ValueError:
        return None
    if "github.com" not in (p.hostname or "").lower():
        return None

    parts = [seg for seg in p.path.split("/") if seg]
    if len(parts) < 2:
        return None

    owner, repo = parts[0], parts[1]
    repo = re.sub(r"\.git$", "", repo)

    subpath = ""
    if len(parts) > 4 and parts[2] == "tree":
        subpath = "/".join(parts[4:])

    return owner, repo, subpath


def _github_api_get(path: str) -> dict:
    url = f"https://api.github.com{path}"
    req = Request(
        url,
        headers={
            "User-Agent": GITHUB_API_USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urlopen(req, timeout=GITHUB_API_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 404:
            raise _GitHubReleaseError("no releases found") from e
        if e.code == 403:
            raise _GitHubReleaseError("GitHub API rate-limited this request -- try again shortly") from e
        raise _GitHubReleaseError(f"GitHub API returned HTTP {e.code}") from e
    except URLError as e:
        raise _GitHubReleaseError(f"Couldn't reach GitHub API: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise _GitHubReleaseError(f"GitHub API returned unparseable JSON: {e}") from e


def _pick_release_asset(assets: list, repo: str) -> Optional[dict]:
    """Best archive asset on a release, preferring names that mention conky/the repo."""
    archives = [a for a in assets if str(a.get("name", "")).lower().endswith(ARCHIVE_EXTS)]
    if not archives:
        return None

    def score(a: dict) -> tuple:
        name = str(a.get("name", "")).lower()
        return ("conky" in name, repo.lower() in name)

    archives.sort(key=score, reverse=True)
    return archives[0]


def _fetch_latest_release(owner: str, repo: str) -> dict:
    """
    Latest release, preferring GitHub's own "latest" (excludes pre-releases
    and drafts). Falls back to the newest entry in the full release list if
    the repo only has pre-releases.
    """
    try:
        return _github_api_get(f"/repos/{owner}/{repo}/releases/latest")
    except _GitHubReleaseError:
        releases = _github_api_get(f"/repos/{owner}/{repo}/releases")
        if isinstance(releases, list) and releases:
            return releases[0]
        raise


def _download_github_release(
    owner: str, repo: str, tmp_dir: Path, progress: ProgressCb = None
) -> tuple[Path, bool]:
    """
    Download from the repo's latest release. Returns (archive_path, was_source_archive).
    Prefers an attached release asset; falls back to the tag's source archive
    via codeload if the release has no assets.
    """
    _log(progress, f"Checking {owner}/{repo} releases\u2026")
    release = _fetch_latest_release(owner, repo)
    tag = release.get("tag_name") or release.get("name") or ""
    assets = release.get("assets") or []

    asset = _pick_release_asset(assets, repo)
    if asset:
        url = asset.get("browser_download_url")
        if not url:
            raise _GitHubReleaseError("release asset had no download URL")
        dest = tmp_dir / str(asset.get("name") or f"{repo}-release")
        return download_file(url, dest, progress=progress), False

    if not tag:
        raise _GitHubReleaseError("release has no downloadable assets and no tag to fall back to")

    _log(progress, f"Release '{tag}' has no attached files -- using its source archive\u2026")
    url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/tags/{tag}"
    dest = tmp_dir / f"{repo}-{tag}.zip"
    return download_file(url, dest, progress=progress), True


def _install_from_github(entry: ThemeVaultEntry, install_root: str, progress: ProgressCb) -> InstallResult:
    parsed = _github_owner_repo_subpath(entry.link)
    if not parsed:
        return InstallResult(False, f"Couldn't parse a GitHub repo out of {entry.link!r}.")
    owner, repo, subpath = parsed

    with tempfile.TemporaryDirectory(prefix="conkystudio-tv-gh-") as tmp:
        tmp_path = Path(tmp)
        try:
            archive, is_source_archive = _download_github_release(owner, repo, tmp_path, progress=progress)
        except _GitHubReleaseError as e:
            return InstallResult(False, f"Couldn't get a release for {owner}/{repo}: {e}")
        except Exception as e:  # noqa: BLE001
            return InstallResult(False, str(e))

        extract_dir = tmp_path / "extracted"
        try:
            _extract(archive, extract_dir, progress=progress)
        except Exception as e:  # noqa: BLE001
            return InstallResult(False, f"Extract failed: {e}", source_path=str(archive))

        search_root = extract_dir
        if is_source_archive:
            # codeload zips unpack to a single "<repo>-<tag>/" folder.
            top_level = [p for p in extract_dir.iterdir() if p.is_dir()]
            search_root = top_level[0] if len(top_level) == 1 else extract_dir
            if subpath:
                candidate = search_root / subpath
                if candidate.is_dir():
                    search_root = candidate

        theme_root = _find_theme_root(search_root)
        if theme_root is None:
            return InstallResult(
                False,
                f"Downloaded {owner}/{repo}'s release, but no Conky theme files were found "
                "(expected conky.conf, start.sh, theme.json, or render.lua).",
                source_path=str(archive),
            )

        install_root_path = Path(install_root).expanduser()
        install_root_path.mkdir(parents=True, exist_ok=True)

        name = _safe_name(entry.display_name or theme_root.name)
        target = install_root_path / name
        if target.exists():
            i = 2
            while (install_root_path / f"{name}-{i}").exists():
                i += 1
            target = install_root_path / f"{name}-{i}"
            name = target.name

        _log(progress, f"Installing to {target}\u2026")
        shutil.copytree(theme_root, target)
        added_start = _ensure_start_sh(target, progress=progress)

        msg = f"Installed '{entry.display_name}' to {target}"
        if added_start:
            msg += " (added a minimal start.sh)"
        return InstallResult(True, msg, install_dir=str(target), theme_name=name, source_path=entry.link)


# ---------------------------------------------------------------------------
# Pling / openDesktop -- unchanged OCS pipeline, just entered from a
# Theme Vault entry instead of the OCS tab's own search/browse.
# ---------------------------------------------------------------------------

def _extract_ocs_content_id(link: str) -> Optional[str]:
    """
    Pull a content id out of a Pling/openDesktop detail-page URL.
    Handles the two common shapes: .../p/<id>/... and ?content=<id>.
    """
    try:
        p = urlparse(link)
    except ValueError:
        return None
    m = re.search(r"[?&]content=(\d+)", p.query or "")
    if m:
        return m.group(1)
    m = re.search(r"/p/(\d+)", p.path or "")
    if m:
        return m.group(1)
    m = re.search(r"/(\d+)(?:/|$)", p.path or "")
    return m.group(1) if m else None


def _install_from_ocs(entry: ThemeVaultEntry, progress: ProgressCb) -> InstallResult:
    content_id = _extract_ocs_content_id(entry.link)
    if not content_id:
        return InstallResult(False, f"Couldn't find an OCS content id in {entry.link!r}.")

    provider = "pling" if entry.host == "Pling" else "opendesktop"
    client = OcsClient(base_url=provider_base(provider))
    try:
        content = client.get(content_id)
    except OcsError as e:
        return InstallResult(False, f"OCS lookup failed: {e}")

    # Same install_content() the OCS tab's Pling/openDesktop browse flow
    # already uses -- nothing about that path changes here.
    return install_content(content, progress=progress)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def install_theme_vault_entry(
    entry: ThemeVaultEntry,
    *,
    install_root: str = DEFAULT_INSTALL_ROOT,
    progress: ProgressCb = None,
) -> InstallResult:
    """
    Download-and-install a Theme Vault catalog entry into install_root.

    GitHub entries are fetched from the repo's latest Release. Pling/
    openDesktop entries go through the existing, unmodified OCS install
    pipeline. Anything else has no generic download path and comes back
    as a clear failure so the UI can offer "open link" instead.
    """
    if not entry.link:
        return InstallResult(False, f"'{entry.display_name}' has no link to install from.")

    if entry.host == "GitHub":
        return _install_from_github(entry, install_root, progress)
    if entry.host in ("Pling", "openDesktop"):
        return _install_from_ocs(entry, progress)

    return InstallResult(
        False,
        f"'{entry.display_name}' is hosted on {entry.host or 'an unsupported site'} -- "
        "Theme Vault can't auto-install from there yet. Open the link to grab it manually.",
    )
