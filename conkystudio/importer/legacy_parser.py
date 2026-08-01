"""
Legacy theme importer: conky.conf (+ TEXT section, + optional Lua
mouse/draw-hook files, + companion shell scripts) -> a Project. This is
semantic extraction, not literal preservation -- deliberately. A ${cpu}
becomes a CPU Usage source node wired to whatever visual seems to want
it; the exact original pixel layout is a best-effort approximation (a
running x/y cursor driven by ${goto}/${voffset}/${alignc}), not a
guarantee. Nothing is silently dropped, though: anything not confidently
mapped becomes a Custom Script source or a Custom Lua visual node instead
of being lost, and every approximation/unmapped bit is listed in
ImportResult.warnings.

Scope boundary, stated plainly: this does NOT attempt to parse arbitrary
hand-written Cairo drawing code into visual nodes (an existing
lua_draw_hook_pre/post Lua file's drawing FUNCTION BODY is wrapped whole
into one Custom Lua node, with only its own surface-setup/teardown
boilerplate stripped). True "read arbitrary Cairo and re-derive the
intended shapes" is a different, much harder problem than parsing
Conky's own regular ${...} template syntax, and this doesn't claim to
solve it.
"""
from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field

from conkystudio.model.project import Project, NodeInstance, new_id, CanvasSettings

VAR_RE = re.compile(r"\$\{([^{}]*)\}")

# Known script basenames get mapped to a purpose-built native/external
# source instead of a generic Custom Script -- these are the exact
# scripts this importer was validated against (see the Ridge theme).
KNOWN_SCRIPTS = {
    "greeting.sh": ("native", "source.greeting", {}),
    "playerctl.sh": ("family", "source.nowplaying_title", {}),
    "spot.sh": ("family", "source.nowplaying_artist", {}),
    "spot2.sh": ("family", "source.nowplaying_progress", {}),
    "weather-text-icon": ("custom", None, {"output_kind": "text"}),
    "forecast-text-icon": ("custom", None, {"output_kind": "text"}),
}

FONT_SIZE_RE = re.compile(r"size=(\d+)")

_LUA_SCRIPT_PATH_RE = re.compile(
    r"""(?:io\.popen|os\.execute)\s*\(\s*['"]([^'"]+\.sh[^'"]*)['"]"""
    r"""|['"]([^'"]+/[^'"]+\.sh)['"]"""
)


@dataclass
class ImportResult:
    project: Project
    warnings: list = field(default_factory=list)


@dataclass
class _Cursor:
    x: float = 20.0
    y: float = 20.0
    color: str = "#FFFFFF"
    font_family: str = "Sans"
    font_size: int = 12


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _find_conf(theme_dir: str, conf_filename: str | None = None) -> str:
    if conf_filename:
        path = os.path.join(theme_dir, conf_filename)
        if os.path.isfile(path):
            return path
    top = [f for f in os.listdir(theme_dir) if f.endswith(".conf") or f == "conkyrc"]
    if top:
        preferred = sorted(
            top,
            key=lambda n: (0 if n in ("conky.conf", "conkyrc") else 1, n),
        )
        return os.path.join(theme_dir, preferred[0])
    for root, _dirs, files in os.walk(theme_dir):
        for f in files:
            if f.endswith(".conf") or f == "conkyrc":
                return os.path.join(root, f)
    raise FileNotFoundError(f"No .conf file found in {theme_dir}")


def _parse_conky_config_block(conf_text: str) -> dict:
    m = re.search(r"conky\.config\s*=\s*\{(.*?)\n\}", conf_text, re.DOTALL)
    block = m.group(1) if m else ""
    settings = {}
    for key in (
        "alignment", "gap_x", "gap_y", "update_interval", "own_window_type",
        "minimum_width", "minimum_height", "maximum_width",
        "default_color", "default_outline_color", "default_shade_color",
        "font", "default_font",
    ):
        km = re.search(rf"\b{re.escape(key)}\s*=\s*'?\"?([^,'\"\n]+)'?\"?\s*,", block)
        if km:
            settings[key] = km.group(1).strip()
    # colourN / colorN palette (Conky accepts both spellings)
    for n in range(10):
        for prefix in ("color", "colour"):
            key = f"{prefix}{n}"
            km = re.search(rf"\b{re.escape(key)}\s*=\s*'?\"?([^,'\"\n]+)'?\"?\s*,", block)
            if km:
                settings[f"color{n}"] = km.group(1).strip().lstrip("#")
                break
    lua_load_m = re.search(r"lua_load\s*=\s*(.+?),\s*\n", block)
    if lua_load_m:
        settings["lua_load_raw"] = lua_load_m.group(1).strip()
    for hook_key in ("lua_draw_hook_post", "lua_draw_hook_pre"):
        hm = re.search(rf"\b{hook_key}\s*=\s*['\"]?([\w.]+)['\"]?\s*,", block)
        if hm:
            settings[hook_key] = hm.group(1).strip()
    return settings




def _resolve_lua_locals(conf_text: str) -> dict[str, str]:
    """Pick up `local WIDTH = 1920` style bindings from the conf preamble
    (and anywhere outside comments). Used when canvas size is written as
    minimum_width = WIDTH rather than a numeric literal -- common in
    full-screen HUD themes that define WIDTH/HEIGHT once at the top."""
    out: dict[str, str] = {}
    for m in re.finditer(
        r"\blocal\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([-+]?\d+(?:\.\d+)?)",
        conf_text,
    ):
        out[m.group(1)] = m.group(2)
    return out


def _parse_int_setting(settings: dict, *keys: str, default: int) -> int:
    """Best-effort int from a settings value that may be a number, a
    numeric string, or still an unresolved Lua identifier. Never raises."""
    for key in keys:
        raw = settings.get(key)
        if raw is None:
            continue
        try:
            return int(float(str(raw).strip()))
        except (ValueError, TypeError):
            continue
    return default


def _parse_float_setting(settings: dict, *keys: str, default: float) -> float:
    for key in keys:
        raw = settings.get(key)
        if raw is None:
            continue
        try:
            return float(str(raw).strip())
        except (ValueError, TypeError):
            continue
    return default

