"""
ocs:// / ocss:// URL parsing (OCS-URL specification).

Example:
  ocs://install?url=https%3A%2F%2Fexample.com%2Ftheme.tar.gz&type=conky&filename=theme.tar.gz

Spec reference:
  https://www.opencode.net/dfn2/ocs-url/-/blob/master/docs/OCS-URL-specification.md
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class OcsUrl:
    scheme: str          # ocs | ocss
    command: str         # install | download
    url: str             # file URL (decoded)
    install_type: str    # conky | downloads | themes | ...
    filename: str

    @property
    def is_install(self) -> bool:
        return self.command.lower() == "install"


class OcsUrlError(ValueError):
    pass


def parse_ocs_url(url: str) -> OcsUrl:
    if not url or not isinstance(url, str):
        raise OcsUrlError("empty ocs url")

    p = urlparse(url.strip())
    scheme = (p.scheme or "").lower()
    if scheme not in ("ocs", "ocss"):
        raise OcsUrlError(f"unsupported scheme: {p.scheme!r}")

    # ocs://install?url=...  → netloc=install, query=...
    # ocs:install?url=...    → path=install, query=...
    command = (p.netloc or "").strip()
    if not command:
        command = (p.path or "").lstrip("/").split("/")[0]
    command = (command or "install").lower()
    if command not in ("install", "download"):
        # Some links put the whole thing in path
        command = "install"

    qs = parse_qs(p.query, keep_blank_values=False)

    def first(key: str, default: str = "") -> str:
        vals = qs.get(key) or []
        return unquote(vals[0]) if vals else default

    file_url = first("url")
    if not file_url:
        raise OcsUrlError("ocs url missing required query parameter: url")

    install_type = first("type", "downloads") or "downloads"
    filename = first("filename", "")

    return OcsUrl(
        scheme=scheme,
        command=command,
        url=file_url,
        install_type=install_type,
        filename=filename,
    )


def build_ocs_url(
    file_url: str,
    *,
    command: str = "install",
    install_type: str = "conky",
    filename: str = "",
    secure: bool = False,
) -> str:
    """Build an ocs:// link (values are urlencoded)."""
    from urllib.parse import urlencode

    q = {"url": file_url, "type": install_type}
    if filename:
        q["filename"] = filename
    scheme = "ocss" if secure else "ocs"
    return f"{scheme}://{command}?{urlencode(q)}"
