# Community Store

Conky Studio’s **Community Store** is a lightweight catalogue of themes published as a static JSON index. Anyone can host an index; the app is not locked to a single vendor. Users point the Store tab at an **Index URL**, browse entries, and install archives into `~/.config/conky/`.

This is separate from **OpenDesktop / Pling** (OCS API), which is a live third-party network. The Community Store is *your* (or the project’s) curated list.

---

## How it works (user view)

1. Open the **Store** tab → **Community**.
2. Confirm or edit the **Index URL** (default points at the project’s `store.json` on GitHub).
3. Click **Browse** — Studio downloads the index over HTTPS and lists themes.
4. Select a theme to read name, author, version, tags, description.
5. Click **Install** — Studio downloads the archive, optionally checks **SHA-256**, then unpacks it with the same installer used for local theme archives.

Installed themes appear under **Manager** and can be started like any other theme.

If the default URL is empty or the host is offline, Browse shows an error; you can still paste another index URL.

---

## Architecture

```text
┌─────────────────────┐         HTTPS GET          ┌──────────────────────┐
│  Store tab (UI)     │  ───────────────────────►  │  index.json /        │
│  Index URL field    │                            │  store.json          │
└─────────┬───────────┘                            │  (static host)       │
          │                                        └──────────┬───────────┘
          │  parse → StoreIndex                                │
          ▼                                                    │
┌─────────────────────┐                                        │
│  store/client.py    │   download_url (+ optional sha256)     │
│  fetch_index()      │  ───────────────────────────────────►  │ theme .zip/.tar.gz
│  download_and_install()                                      │
└─────────┬───────────┘                                        │
          │                                                    │
          ▼                                                    │
┌─────────────────────┐                                        │
│  manager/installer  │  install into ~/.config/conky/<name>   │
└─────────────────────┘
```

| Piece | Role |
|--------|------|
| **Index** | One JSON file listing themes (metadata + download URLs + checksums) |
| **client.py** | Fetch index, download archive, verify SHA-256, call installer |
| **index_schema.py** | Dataclasses for `StoreIndex` / `StoreThemeEntry` |
| **installer** | Shared unpack path used by Manager import and the Store |

No account, no API key, no dynamic backend — only static files a CDN or GitHub raw URL can serve.

---

## Index format (`store.json` / `index.json`)

```json
{
  "api_version": "1.0",
  "updated_at": "2026-07-30",
  "themes": [
    {
      "id": "aurora-hud",
      "name": "Aurora HUD",
      "author": "example",
      "version": "1.2.0",
      "description": "Minimal top-bar system monitor with soft glow.",
      "tags": ["hud", "minimal", "cpu", "ram"],
      "preview_url": "https://example.com/previews/aurora-hud.png",
      "download_url": "https://example.com/releases/aurora-hud-1.2.0.zip",
      "sha256": "abcdef0123456789..."
    }
  ]
}
```

### Fields

| Field | Required | Description |
|--------|----------|-------------|
| `api_version` | Recommended | Manifest format version (`"1.0"`) |
| `updated_at` | Optional | ISO date or free-form string for humans |
| `themes` | Yes | Array of theme entries |

### Theme entry

| Field | Required | Description |
|--------|----------|-------------|
| `id` | Yes | Stable slug (unique within the index) |
| `name` | Yes | Display name |
| `author` | Optional | Creator credit |
| `version` | Optional | Semver or free-form; shown in the list |
| `description` | Optional | Longer text in the detail pane |
| `tags` | Optional | List of strings for filtering / display |
| `preview_url` | Optional | Image URL (UI may show later; not required to install) |
| `download_url` | **Yes for install** | Direct link to `.zip` or `.tar.gz` |
| `sha256` | Strongly recommended | Hex digest of the archive; install aborts on mismatch |

If `download_url` is missing, Install reports that the entry cannot be downloaded.  
If `sha256` is set and the file hash differs, install is refused (integrity protection).

---

## Default index URL

Defined in `conkystudio/store/client.py`:

```text
https://raw.githubusercontent.com/bobbycomet/Conky-Studio/main/store.json
```

The Store tab’s **Index URL** field overrides this per session (and can be pointed at any compatible host).

---

## Hosting your own community index

### Option A — GitHub (simplest)

1. Create a repo (e.g. `conky-studio-community-themes`).
2. Add `store.json` at the repo root (or `index.json`).
3. Put release archives in `releases/` or attach them to GitHub Releases.
4. Point download URLs at:
   - Release assets, or  
   - `https://raw.githubusercontent.com/<user>/<repo>/<branch>/path/to/theme.zip`  
   (raw works for small files; Releases are better for large zips).
5. Users set Index URL to:
   ```text
   https://raw.githubusercontent.com/<user>/<repo>/<branch>/store.json
   ```

### Option B — Any static host

Serve `store.json` and the archives over HTTPS (GitLab Pages, Cloudflare R2, nginx, etc.). Same JSON shape.

### Suggested repo layout

```text
conky-studio-community-themes/
├── store.json                 # the index
├── themes/
│   └── aurora-hud/
│       ├── theme source…      # optional, for authors
│       └── ...
├── dist/
│   └── aurora-hud-1.2.0.zip   # what download_url points at
├── scripts/
│   └── validate_index.py      # optional CI: schema + sha256
└── README.md
```

### Computing SHA-256

```bash
sha256sum dist/aurora-hud-1.2.0.zip
# paste the hex into the theme entry's "sha256" field
```

---

## Install pipeline (technical)

1. `fetch_index(url)` → HTTP GET → `json.loads` → `StoreIndex.from_dict`.
2. User selects a `StoreThemeEntry`.
3. `download_and_install(entry)`:
   - Downloads `entry.download_url` to a temp file.
   - If `entry.sha256` is non-empty, hashes the file; mismatch → error, no install.
   - Calls `installer.install_theme_archive(tmp_path, install_root)`.
4. Theme lands under the default install root (typically `~/.config/conky/<name>`).

Network errors surface as `StoreError` / failed `InstallResult` with a readable message.

---

## Relation to OpenDesktop / Pling

| | Community Store | OpenDesktop / Pling |
|--|-----------------|---------------------|
| Source | Static `store.json` you control | Live OCS API |
| Curation | Explicit list + checksums | Search the whole network |
| Trust | Index + SHA-256 | Provider + download links (often short-lived) |
| Offline / mirror | Easy to fork and rehost | Depends on Pling uptime |
| Best for | Official / trusted theme packs | Discovery of third-party content |

Both install into the same Manager root so users have one place to run themes.

---

## Trust and safety

- The index is **untrusted input**. Only install from indexes and URLs you believe.
- **SHA-256** is the main integrity check; omit it only for private testing.
- Archives are unpacked by the same code path as “import local theme” — malicious zips can still write unexpected paths if the installer is permissive; prefer checksums and known authors.
- Preview images are remote URLs; treat them like any other web content.

---

## For app developers

| Module | Responsibility |
|--------|----------------|
| `store/index_schema.py` | `StoreThemeEntry`, `StoreIndex` |
| `store/client.py` | `DEFAULT_INDEX_URL`, `fetch_index`, `download_and_install` |
| `ui/store_tab.py` | Community panel UI (URL, Browse, list, Install) |

To change the shipped default catalogue, update `store.json` on the default branch and/or `DEFAULT_INDEX_URL` in `client.py`.

---

## Quick checklist for publishers

- [ ] Theme packs as `.zip` or `.tar.gz` with a clear top-level folder  
- [ ] `store.json` entry per theme with unique `id`  
- [ ] Working `download_url` (HTTPS)  
- [ ] `sha256` of the exact file at that URL  
- [ ] Sensible `name`, `version`, `description`, `tags`  
- [ ] Index URL documented in your README for Conky Studio users  

Once the index is online, users only need that URL in the Store tab’s **Index URL** field and **Browse**.