def _resolve_lua_load_path(raw: str, theme_dir: str) -> str:
    """Handles both the simple `'path/to/file.lua'` form and the
    `os.getenv("HOME") .. '/relative/path.lua'` concatenation form seen
    in real themes -- extracts whatever comes after the last '..' as the
    relative part, then resolves it against theme_dir."""
    parts = raw.split("..")
    tail = parts[-1].strip().strip("'\"")
    tail = tail.lstrip("/")
    basename = os.path.basename(tail)
    if not basename:
        return ""
    candidate = os.path.join(theme_dir, basename)
    if os.path.isfile(candidate):
        return candidate
    candidate2 = os.path.join(theme_dir, "scripts", basename)
    if os.path.isfile(candidate2):
        return candidate2
    # Try relative path under theme_dir if tail has subdirs
    candidate3 = os.path.join(theme_dir, tail)
    if os.path.isfile(candidate3):
        return candidate3
    return ""


def _resolve_all_lua_loads(raw: str, theme_dir: str) -> list[str]:
    """lua_load can be a single path or a list; also pick up sibling .lua files."""
    paths: list[str] = []
    chunks = re.split(r"\s*;\s*|\s+,?\s+(?=os\.getenv|'|\")", raw) if raw else []
    if not chunks:
        chunks = [raw] if raw else []
    for chunk in chunks:
        chunk = (chunk or "").strip().rstrip(",")
        if not chunk:
            continue
        p = _resolve_lua_load_path(chunk, theme_dir)
        if p and p not in paths:
            paths.append(p)
    if paths:
        folder = os.path.dirname(paths[0])
        try:
            for f in os.listdir(folder):
                if f.endswith(".lua"):
                    full = os.path.join(folder, f)
                    if full not in paths:
                        paths.append(full)
        except OSError:
            pass
    else:
        for sub in ("", "scripts"):
            d = os.path.join(theme_dir, sub) if sub else theme_dir
            if not os.path.isdir(d):
                continue
            try:
                for f in os.listdir(d):
                    if f.endswith(".lua"):
                        paths.append(os.path.join(d, f))
            except OSError:
                pass
    return paths


def _list_theme_scripts(theme_dir: str) -> list[str]:
    out: list[str] = []
    skip_dirs = {"_imported_scripts", ".git", "__pycache__"}
    for root, dirs, files in os.walk(theme_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            path = os.path.join(root, f)
            if f.endswith(".sh") or f.endswith(".bash"):
                out.append(path)
                continue
            try:
                with open(path, "rb") as fh:
                    head = fh.read(32)
                if head.startswith(b"#!/") and b"sh" in head:
                    out.append(path)
            except OSError:
                pass
    return out




_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".bmp", ".tif", ".tiff"}


def _list_theme_images(theme_dir: str) -> list[str]:
    """Collect image files under the theme. Prefer assets/ and images/
    subfolders (the usual layout for hand-authored Cairo themes) but also
    pick up loose images at the theme root so nothing is dropped."""
    out: list[str] = []
    seen: set[str] = set()
    skip_dirs = {"_imported_scripts", ".git", "__pycache__", ".runtime-cache", "fonts"}

    preferred = []
    for sub in ("assets", "images", "img", "Icons", "icons"):
        d = os.path.join(theme_dir, sub)
        if os.path.isdir(d):
            preferred.append(d)
    preferred.append(theme_dir)

    walked: set[str] = set()
    for base in preferred:
        base = os.path.abspath(base)
        if base in walked:
            continue
        walked.add(base)
        if base == os.path.abspath(theme_dir):
            try:
                for f in os.listdir(base):
                    full = os.path.join(base, f)
                    if not os.path.isfile(full):
                        continue
                    ext = os.path.splitext(f)[1].lower()
                    if ext in _IMAGE_EXTS and full not in seen:
                        seen.add(full)
                        out.append(full)
            except OSError:
                pass
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in _IMAGE_EXTS:
                    continue
                full = os.path.join(root, f)
                if full not in seen:
                    seen.add(full)
                    out.append(full)
    return out


def _rewrite_lua_asset_paths(lua_body: str, image_basenames: set[str]) -> tuple[str, int]:
    """Rewrite absolute / HOME-relative asset and cache paths in imported
    Lua so they resolve through theme-local folders at runtime:

      ASSETS_DIR  -> THEME_DIR .. '/assets/'   (matches original Batman/etc layout)
      image paths -> ASSETS_DIR .. 'basename'  (or THEME_DIR .. '/assets/basename')
      *CACHE*     -> CACHE_DIR .. '/basename'

    Studio's own Image/Glow nodes still use IMAGES_DIR (theme/images/);
    builder copies the same files into both assets/ and images/ so either
    convention works. Bare basenames (`'joker.png'`) are left alone so
    `ASSETS_DIR .. case.image` keeps working after ASSETS_DIR is rewritten.
    """
    if not lua_body:
        return lua_body, 0
    count = 0

    def _is_dir_path(p: str) -> bool:
        p = p.replace("\\", "/")
        if p.startswith("~") or p.startswith("/home/") or p.startswith("/Users/"):
            return True
        parts = [s for s in p.split("/") if s and s != "."]
        return len(parts) >= 2

    # CFG.ASSETS_DIR = os.getenv('HOME') .. '/.config/conky/Batman/assets/'
    def assets_repl(m):
        nonlocal count
        count += 1
        return m.group(1) + "THEME_DIR .. '/assets/'"

    lua_body = re.sub(
        r"""((?:local\s+)?(?:\w+\.)?ASSETS_DIR\s*=\s*)"""
        r"""(?:os\.getenv\s*\(\s*['"]HOME['"]\s*\)\s*\.\.\s*)?['"][^'"]*['"]""",
        assets_repl,
        lua_body,
    )

    # WEATHER_CACHE / SENSORS_CACHE -> CACHE_DIR .. '/foo.cache'
    def cache_repl(m):
        nonlocal count
        prefix, quoted = m.group(1), m.group(2)
        base = os.path.basename(quoted.replace("\\", "/"))
        if not base:
            return m.group(0)
        count += 1
        return f"{prefix}CACHE_DIR .. '/{base}'"

    lua_body = re.sub(
        r"""((?:local\s+)?(?:\w+\.)?\w*CACHE\w*\s*=\s*)"""
        r"""(?:os\.getenv\s*\(\s*['"]HOME['"]\s*\)\s*\.\.\s*)?['"]([^'"]+)['"]""",
        cache_repl,
        lua_body,
    )

    # BAT_IMAGE_PATH = .../assets/bat.png  -> ASSETS_DIR .. 'bat.png'
    # (ASSETS_DIR already ends with / after rewrite, or we use explicit path)
    def path_repl(m):
        nonlocal count
        prefix, quoted = m.group(1), m.group(2)
        if not _is_dir_path(quoted):
            return m.group(0)
        base = os.path.basename(quoted.replace("\\", "/"))
        if image_basenames and base not in image_basenames:
            return m.group(0)
        if not base:
            return m.group(0)
        count += 1
        # Prefer ASSETS_DIR so themes that concat ASSETS_DIR .. name stay consistent;
        # fall back expression works even if ASSETS_DIR wasn't in the file.
        return f"{prefix}(ASSETS_DIR or (THEME_DIR .. '/assets/')) .. '{base}'"

    lua_body = re.sub(
        r"""((?:local\s+)?(?:\w+\.)?\w*(?:PATH|path|IMAGE|image|ICON|icon|FILE|file)\w*\s*=\s*)"""
        r"""(?:os\.getenv\s*\(\s*['"]HOME['"]\s*\)\s*\.\.\s*)?['"]([^'"]+)['"]""",
        path_repl,
        lua_body,
    )

    if image_basenames:
        def literal_repl(m):
            nonlocal count
            quote, body = m.group(1), m.group(2)
            if not _is_dir_path(body):
                return m.group(0)
            base = os.path.basename(body.replace("\\", "/"))
            if base not in image_basenames:
                return m.group(0)
            count += 1
            return f"(ASSETS_DIR or (THEME_DIR .. '/assets/')) .. {quote}{base}{quote}"

        lua_body = re.sub(
            r"""(['"])([^'"]+\.(?:png|jpe?g|webp|svg|gif|bmp|tiff?))\1""",
            literal_repl,
            lua_body,
            flags=re.IGNORECASE,
        )

    return lua_body, count



