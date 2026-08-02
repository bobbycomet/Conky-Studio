"""
Open Collaboration Services (OCS) client for Pling / openDesktop.

Spec: https://www.freedesktop.org/wiki/Specifications/open-collaboration-services
Providers typically expose:
  https://api.pling.com/ocs/v1/
  https://www.opendesktop.org/ocs/v1/

Public content list/get usually work without auth. Status 200 from the API
means rate-limited; surface that to the UI.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

DEFAULT_PROVIDERS: dict[str, str] = {
    "pling": "https://api.pling.com/ocs/v1/",
    "opendesktop": "https://www.opendesktop.org/ocs/v1/",
}

# Heuristic keywords for Conky-related categories / search boost
CONKY_KEYWORDS = ("conky", "system monitor", "desktop widget", "hud")


class OcsError(Exception):
    """Base error for OCS client failures."""


class OcsRateLimited(OcsError):
    """API returned statuscode 200 (too many requests)."""


class OcsNotFound(OcsError):
    """Content id not found (statuscode 101)."""


@dataclass
class OcsCategory:
    id: str
    name: str


@dataclass
class OcsDownload:
    name: str
    url: str
    size: str = ""
    download_type: str = ""


@dataclass
class OcsContent:
    id: str
    name: str
    summary: str = ""
    description: str = ""
    version: str = ""
    author: str = ""
    preview_url: str = ""
    detail_page: str = ""
    score: str = ""
    downloads: list[OcsDownload] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def best_download(self) -> Optional[OcsDownload]:
        return self.downloads[0] if self.downloads else None

    def looks_like_conky(self) -> bool:
        blob = f"{self.name} {self.summary} {self.description}".lower()
        return any(k in blob for k in CONKY_KEYWORDS)


class OcsClient:
    """Minimal OCS CONTENT client (categories, search, get)."""

    def __init__(
        self,
        base_url: str = DEFAULT_PROVIDERS["pling"],
        timeout: float = 25.0,
        user_agent: str = "ConkyStudio/1.0 (OCS)",
    ):
        self.base = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.user_agent = user_agent

    # ------------------------------------------------------------------ HTTP
    def _request(self, path: str, params: Optional[dict] = None) -> bytes:
        q = dict(params or {})
        # Prefer JSON; providers that only speak XML still return XML and we fall back.
        q.setdefault("format", "json")
        url = urljoin(self.base, path.lstrip("/"))
        if q:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(q)}"
        req = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json, application/xml, text/xml, */*"})
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except HTTPError as e:
            raise OcsError(f"HTTP {e.code} for {url}") from e
        except URLError as e:
            raise OcsError(f"Network error: {e.reason}") from e

    def _check_meta(self, meta: dict) -> None:
        code = str(meta.get("statuscode") or meta.get("statusCode") or "")
        if code in ("100", "ok", ""):
            return
        if code == "200":
            raise OcsRateLimited(meta.get("message") or "Rate limited by OCS provider")
        if code == "101":
            raise OcsNotFound(meta.get("message") or "Not found")
        # Some providers nest status under meta differently
        status = str(meta.get("status") or "").lower()
        if status in ("ok", "success", ""):
            return
        raise OcsError(f"OCS error {code}: {meta.get('message', '')}")

    # ------------------------------------------------------------------ public API
    def categories(self) -> list[OcsCategory]:
        raw = self._request("content/categories")
        data = self._decode(raw)
        self._check_meta(data.get("meta") or data.get("ocs", {}).get("meta") or {})
        items = self._data_list(data, "category")
        out: list[OcsCategory] = []
        for it in items:
            cid = str(it.get("id") or it.get("categoryid") or "")
            name = str(it.get("name") or it.get("categoryname") or "")
            if cid:
                out.append(OcsCategory(id=cid, name=name))
        return out

    def conky_categories(self) -> list[OcsCategory]:
        """Categories whose names look Conky-related."""
        return [
            c for c in self.categories()
            if any(k in c.name.lower() for k in CONKY_KEYWORDS)
        ]

    def search(
        self,
        query: str = "",
        category_ids: str = "",
        page: int = 0,
        pagesize: int = 24,
    ) -> list[OcsContent]:
        """
        category_ids: single id or OCS multi form \"12x34\".
        """
        params: dict[str, Any] = {"page": int(page), "pagesize": int(pagesize)}
        if query:
            params["search"] = query
        if category_ids:
            params["categories"] = category_ids
        raw = self._request("content/data", params)
        return self._parse_contents(raw)

    def get(self, content_id: str) -> OcsContent:
        raw = self._request(f"content/data/{content_id}")
        items = self._parse_contents(raw)
        if not items:
            raise OcsNotFound(f"content {content_id} not found")
        return items[0]

    # ------------------------------------------------------------------ decode
    def _decode(self, raw: bytes) -> dict:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return {}
        if text[0] in "{[":
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        return self._xml_to_dict(text)

    def _xml_to_dict(self, text: str) -> dict:
        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            raise OcsError(f"Invalid OCS response: {e}") from e

        def node_to_obj(el: ET.Element) -> Any:
            children = list(el)
            if not children:
                return (el.text or "").strip()
            # Group repeated tags into lists
            acc: dict[str, Any] = {}
            for ch in children:
                val = node_to_obj(ch)
                if ch.tag in acc:
                    if not isinstance(acc[ch.tag], list):
                        acc[ch.tag] = [acc[ch.tag]]
                    acc[ch.tag].append(val)
                else:
                    acc[ch.tag] = val
            return acc

        body = node_to_obj(root)
        if isinstance(body, dict):
            return body if "meta" in body or "data" in body else {"ocs": body}
        return {"data": body}

    def _data_list(self, data: dict, singular: str) -> list[dict]:
        """
        OCS wraps payloads in meta/data. Content lists may be:
          data.content  (list or single)
          data[singular]
        """
        root = data.get("ocs", data)
        meta = root.get("meta") or data.get("meta") or {}
        if isinstance(meta, dict):
            self._check_meta(meta)

        payload = root.get("data") or data.get("data") or root
        if not isinstance(payload, dict):
            return []

        for key in (singular, f"{singular}s", "content", "contents"):
            block = payload.get(key)
            if block is None:
                continue
            if isinstance(block, list):
                return [b for b in block if isinstance(b, dict)]
            if isinstance(block, dict):
                # Single item or map of id -> item
                if any(k in block for k in ("id", "name", "contentid")):
                    return [block]
                return [v for v in block.values() if isinstance(v, dict)]
        # Sometimes data itself is the content list under numbered keys
        return []

    def _parse_contents(self, raw: bytes) -> list[OcsContent]:
        data = self._decode(raw)
        items = self._data_list(data, "content")
        if not items:
            # get() sometimes returns data as the content object directly
            root = data.get("ocs", data)
            payload = root.get("data") or {}
            if isinstance(payload, dict) and (payload.get("id") or payload.get("contentid")):
                items = [payload]

        return [self._to_content(it) for it in items]

    def _to_content(self, it: dict) -> OcsContent:
        cid = str(it.get("id") or it.get("contentid") or "")
        name = str(it.get("name") or it.get("contentname") or "")
        summary = str(it.get("summary") or "")
        description = str(it.get("description") or it.get("descriptionlong") or "")
        version = str(it.get("version") or "")
        author = str(it.get("personid") or it.get("author") or it.get("username") or "")
        score = str(it.get("score") or it.get("rating") or "")
        detail = str(it.get("detailpage") or it.get("detail_page") or "")

        preview = ""
        for key in ("previewpic1", "previewurl", "preview", "smallpreviewpic1", "icon"):
            v = it.get(key)
            if v:
                preview = str(v)
                break

        downloads: list[OcsDownload] = []
        # JSON style: downloadlink / downloads array
        dl_block = it.get("downloads") or it.get("download")
        if isinstance(dl_block, list):
            for d in dl_block:
                if not isinstance(d, dict):
                    continue
                url = str(d.get("link") or d.get("url") or d.get("downloadlink") or "")
                if url:
                    downloads.append(OcsDownload(
                        name=str(d.get("name") or d.get("downloadname") or "file"),
                        url=url,
                        size=str(d.get("size") or d.get("downloadsize") or ""),
                        download_type=str(d.get("type") or d.get("downloadtype") or ""),
                    ))
        elif isinstance(dl_block, dict):
            url = str(dl_block.get("link") or dl_block.get("url") or "")
            if url:
                downloads.append(OcsDownload(
                    name=str(dl_block.get("name") or "file"),
                    url=url,
                    size=str(dl_block.get("size") or ""),
                ))

        # Classic OCS numbered fields: downloadlink1, downloadname1, ...
        if not downloads:
            numbered = []
            for key, val in it.items():
                m = re.match(r"^downloadlink(\d+)$", str(key), re.I)
                if m and val:
                    n = m.group(1)
                    numbered.append((int(n), str(val), str(it.get(f"downloadname{n}") or f"file{n}")))
            for _, url, dname in sorted(numbered):
                downloads.append(OcsDownload(name=dname, url=url))

        return OcsContent(
            id=cid,
            name=name,
            summary=summary,
            description=description,
            version=version,
            author=author,
            preview_url=preview,
            detail_page=detail,
            score=score,
            downloads=downloads,
            raw=it,
        )


def provider_base(name: str) -> str:
    key = (name or "pling").lower().strip()
    return DEFAULT_PROVIDERS.get(key, DEFAULT_PROVIDERS["pling"])
