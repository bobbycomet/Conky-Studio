"""
Theme Vault client: fetch the manifest.json (+ $ref'd Themes/*.json) that
backs the static site in theme-vault/ (see theme-vault/THEME_SCHEMA.md).

Deliberately mirrors theme-vault/app.js's resolveThemeRefs() / normalizeTheme()
/ detectHost() / resolveMediaSrc() so the desktop Store tab and the public
website always agree on how a manifest is read, no matter which one changes
first.

This is a browse-and-link-out catalog, not a download-and-install pipeline:
every entry's `link` points at wherever the theme actually lives (GitHub,
Pling, KDE Store, openDesktop, ...) and Conky Studio never downloads or runs
anything from these entries itself. Contrast with store/client.py +
store/ocs_install.py, which do own a verified download-and-install path for
a different, direct-hosted catalog.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

DEFAULT_CATALOGS: dict[str, str] = {
    "official": "https://raw.githubusercontent.com/bobbycomet/Conky-Studio/main/theme-manifest.json",
    "community": "https://raw.githubusercontent.com/bobbycomet/Conky-Studio-Theme-Community-Store/main/manifest.json",
}
DEFAULT_INDEX_URL = DEFAULT_CATALOGS["official"]

REQUEST_TIMEOUT = 10
USER_AGENT = "ConkyStudio/1.0 (ThemeVault)"

# Anything not in this list still gets its real name on the badge -- this
# only decides which get their own filter tab vs. falling into "Other".
KNOWN_HOSTS = ("GitHub", "GitLab", "Pling", "openDesktop", "KDE Store", "GNOME Look", "XFCE Look")


class ThemeVaultError(Exception):
    pass


@dataclass
class ThemeVaultEntry:
    id: str
    name: str = ""
    author: str = ""
    version: str = ""
    description: str = ""
    tags: list = field(default_factory=list)
    preview: str = ""
    screenshots: list = field(default_factory=list)
    plugins: list = field(default_factory=list)
    link: str = ""
    host: str = ""
    readme: str = ""
    readme_url: str = ""
    license: str = ""
    resolution: str = ""
    conky_version: str = ""
    # The manifest or $ref URL this entry was read from -- preview/screenshot
    # paths resolve relative to *this*, not the root manifest, since
    # preview.png normally sits next to its theme JSON in Themes/.
    source_url: str = ""

    @property
    def display_name(self) -> str:
        return self.name or self.id

    @property
    def host_group(self) -> str:
        return self.host if self.host in KNOWN_HOSTS else "Other"

    def preview_src(self) -> str:
        return resolve_media_src(self.preview, self.source_url)

    def screenshot_srcs(self) -> list[str]:
        return [s for s in (resolve_media_src(s, self.source_url) for s in self.screenshots) if s]


def detect_host(link: str) -> str:
    """Best-effort host label from a link's domain. Mirrors app.js's detectHost()."""
    try:
        host = (urlparse(link).hostname or "").lower()
    except ValueError:
        return "Other"
    if not host:
        return "Other"
    if host.startswith("www."):
        host = host[4:]
    if "github.com" in host:
        return "GitHub"
    if "gitlab.com" in host:
        return "GitLab"
    if "pling.com" in host:
        return "Pling"
    if "opendesktop.org" in host:
        return "openDesktop"
    if "store.kde.org" in host or host == "kde.org":
        return "KDE Store"
    if "gnome-look.org" in host:
        return "GNOME Look"
    if "xfce-look.org" in host:
        return "XFCE Look"
    bare = ".".join(host.split(".")[:-1]) or host
    return bare.capitalize() if bare else "Other"


def resolve_media_src(value: str, source_url: str) -> str:
    """Absolute URL as-is; anything else resolved relative to source_url."""
    v = (value or "").strip()
    if not v:
        return ""
    if re.match(r"^https?://", v, re.I):
        return v
    if source_url:
        try:
            return urljoin(source_url, v)
        except ValueError:
            pass
    return v


def _get(url: str) -> bytes:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.URLError as e:
        raise ThemeVaultError(f"Couldn't reach {url}: {e}") from e


def _get_json(url: str) -> dict:
    raw = _get(url)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ThemeVaultError(f"{url} wasn't valid JSON: {e}") from e


def fetch_manifest(manifest_url: str = DEFAULT_INDEX_URL) -> list[ThemeVaultEntry]:
    """
    Fetch manifest_url, resolve any {"$ref": "..."} theme entries relative to
    it, and return normalized, sorted ThemeVaultEntry objects.
    """
    data = _get_json(manifest_url)
    raw_themes = data.get("themes")
    if not isinstance(raw_themes, list):
        raise ThemeVaultError('manifest.json has no "themes" list.')

    entries: list[ThemeVaultEntry] = []
    for item in raw_themes:
        if not isinstance(item, dict):
            continue
        if "$ref" in item:
            ref_url = urljoin(manifest_url, str(item["$ref"]))
            try:
                raw = _get_json(ref_url)
            except ThemeVaultError as e:
                # One bad $ref shouldn't sink the whole catalog -- surface
                # it as a visible-but-broken entry instead of vanishing it.
                entries.append(ThemeVaultEntry(
                    id=f"broken-ref:{item['$ref']}",
                    name=f"(broken) {item['$ref']}",
                    description=str(e),
                ))
                continue
            source_url = ref_url
        else:
            raw = item
            source_url = manifest_url
        if not raw.get("id"):
            continue
        entries.append(_normalize(raw, source_url))

    entries.sort(key=lambda t: (t.display_name.lower(), t.id))
    return entries


def _normalize(raw: dict, source_url: str) -> ThemeVaultEntry:
    link = str(raw.get("link") or "").strip()
    host = str(raw.get("host") or "").strip() or (detect_host(link) if link else "Other")
    return ThemeVaultEntry(
        id=str(raw.get("id")),
        name=str(raw.get("name") or raw.get("id") or ""),
        author=str(raw.get("author") or ""),
        version=str(raw.get("version") or ""),
        description=str(raw.get("description") or ""),
        tags=[str(t) for t in (raw.get("tags") or []) if t],
        preview=str(raw.get("preview") or ""),
        screenshots=[str(s) for s in (raw.get("screenshots") or []) if s],
        plugins=[str(p) for p in (raw.get("plugins") or []) if p],
        link=link,
        host=host,
        readme=str(raw.get("readme") or ""),
        readme_url=str(raw.get("readme_url") or ""),
        license=str(raw.get("license") or ""),
        resolution=str(raw.get("resolution") or ""),
        conky_version=str(raw.get("conky_version") or ""),
        source_url=source_url,
    )


def fetch_readme(entry: ThemeVaultEntry) -> str:
    """
    Raw markdown for entry: inline `readme` wins; otherwise fetch
    `readme_url` (resolved relative to entry.source_url). Returns "" if
    neither is set. Raises ThemeVaultError on network failure so the caller
    can show a fallback instead of a blank panel.
    """
    if entry.readme:
        return entry.readme
    if not entry.readme_url:
        return ""
    url = resolve_media_src(entry.readme_url, entry.source_url) or entry.readme_url
    return _get(url).decode("utf-8", errors="replace")


def fetch_preview_bytes(entry: ThemeVaultEntry) -> Optional[bytes]:
    """Preview image bytes, or None if there is none / it fails to fetch."""
    src = entry.preview_src()
    if not src or not re.match(r"^https?://", src, re.I):
        return None
    try:
        return _get(src)
    except ThemeVaultError:
        return None


# ---------------------------------------------------------------------------
# Minimal, safe-by-construction markdown -> HTML for QTextBrowser
# ---------------------------------------------------------------------------
# README content comes from arbitrary third-party repos, so everything is
# HTML-escaped first and markdown constructs are layered on *top* of the
# escaped text -- raw HTML in a README is never passed through as-is. Mirrors
# theme-vault/app.js's mdToHtml().

def render_readme_html(markdown_text: str) -> str:
    if not markdown_text.strip():
        return "<p style='color:#9599ab'>No README provided. Check the link above for docs.</p>"

    text = html.escape(markdown_text.replace("\r\n", "\n"))

    blocks: list[str] = []

    def _stash_code(m: "re.Match") -> str:
        code = m.group(1).lstrip("\n")
        blocks.append(
            f"<pre style='background:#0c0d12;color:#c7cbe0;padding:12px;"
            f"border-radius:8px;overflow-x:auto;'><code>{code}</code></pre>"
        )
        return f"\x00BLOCK{len(blocks) - 1}\x00"

    text = re.sub(r"```([\s\S]*?)```", _stash_code, text)

    text = re.sub(r"^###\s+(.*)$", r"<h4>\1</h4>", text, flags=re.M)
    text = re.sub(r"^##\s+(.*)$", r"<h3>\1</h3>", text, flags=re.M)
    text = re.sub(r"^#\s+(.*)$", r"<h3>\1</h3>", text, flags=re.M)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    # Links: http(s) only -- never javascript:/data: etc.
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)

    def _list(m: "re.Match") -> str:
        items = "".join(
            f"<li>{ln.strip()[1:].strip()}</li>"
            for ln in m.group(0).strip().split("\n")
        )
        return f"<ul>{items}</ul>"

    text = re.sub(r"(?:^[-*]\s+.*$\n?)+", _list, text, flags=re.M)

    parts = []
    for chunk in re.split(r"\n{2,}", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        if re.match(r"^<(h3|h4|ul)", chunk):
            parts.append(chunk)
        else:
            parts.append(f"<p>{chunk.replace(chr(10), '<br>')}</p>")
    text = "\n".join(parts)

    for i, code_html in enumerate(blocks):
        text = text.replace(f"\x00BLOCK{i}\x00", code_html)

    return text