def _patch_script_cache_dir(script_path: str, scripts_out_dir: str) -> str:
    """If a companion script hard-codes HOME/.cache/..., write a patched
    copy that uses Studio's theme-local .runtime-cache (same folder
    CACHE_DIR resolves to in render.lua). Returns the path to use as
    script_path (patched copy or original)."""
    try:
        with open(script_path, "r", encoding="utf-8", errors="replace") as f:
            src = f.read()
    except OSError:
        return script_path

    patched = re.sub(
        r'CACHE_DIR\s*=\s*["\']\$\{?HOME\}?/\.cache/[^"\']+["\']',
        'CACHE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.runtime-cache"',
        src,
    )
    if patched == src:
        return script_path

    os.makedirs(scripts_out_dir, exist_ok=True)
    base = os.path.basename(script_path)
    dest = os.path.join(scripts_out_dir, f"patched_{base}")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(patched)
    try:
        os.chmod(dest, os.stat(dest).st_mode | 0o111)
    except OSError:
        pass
    return dest


def _scripts_mentioned_in_lua(lua_text: str, theme_dir: str) -> list[str]:
    found: list[str] = []
    for m in _LUA_SCRIPT_PATH_RE.finditer(lua_text):
        raw = (m.group(1) or m.group(2) or "").strip()
        if not raw:
            continue
        base = os.path.basename(raw.replace("~", ""))
        if ".sh" in base:
            base = base.split(".sh")[0] + ".sh"
        for root, _d, files in os.walk(theme_dir):
            if base in files:
                full = os.path.join(root, base)
                if full not in found:
                    found.append(full)
                break
    return found


def _make_script_executable_copy(inline_cmd: str, scripts_dir: str, hint: str) -> str:
    os.makedirs(scripts_dir, exist_ok=True)
    safe_hint = re.sub(r"[^a-zA-Z0-9_]+", "_", hint)[:30] or "script"
    filename = f"imported_{safe_hint}_{abs(hash(inline_cmd)) % 100000}.sh"
    path = os.path.join(scripts_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n" + inline_cmd + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _find_existing_script(cmd: str, theme_dir: str) -> str:
    first_token = cmd.strip().split()[0] if cmd.strip() else ""
    basename = os.path.basename(first_token.replace("~", ""))
    if not basename:
        return ""
    for root, _dirs, files in os.walk(theme_dir):
        if basename in files:
            return os.path.join(root, basename)
    return ""



def _read_script_body_for_edit(script_path: str, max_bytes: int = 32_000) -> str:
    """Load a companion script into script_body so Properties can edit it inline.
    Skips huge files (keep path-only)."""
    if not script_path or not os.path.isfile(script_path):
        return ""
    try:
        if os.path.getsize(script_path) > max_bytes:
            return ""
        with open(script_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


class _ImportContext:
    def __init__(self, project: Project, theme_dir: str, scripts_out_dir: str, settings: dict | None = None):
        self.project = project
        self.theme_dir = theme_dir
        self.scripts_out_dir = scripts_out_dir
        self.warnings: list = []
        self.custom_script_cache: dict = {}
        self._source_cache: dict = {}  # (type, frozen_props) -> NodeInstance
        self.palette: dict[str, str] = {}
        settings = settings or {}
        # default + color0..9 from conky.config
        def _norm_hex(raw: str) -> str:
            s = (raw or "").strip().lstrip("#")
            if len(s) == 3:
                s = "".join(ch * 2 for ch in s)
            if re.match(r"^[0-9a-fA-F]{6}$", s):
                return "#" + s.upper()
            return "#FFFFFF"
        dc = settings.get("default_color") or settings.get("color0") or "FFFFFF"
        self.palette["default"] = _norm_hex(dc)
        for i in range(10):
            if f"color{i}" in settings:
                self.palette[str(i)] = _norm_hex(settings[f"color{i}"])
            else:
                self.palette[str(i)] = self.palette["default"]
        # Default font from conf
        font_raw = settings.get("font") or settings.get("default_font") or "Sans:size=12"
        self.default_font_family = font_raw.split(":")[0].strip() or "Sans"
        size_m = FONT_SIZE_RE.search(font_raw)
        self.default_font_size = int(size_m.group(1)) if size_m else 12

    def resolve_color(self, name: str, rest: str) -> str:
        """Map ${color}, ${color3}, ${color #aabbcc} to #RRGGBB."""
        rest = (rest or "").strip()
        if rest.startswith("#") or re.match(r"^[0-9a-fA-F]{3,6}$", rest):
            s = rest.lstrip("#")
            if len(s) == 3:
                s = "".join(ch * 2 for ch in s)
            if re.match(r"^[0-9a-fA-F]{6}$", s):
                return "#" + s.upper()
            return self.palette.get("default", "#FFFFFF")
        # ${color3} form: name is color3 and rest empty, or name is color and rest is 3
        if name.startswith("color") and len(name) > 5 and name[5:].isdigit():
            return self.palette.get(name[5:], self.palette["default"])
        if rest.isdigit():
            return self.palette.get(rest, self.palette["default"])
        return self.palette.get("default", "#FFFFFF")

    def get_or_create_source(self, node_type: str, props: dict | None = None, label: str = "") -> NodeInstance:
        """Reuse identical native/family sources so TEXT-heavy themes don't spawn dozens of CPU nodes."""
        props = dict(props or {})
        key = (node_type, tuple(sorted((k, str(v)) for k, v in props.items())))
        existing = self._source_cache.get(key)
        if existing is not None:
            return existing
        for n in self.project.nodes:
            if n.type != node_type:
                continue
            if all(str(n.props.get(k, "")) == str(v) for k, v in props.items()):
                self._source_cache[key] = n
                return n
        # Guard against typos / older Studio builds missing a source type.
        try:
            from conkystudio.nodes import registry as _reg
            _reg.get(node_type)
        except Exception:
            self.warnings.append(
                f"Source type {node_type!r} is not registered in this build; "
                f"skipped (props={props}). Update Studio or map it to Custom Script."
            )
            # Placeholder text-ish custom script so wiring still has something.
            node = self.make_custom_script_source(f"echo 0  # missing {node_type}", 60, "number")
            self._source_cache[key] = node
            return node
        node = self.project.add_node(NodeInstance(
            id=new_id("n"), type=node_type, label=label, props=props,
        ))
        self._source_cache[key] = node
        return node

    def make_custom_script_source(self, raw_cmd: str, interval: int, output_kind: str = "text") -> NodeInstance:
        key = (raw_cmd.strip(), interval)
        if key in self.custom_script_cache:
            return self.custom_script_cache[key]

        existing = _find_existing_script(raw_cmd, self.theme_dir)
        if existing:
            script_path = existing
        else:
            script_path = _make_script_executable_copy(raw_cmd, self.scripts_out_dir, raw_cmd[:20])
            self.warnings.append(
                f"Inline command wrapped into a generated script since no matching file was found "
                f"in the imported theme: {raw_cmd[:70]!r}{'...' if len(raw_cmd) > 70 else ''}"
            )

        body = _read_script_body_for_edit(script_path)
        node = self.project.add_node(NodeInstance(
            id=new_id("n"), type="source.custom_script",
            props={
                "script_path": script_path,
                "script_body": body,
                "poll_mode": "execi",
                "poll_interval": max(1, interval),
                "output_kind": output_kind,
            },
        ))
        self.custom_script_cache[key] = node
        return node


def _classify_known_script(cmd: str) -> tuple:
    first_token = cmd.strip().split()[0] if cmd.strip() else ""
    basename = os.path.basename(first_token.replace("~", ""))
    return KNOWN_SCRIPTS.get(basename, (None, None, None))


def _strip_conditionals(text: str) -> tuple:
    stripped_any = False
    pattern = re.compile(r"\$\{if_running[^}]*\}|\$\{if_match[^}]*\}|\$\{endif\}")
    if pattern.search(text):
        stripped_any = True
    text = pattern.sub("", text)
    return text, stripped_any


def parse_text_section(text_section: str, ctx: _ImportContext, canvas_w: int) -> None:
    cursor = _Cursor(
        color=getattr(ctx, "palette", {}).get("default", "#FFFFFF"),
        font_family=getattr(ctx, "default_font_family", "Sans"),
        font_size=getattr(ctx, "default_font_size", 12),
    )
    z = 0
    any_conditional_stripped = False
    ignored_directives: dict[str, int] = {}

    for raw_line in text_section.split("\n"):
        line, stripped = _strip_conditionals(raw_line)
        any_conditional_stripped = any_conditional_stripped or stripped
        if not line.strip():
            cursor.y += cursor.font_size + 6
            continue

        pos = 0
        literal_run = ""

        def flush_literal(run: str):
            nonlocal z
            run = run.strip()
            if run:
                ctx.project.add_node(NodeInstance(
                    id=new_id("n"), type="visual.text", z=z,
                    props={
                        "value": run, "x": int(cursor.x), "y": int(cursor.y),
                        "font_family": cursor.font_family, "font_size": cursor.font_size,
                        "color": cursor.color,
                    },
                ))
                z += 1

        for m in VAR_RE.finditer(line):
            literal_run += line[pos:m.start()]
            directive = m.group(1).strip()
            pos = m.end()
            parts = directive.split(None, 1)
            name = parts[0] if parts else ""
            rest = parts[1] if len(parts) > 1 else ""

            if name == "goto":
                flush_literal(literal_run); literal_run = ""
                try:
                    cursor.x = float(rest.strip())
                except ValueError:
                    pass
                continue
            if name == "offset":
                flush_literal(literal_run); literal_run = ""
                try:
                    cursor.x += float(rest.strip())
                except ValueError:
                    pass
                continue
            if name == "voffset":
                flush_literal(literal_run); literal_run = ""
                try:
                    cursor.y += float(rest.strip())
                except ValueError:
                    pass
                continue
            if name == "alignc":
                flush_literal(literal_run); literal_run = ""
                try:
                    cursor.x = canvas_w / 2 + float(rest.strip() or 0)
                except ValueError:
                    cursor.x = canvas_w / 2
                continue
            if name == "alignr":
                flush_literal(literal_run); literal_run = ""
                try:
                    cursor.x = max(0.0, canvas_w - float(rest.strip() or 0))
                except ValueError:
                    cursor.x = max(0.0, canvas_w - 80)
                continue
            if name.startswith("color") or name.startswith("colour"):
                cursor.color = ctx.resolve_color(name.replace("colour", "color"), rest)
                continue
            if name in ("hr", "stippled_hr"):
                flush_literal(literal_run); literal_run = ""
                try:
                    length = int(float(rest.strip() or (canvas_w - cursor.x)))
                except ValueError:
                    length = max(40, int(canvas_w - cursor.x))
                ctx.project.add_node(NodeInstance(
                    id=new_id("n"), type="visual.hline", z=z,
                    props={
                        "x": int(cursor.x), "y": int(cursor.y),
                        "length": length, "line_width": 1.0,
                        "color": cursor.color, "opacity": 0.55,
                    },
                ))
                z += 1
                cursor.y += 8
                continue
            if name == "font":
                if rest.strip():
                    cursor.font_family = rest.split(":")[0].strip()
                    size_m = FONT_SIZE_RE.search(rest)
                    if size_m:
                        cursor.font_size = int(size_m.group(1))
                else:
                    cursor.font_family, cursor.font_size = "Sans", 12
                continue

            if name == "image":
                flush_literal(literal_run); literal_run = ""
                img_args = rest
                path_m = re.match(r"(\S+)", img_args)
                pos_m = re.search(r"-p\s+(-?\d+),(-?\d+)", img_args)
                size_m = re.search(r"-s\s+(\d+)x(\d+)", img_args)
                no_cache = "-n" in img_args
                ix, iy = (int(pos_m.group(1)), int(pos_m.group(2))) if pos_m else (int(cursor.x), int(cursor.y))
                iw, ih = (int(size_m.group(1)), int(size_m.group(2))) if size_m else (64, 64)
                src_path = path_m.group(1) if path_m else ""
                if no_cache:
                    ctx.project.add_node(NodeInstance(id=new_id("n"), type="visual.album_art", z=z, props={
                        "x": ix, "y": iy, "size": min(iw, ih),
                    }))
                    ctx.warnings.append(
                        f"${{image ... -n}} at ({ix},{iy}) imported as Album Art; "
                        f"original path was {src_path!r}."
                    )
                else:
                    resolved = ""
                    base = os.path.basename(src_path.replace("~", ""))
                    for root, _d, files in os.walk(ctx.theme_dir):
                        if base in files:
                            resolved = os.path.join(root, base)
                            break
                    ctx.project.add_node(NodeInstance(id=new_id("n"), type="visual.image_icon", z=z, props={
                        "x": ix, "y": iy, "size": min(iw, ih), "path": resolved,
                    }))
                    if not resolved:
                        ctx.warnings.append(
                            f"${{image}} at ({ix},{iy}) referenced {src_path!r}, which wasn't "
                            f"found among the imported files -- re-attach it manually."
                        )
                z += 1
                continue

            if name in ("execi", "execpi", "texeci"):
                exec_m = re.match(r"(\d+)\s+(.*)", rest, re.DOTALL)
                interval = int(exec_m.group(1)) if exec_m else 60
                cmd = exec_m.group(2) if exec_m else rest
                kind, mapped_type, extra = _classify_known_script(cmd)
                if kind == "native":
                    src_node = ctx.get_or_create_source(mapped_type, {})
                elif kind == "family":
                    src_node = ctx.get_or_create_source(
                        mapped_type, {"poll_mode": "execi", "poll_interval": interval},
                    )
                else:
                    src_node = ctx.make_custom_script_source(
                        cmd, interval, (extra or {}).get("output_kind", "text"),
                    )
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue

            if name == "exec":
                src_node = ctx.make_custom_script_source(rest, 3600, "text")
                ctx.warnings.append(
                    f"${{exec}} (runs once at Conky startup only) imported as a Custom Script "
                    f"polling every 3600s -- adjust if a literal one-shot matters for {rest[:50]!r}."
                )
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue

            if name == "execbar":
                bar_m = re.match(r"[\d,]+\s+'?(.*?)'?$", rest)
                cmd = bar_m.group(1) if bar_m else rest
                kind, mapped_type, extra = _classify_known_script(cmd)
                if kind == "family":
                    src_node = ctx.get_or_create_source(mapped_type, {"poll_mode": "execi"})
                elif kind == "native":
                    src_node = ctx.get_or_create_source(mapped_type, {})
                else:
                    src_node = ctx.make_custom_script_source(cmd, 5, "number")
                bar = ctx.project.add_node(NodeInstance(id=new_id("n"), type="visual.bar", z=z, props={
                    "x": int(cursor.x), "y": int(cursor.y), "width": 200, "height": 10, "color": cursor.color,
                }))
                ctx.project.add_edge(src_node.id, bar.id, "value")
                z += 1
                continue

            if name == "time":
                fmt = rest.strip() or "%H:%M"
                src_node = ctx.get_or_create_source("source.datetime", {"strftime_format": fmt})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name == "cpu":
                core = (rest.strip() or "overall")
                if core in ("", "cpu"):
                    core = "overall"
                elif core.isdigit():
                    core = f"cpu{core}"
                props = {"core": core} if core != "overall" else {"core": "overall"}
                if props["core"] not in ("overall", "cpu0", "cpu1", "cpu2", "cpu3", "cpu4", "cpu5", "cpu6", "cpu7"):
                    props = {"core": "overall"}
                src_node = ctx.get_or_create_source("source.cpu_percent", props)
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name in ("memperc", "mem"):
                src_node = ctx.get_or_create_source("source.ram_percent", {})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name in ("fs_used_perc", "fs_bar"):
                mount = (rest.strip().split() or ["/"])[-1] if rest.strip() else "/"
                if not mount.startswith("/"):
                    mount = "/"
                src_node = ctx.get_or_create_source("source.disk_percent", {"mount_path": mount})
                if name == "fs_bar":
                    flush_literal(literal_run); literal_run = ""
                    bar = ctx.project.add_node(NodeInstance(
                        id=new_id("n"), type="visual.bar", z=z,
                        props={
                            "x": int(cursor.x), "y": int(cursor.y),
                            "width": 180, "height": 10, "color": cursor.color,
                        },
                    ))
                    ctx.project.add_edge(src_node.id, bar.id, "value")
                    z += 1
                else:
                    literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name in ("battery_percent", "battery"):
                device = rest.strip() or "BAT0"
                src_node = ctx.get_or_create_source("source.battery_percent", {"device": device})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name in ("downspeed", "downspeedf"):
                src_node = ctx.get_or_create_source("source.net_down", {"interface": "auto"})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name in ("upspeed", "upspeedf"):
                src_node = ctx.get_or_create_source("source.net_up", {"interface": "auto"})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name == "uptime":
                src_node = ctx.get_or_create_source("source.uptime", {"format": "long"})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name == "uptime_short":
                src_node = ctx.get_or_create_source("source.uptime", {"format": "short"})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name in ("nodename", "sysname"):
                src_node = ctx.get_or_create_source("source.hostname", {})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name == "kernel":
                src_node = ctx.get_or_create_source("source.kernel", {})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name == "processes":
                src_node = ctx.get_or_create_source("source.process_count", {})
                literal_run += f"{{{{VALUE:{src_node.id}}}}}"
                continue
            if name in ("cpubar", "cpugraph"):
                flush_literal(literal_run); literal_run = ""
                src_node = ctx.get_or_create_source("source.cpu_percent", {"core": "overall"})
                w, h = (180, 12) if name == "cpubar" else (180, 40)
                vis = "visual.bar" if name == "cpubar" else "visual.history_graph"
                node = ctx.project.add_node(NodeInstance(
                    id=new_id("n"), type=vis, z=z,
                    props={
                        "x": int(cursor.x), "y": int(cursor.y),
                        "width": w, "height": h, "color": cursor.color,
                    },
                ))
                ctx.project.add_edge(src_node.id, node.id, "value")
                z += 1
                continue
            if name in ("membar", "memgraph"):
                flush_literal(literal_run); literal_run = ""
                src_node = ctx.get_or_create_source("source.ram_percent", {})
                w, h = (180, 12) if name == "membar" else (180, 40)
                vis = "visual.bar" if name == "membar" else "visual.history_graph"
                node = ctx.project.add_node(NodeInstance(
                    id=new_id("n"), type=vis, z=z,
                    props={
                        "x": int(cursor.x), "y": int(cursor.y),
                        "width": w, "height": h, "color": cursor.color,
                    },
                ))
                ctx.project.add_edge(src_node.id, node.id, "value")
                z += 1
                continue
            if name in ("swapbar", "swapperc"):
                if name == "swapperc":
                    literal_run += "0"
                else:
                    flush_literal(literal_run); literal_run = ""
                    ignored_directives[name] = ignored_directives.get(name, 0) + 1
                continue
            if name in ("top", "top_mem", "top_io", "top_time"):
                flush_literal(literal_run); literal_run = ""
                ctx.project.add_node(NodeInstance(
                    id=new_id("n"), type="visual.text", z=z,
                    props={
                        "value": f"[${{{name}}} — edit or replace with Custom Script]",
                        "x": int(cursor.x), "y": int(cursor.y),
                        "font_family": cursor.font_family, "font_size": max(9, cursor.font_size - 2),
                        "color": cursor.color,
                    },
                ))
                z += 1
                ignored_directives[name] = ignored_directives.get(name, 0) + 1
                continue

            ignored_directives[name or directive[:20]] = ignored_directives.get(name or directive[:20], 0) + 1

        literal_run += line[pos:]
        remaining = literal_run.strip()
        if remaining:
            value_ids = re.findall(r"\{\{VALUE:([\w]+)\}\}", remaining)
            if len(value_ids) == 1 and remaining.strip() == f"{{{{VALUE:{value_ids[0]}}}}}":
                text_node = ctx.project.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=z, props={
                    "value": "", "x": int(cursor.x), "y": int(cursor.y),
                    "font_family": cursor.font_family, "font_size": cursor.font_size, "color": cursor.color,
                }))
                ctx.project.add_edge(value_ids[0], text_node.id, "value")
            elif value_ids:
                template = re.sub(r"\{\{VALUE:[\w]+\}\}", "{value}", remaining, count=1)
                extra_ids = value_ids[1:]
                fmt_node = ctx.project.add_node(NodeInstance(
                    id=new_id("n"), type="logic.string_format", props={"template": template},
                ))
                ctx.project.add_edge(value_ids[0], fmt_node.id, "input")
                text_node = ctx.project.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=z, props={
                    "value": "", "x": int(cursor.x), "y": int(cursor.y),
                    "font_family": cursor.font_family, "font_size": cursor.font_size, "color": cursor.color,
                }))
                ctx.project.add_edge(fmt_node.id, text_node.id, "value")
                if len(extra_ids) > 0:
                    ctx.warnings.append(
                        f"Line had {len(value_ids)} values but only the template's first "
                        f"{{value}} slot is wired -- the rest ({len(extra_ids)}) are still "
                        f"present as source nodes, just not auto-bound: {remaining[:60]!r}"
                    )
            else:
                ctx.project.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=z, props={
                    "value": remaining, "x": int(cursor.x), "y": int(cursor.y),
                    "font_family": cursor.font_family, "font_size": cursor.font_size, "color": cursor.color,
                }))
            z += 1

        cursor.y += cursor.font_size + 6

    if any_conditional_stripped:
        ctx.warnings.append(
            "${if_running}/${if_match}/${endif} blocks were unwrapped (contents kept, always "
            "shown) -- Conky Studio doesn't have a process-conditional-visibility node yet."
        )
    if ignored_directives:
        parts = [f"${{{k}}}×{c}" if c > 1 else f"${{{k}}}" for k, c in sorted(ignored_directives.items())]
        if len(parts) > 12:
            shown = ", ".join(parts[:12]) + f", … (+{len(parts) - 12} more)"
        else:
            shown = ", ".join(parts)
        ctx.warnings.append(
            f"Some TEXT directives have no direct Studio node and were skipped or approximated: {shown}."
        )


CLICK_REGION_RE = re.compile(
    r"if\s+event\.x\s*>=\s*(-?\d+)\s+and\s+event\.x\s*<=\s*(-?\d+)\s+and\s+event\.y\s*>=\s*(-?\d+)\s+and\s+event\.y\s*<=\s*(-?\d+)\s+then"
    r"(.*?)end",
    re.DOTALL,
)
COMMAND_RE = re.compile(r'os\.execute\(\s*"([^"]+?)(?:\s*&)?"\s*\)')


def parse_mouse_regions(lua_text: str, project: Project) -> int:
    count = 0
    for m in CLICK_REGION_RE.finditer(lua_text):
        x1, x2, y1, y2, body = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
        commands = [c for c in COMMAND_RE.findall(body) if "paplay" not in c and "message-new-instant" not in c]
        if not commands:
            continue
        label = commands[0][:24]
        node = project.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=project.next_z(), props={
            "value": f"[{label}]", "x": x1, "y": y1, "font_size": 9, "color": "#5c636d",
        }))
        node.on_click_command = commands[0]
        node.click_x, node.click_y = x1, y1
        node.click_w, node.click_h = x2 - x1, y2 - y1
        count += 1
    return count


BOILERPLATE_PATTERNS = [
    re.compile(r"local\s+\w+\s*=\s*cairo_xlib_surface_create\([^)]*\)\s*\n?"),
    re.compile(r"local\s+\w+\s*=\s*cairo_create\([^)]*\)\s*\n?"),
    re.compile(r"cairo_destroy\(\w+\)\s*\n?"),
    re.compile(r"cairo_surface_destroy\(\w+\)\s*\n?"),
    re.compile(r"require\s*['\"]cairo['\"]\s*\n?"),
    re.compile(r"if\s+conky_window\s*==\s*nil\s+then\s+return\s+end\s*\n?"),
    re.compile(r"if\s+updates\s*<\s*\d+\s+then\s+return\s+end\s*\n?"),
]


def _strip_known_boilerplate(lua_text: str) -> str:
    for pat in BOILERPLATE_PATTERNS:
        lua_text = pat.sub("", lua_text)
    lua_text = re.sub(
        r"local\s+(\w+)\s*,\s*(\w+)\s*=\s*conky_window\.width\s*,\s*conky_window\.height",
        r"local \1, \2 = W, H",
        lua_text,
    )
    lua_text = re.sub(r"conky_window\.width", "W", lua_text)
    lua_text = re.sub(r"conky_window\.height", "H", lua_text)
    return lua_text


def _extract_draw_hook_body(lua_text: str, hook_name: str | None) -> str:
    candidates = []
    if hook_name:
        candidates.append(hook_name.strip().strip("'\""))
    candidates += ["conky_main_draw", "conky_main", "main_draw", "conky_draw"]
    for m in re.finditer(r"function\s+(conky_\w+)\s*\(", lua_text):
        name = m.group(1)
        if name not in candidates:
            candidates.append(name)

    for name in candidates:
        pat = re.compile(
            rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\n(.*)\nend\s*$",
            re.DOTALL | re.MULTILINE,
        )
        m = pat.search(lua_text)
        if not m:
            pat2 = re.compile(
                rf"function\s+{re.escape(name)}\s*\([^)]*\)\s*\n(.*?)\nend\b",
                re.DOTALL,
            )
            m = pat2.search(lua_text)
        if not m:
            continue
        body = m.group(1)
        preamble = lua_text[: m.start()].rstrip()
        combined = (preamble + "\n\n" + body).strip() if preamble else body.strip()
        return _strip_known_boilerplate(combined)

    return _strip_known_boilerplate(lua_text)


def import_legacy_theme(theme_dir: str, conf_filename: str = None) -> ImportResult:
    conf_path = _find_conf(theme_dir, conf_filename)
    conf_text = _read(conf_path)
    settings = _parse_conky_config_block(conf_text)

    name = os.path.splitext(os.path.basename(conf_path))[0]

    # Resolve Lua locals like `local WIDTH = 1920` so settings that still
    # hold the identifier (minimum_width = WIDTH) become numeric. Themes
    # that hard-code the number are unchanged.
    lua_locals = _resolve_lua_locals(conf_text)
    for key in (
        "minimum_width", "minimum_height", "maximum_width",
        "gap_x", "gap_y", "update_interval",
    ):
        val = settings.get(key)
        if isinstance(val, str) and val in lua_locals:
            settings[key] = lua_locals[val]

    width = _parse_int_setting(settings, "maximum_width", "minimum_width", default=800)
    height = _parse_int_setting(settings, "minimum_height", default=600)
    alignment = settings.get("alignment", "top_left")
    fps = 20
    update_interval = _parse_float_setting(settings, "update_interval", default=1.0)
    if update_interval > 0:
        fps = max(1, min(60, round(1.0 / update_interval))) if update_interval < 1 else 4
    gap_x = _parse_int_setting(settings, "gap_x", default=24)
    gap_y = _parse_int_setting(settings, "gap_y", default=24)

    project = Project(
        name=f"{name} (imported)",
        description=f"Imported from {os.path.basename(conf_path)} by Conky Studio's legacy importer.",
        canvas=CanvasSettings(
            width=width, height=height, alignment=alignment,
            gap_x=gap_x, gap_y=gap_y, fps=max(fps, 8),
        ),
    )
    project.ensure_canvas_node()

    scripts_out_dir = os.path.join(theme_dir, "_imported_scripts")
    ctx = _ImportContext(project, theme_dir, scripts_out_dir, settings)

    text_m = re.search(r"conky\.text\s*=\s*\[\[(.*)\]\]", conf_text, re.DOTALL)
    if text_m:
        parse_text_section(text_m.group(1), ctx, width)
    else:
        ctx.warnings.append(
            "No conky.text [[ ]] section found -- nothing to import from TEXT variables. "
            "If this theme draws everything via a Lua Cairo hook instead, that's handled "
            "separately below (wrapped as a Custom Lua node)."
        )

    # ---- Lua / Cairo hooks (possibly multiple files) ----
    lua_paths = _resolve_all_lua_loads(settings.get("lua_load_raw", ""), theme_dir)
    scripts_from_lua: list[str] = []
    for lua_path in lua_paths:
        if not os.path.isfile(lua_path):
            ctx.warnings.append(f"lua file not found: {lua_path}")
            continue
        lua_text = _read(lua_path)
        scripts_from_lua.extend(_scripts_mentioned_in_lua(lua_text, theme_dir))

        if "cairo_" in lua_text or "cairo." in lua_text:
            hook_name = settings.get("lua_draw_hook_post") or settings.get("lua_draw_hook_pre")
            body = _extract_draw_hook_body(lua_text, hook_name)
            # Path rewrite happens after we know all image basenames (below);
            # stash the raw body for now.
            project.add_node(NodeInstance(
                id=new_id("n"), type="visual.custom_lua", z=project.next_z(),
                label=f"Imported Lua ({os.path.basename(lua_path)})",
                props={"code": body, "x": 0, "y": 0},
            ))
            ctx.warnings.append(
                f"{os.path.basename(lua_path)} contains Cairo drawing -- helpers + the body of "
                f"{hook_name or 'the draw-hook function'} were inlined into one Custom Lua node "
                f"(surface create/destroy stripped so it uses Studio's cr/W/H). Arbitrary Cairo "
                f"isn't decomposed into native nodes by design."
            )
        click_count = parse_mouse_regions(lua_text, project)
        if click_count:
            ctx.warnings.append(
                f"Extracted {click_count} click region(s) from {os.path.basename(lua_path)} "
                f"as clickable marker nodes -- reposition/restyle them as you like."
            )

    if settings.get("lua_load_raw") and not lua_paths:
        ctx.warnings.append(
            f"lua_load pointed at {settings.get('lua_load_raw')!r} but no file was found -- "
            f"any mouse/draw-hook behavior in it was not imported."
        )

    # ---- All shell scripts in the theme (referenced or orphan) ----
    already_paths = {
        n.props.get("script_path")
        for n in project.nodes
        if n.type == "source.custom_script" and n.props.get("script_path")
    }
    theme_scripts = _list_theme_scripts(theme_dir)
    ordered: list[str] = []
    for p in scripts_from_lua + theme_scripts:
        if p not in ordered:
            ordered.append(p)

    for script_path in ordered:
        if script_path in already_paths:
            continue
        base = os.path.basename(script_path)
        # start.sh / stop.sh are theme launchers, not data sources --
        # Studio generates its own start.sh at build time.
        if base.lower() in ("start.sh", "stop.sh", "install.sh"):
            continue
        kind, mapped_type, extra = _classify_known_script(base)
        if kind == "native" and mapped_type:
            if not any(n.type == mapped_type for n in project.nodes):
                project.add_node(NodeInstance(id=new_id("n"), type=mapped_type))
            already_paths.add(script_path)
            continue
        if kind == "family" and mapped_type:
            if not any(n.type == mapped_type for n in project.nodes):
                project.add_node(NodeInstance(
                    id=new_id("n"), type=mapped_type,
                    props={"poll_mode": "execi", "poll_interval": 5},
                ))
            already_paths.add(script_path)
            continue
        # Companion scripts for pure-Lua themes (sensors.sh, weather.sh, …)
        # write cache files the Custom Lua reads -- they are not wired to a
        # visual node's input socket. Default to daemon mode so start.sh
        # keeps them running; builder includes unwired custom scripts too.
        patched = _patch_script_cache_dir(script_path, scripts_out_dir)
        if patched != script_path:
            ctx.warnings.append(
                f"Patched {base} to write its cache under the theme's .runtime-cache "
                f"(matching CACHE_DIR in the imported Custom Lua) instead of a hard-coded "
                f"HOME/.cache/... path."
            )
        body = _read_script_body_for_edit(patched)
        project.add_node(NodeInstance(
            id=new_id("n"), type="source.custom_script",
            label=f"Script: {base}",
            props={
                "script_path": patched,
                "script_body": body,
                "poll_mode": "daemon",
                "poll_interval": 5 if "sensor" in base.lower() else (
                    1800 if "weather" in base.lower() else 30
                ),
                "output_kind": (extra or {}).get("output_kind", "text"),
            },
        ))
        already_paths.add(script_path)

    if theme_scripts:
        ctx.warnings.append(
            f"Found {len(theme_scripts)} shell script(s) under the theme; each is a Custom Script "
            f"(or known native/family source) so nothing is dropped. Wire orphans to visuals as needed."
        )

    # ---- Images (assets/, images/, theme root) ----
    # Pure-Lua themes draw images *inside* the Custom Lua body, so orphan
    # Image/Icon nodes cannot be "wired into" that drawing (Custom Lua has
    # no bindable inputs). Instead we:
    #   1. Rewrite absolute paths in the Lua to IMAGES_DIR / CACHE_DIR
    #   2. Attach the absolute asset paths on the Custom Lua node itself
    #      (props["asset_paths"]) so builder copies them into images/
    # Add a separate Image/Icon manually if you want Studio features
    # (rotation, glow-on-PNG) as an independent layer on top.
    theme_images = _list_theme_images(theme_dir)
    image_basenames: set[str] = {os.path.basename(p) for p in theme_images}

    total_rewrites = 0
    for n in project.nodes:
        if n.type != "visual.custom_lua":
            continue
        code = n.props.get("code") or ""
        bootstrap = (
            "-- Path anchors injected by Conky Studio legacy importer\n"
            "local THEME_DIR = THEME_DIR\n"
            "local IMAGES_DIR = IMAGES_DIR or (THEME_DIR .. '/images')\n"
            "local ASSETS_DIR = THEME_DIR .. '/assets/'\n"
            "local CACHE_DIR = CACHE_DIR or (THEME_DIR .. '/.runtime-cache')\n\n"
        )
        if "Path anchors injected by Conky Studio" not in code:
            code = bootstrap + code
        new_code, n_rewrites = _rewrite_lua_asset_paths(code, image_basenames)
        n.props["code"] = new_code
        n.props["asset_paths"] = list(theme_images)
        total_rewrites += n_rewrites

    if theme_images:
        ctx.warnings.append(
            f"Found {len(theme_images)} image asset(s) under the theme. They are bundled "
            f"with the Custom Lua node (Build copies them into images/) and paths inside "
            f"the Lua were rewritten to IMAGES_DIR. Image/Icon nodes are *not* auto-created: "
            f"Custom Lua cannot accept wires, so a separate Image/Icon would be a second, "
            f"independent drawing. Add one manually and set its Path if you want Studio "
            f"features (rotation, glow-on-PNG, threshold swap) alongside the Lua HUD."
        )
    if total_rewrites:
        ctx.warnings.append(
            f"Rewrote {total_rewrites} absolute/HOME-relative path(s) inside "
            f"Custom Lua to use IMAGES_DIR / CACHE_DIR."
        )

    _layout_import_graph(project)
    warnings = _collapse_warnings(ctx.warnings)
    return ImportResult(project=project, warnings=warnings)


def _layout_import_graph(project: Project) -> None:
    """Park data-source / logic nodes in a left column so TEXT-mapped visuals
    (which keep their draw x/y) don't sit under a pile of overlapping boxes."""
    try:
        from conkystudio.nodes import registry as _reg
    except Exception:
        return
    sources, logics = [], []
    for n in project.nodes:
        if n.id == "canvas" or n.type == "canvas.root":
            continue
        try:
            cat = _reg.get(n.type).category
        except Exception:
            cat = ""
        if cat == "source":
            sources.append(n)
        elif cat == "logic":
            logics.append(n)
    col_x = -420.0
    y = 40.0
    for n in sources:
        n.x, n.y = col_x, y
        y += 70.0
    y = 40.0
    for n in logics:
        n.x, n.y = col_x + 200.0, y
        y += 70.0
    for n in project.nodes:
        try:
            if _reg.get(n.type).category != "visual":
                continue
        except Exception:
            continue
        px = n.props.get("x", n.props.get("cx"))
        py = n.props.get("y", n.props.get("cy"))
        if isinstance(px, (int, float)) and isinstance(py, (int, float)):
            n.x = float(px) + 40
            n.y = float(py) + 40


def _collapse_warnings(warnings: list) -> list:
    """Deduplicate near-identical warning lines and cap list length."""
    seen: dict[str, int] = {}
    order: list[str] = []
    for w in warnings:
        if not w:
            continue
        if w.startswith("Unrecognised directive"):
            continue
        if w in seen:
            seen[w] += 1
            continue
        seen[w] = 1
        order.append(w)
    out = []
    for w in order:
        c = seen.get(w, 1)
        out.append(w if c == 1 else f"{w} (×{c})")
    if len(out) > 40:
        extra = len(out) - 35
        out = out[:35] + [f"…and {extra} more notes (see Studio after import for full graph)."]
    return out


