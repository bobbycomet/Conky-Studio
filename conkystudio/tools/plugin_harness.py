#!/usr/bin/env python3
"""
Plugin harness -- runs every plugin in a plugins.json through the REAL loader +
code generator, executes the generated Lua in an embedded interpreter against a
Cairo shim (drawn with Qt's QPainter), and reports PASS/FAIL per plugin.

    QT_QPA_PLATFORM=offscreen python tools/plugin_harness.py plugins.json [--render outdir] [--only id,id]

Checks per plugin
  logic  : registers, generated expression compiles, evaluates (default props, and
           every enum choice), returns a value of the declared output_kind
  visual : registers, generated draw function compiles, runs at two clock times
           without a Lua error, only calls cairo functions Conky's binding provides,
           and (position stage) gets a draggable stage proxy
Requires: pip install lupa PyQt6   (run from the repo root so `conkystudio` imports)
"""
from __future__ import annotations
import argparse, json, math, os, sys, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import importlib
_LUA = os.environ.get('HARNESS_LUA', 'lupa.lua54')   # lupa.lua51 / lupa.lua53 / lupa.lua54 / lupa.luajit21
LuaRuntime = importlib.import_module(_LUA).LuaRuntime
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (QLinearGradient, QRadialGradient, QGradient, QImage, QPainter, QPainterPath, QColor, QPen, QBrush, QFont,
                          QFontMetricsF, QGuiApplication)

import conkystudio.nodes                       # noqa: F401  populate registry
from conkystudio.nodes import registry
from conkystudio.plugins import loader
from conkystudio.plugins.schema import PluginManifest
from conkystudio.codegen import lua_gen
from conkystudio.model.project import Project, NodeInstance, new_id

_app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

PRELUDE = r'''
STATE = {}
SRC = {}
function clamp(v, lo, hi) if v < lo then return lo elseif v > hi then return hi end return v end
function lerp(a, b, t) return a + (b - a) * t end
function wall_clock() return __T end
function studio_heat_rgb(t)
  t = clamp(tonumber(t) or 0, 0, 1)
  if t < 0.5 then local u = t * 2
    return lerp(0.31, 0.96, u), lerp(0.82, 0.84, u), lerp(0.77, 0.25, u) end
  local u = (t - 0.5) * 2
  return lerp(0.96, 0.88, u), lerp(0.84, 0.25, u), lerp(0.25, 0.25, u)
end
function rounded_rect(cr, x, y, w, h, r)
  r = math.min(r, w / 2, h / 2)
  cairo_new_sub_path(cr)
  cairo_arc(cr, x + w - r, y + r, r, -math.pi / 2, 0)
  cairo_arc(cr, x + w - r, y + h - r, r, 0, math.pi / 2)
  cairo_arc(cr, x + r, y + h - r, r, math.pi / 2, math.pi)
  cairo_arc(cr, x + r, y + r, r, math.pi, 3 * math.pi / 2)
  cairo_close_path(cr)
end
function studio_draw_text(cr, text, x, y, o)
  o = o or {}
  cairo_set_font_size(cr, o.size or 12)
  cairo_set_source_rgba(cr, o.r or 1, o.g or 1, o.b or 1, o.a or 1)
  cairo_move_to(cr, x - (o.align == 'center' and 20 or 0), y); cairo_show_text(cr, tostring(text))
end
tolua = { takeownership = function() end }
cairo_text_extents_t = { create = function() return { width = 0, height = 0, x_bearing = 0, y_bearing = 0 } end }
'''
for _n in ("CAIRO_LINE_CAP_BUTT CAIRO_LINE_CAP_ROUND CAIRO_LINE_CAP_SQUARE "
           "CAIRO_LINE_JOIN_MITER CAIRO_LINE_JOIN_ROUND CAIRO_LINE_JOIN_BEVEL "
           "CAIRO_FONT_SLANT_NORMAL CAIRO_FONT_SLANT_ITALIC CAIRO_FONT_WEIGHT_NORMAL "
           "CAIRO_FONT_WEIGHT_BOLD CAIRO_EXTEND_NONE CAIRO_EXTEND_PAD CAIRO_EXTEND_REPEAT CAIRO_EXTEND_REFLECT").split():
    PRELUDE += f"{_n} = '{_n}'\n"


class Pat:
    def __init__(self, kind, args): self.kind, self.args, self.stops, self.spread = kind, args, [], QGradient.Spread.PadSpread
    def brush(self):
        g = QLinearGradient(*self.args) if self.kind == "linear" else QRadialGradient(self.args[0], self.args[1], self.args[5], self.args[3], self.args[4])
        g.setSpread(self.spread)
        for off, c in self.stops: g.setColorAt(max(0.0, min(1.0, float(off))), c)
        return QBrush(g)


class Shim:
    """The subset of Conky's Lua Cairo binding the plugins may use."""
    def __init__(self, lua, w, h, bg="#0d1117"):
        self.lua, self.w, self.h = lua, w, h
        self.img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        self.img.fill(QColor(bg))
        self.p = QPainter(self.img)
        self.p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.path, self.cur, self.sub = self._newpath(), None, True
        self.src, self.lw, self.cap, self.join, self.fs = (1, 1, 1, 1), 1.0, Qt.PenCapStyle.FlatCap, Qt.PenJoinStyle.MiterJoin, 12.0
        self.stack, self.calls = [], 0
        g = lua.globals()
        for name in dir(self):
            if name.startswith("cairo_"):
                g[name] = getattr(self, name)

    def finish(self):
        self.p.end()
        return self.img
    # state
    def cairo_save(self, cr): self.p.save(); self.stack.append((self.src, self.lw, self.cap, self.join, self.fs))
    def cairo_restore(self, cr):
        self.p.restore(); self.src, self.lw, self.cap, self.join, self.fs = self.stack.pop()
    def cairo_translate(self, cr, x, y): self.p.translate(x, y)
    def cairo_rotate(self, cr, a): self.p.rotate(math.degrees(a))
    def cairo_scale(self, cr, x, y): self.p.scale(x, y)
    def cairo_set_source_rgba(self, cr, r, g, b, a): self.src = (r, g, b, a)
    def cairo_set_source_rgb(self, cr, r, g, b): self.src = (r, g, b, 1)
    def cairo_set_source(self, cr, pat): self.src = pat
    def cairo_pattern_create_linear(self, x0, y0, x1, y1): return Pat("linear", (x0, y0, x1, y1))
    def cairo_pattern_create_radial(self, x0, y0, r0, x1, y1, r1): return Pat("radial", (x0, y0, r0, x1, y1, r1))
    def cairo_pattern_add_color_stop_rgba(self, pat, off, r, g, b, a):
        pat.stops.append((off, QColor.fromRgbF(*(max(0.0, min(1.0, float(v))) for v in (r, g, b, a)))))
    def cairo_pattern_set_extend(self, pat, mode):
        pat.spread = {"CAIRO_EXTEND_REPEAT": QGradient.Spread.RepeatSpread, "CAIRO_EXTEND_REFLECT": QGradient.Spread.ReflectSpread}.get(str(mode), QGradient.Spread.PadSpread)
    def cairo_pattern_destroy(self, pat): pass
    def cairo_set_line_width(self, cr, w): self.lw = w
    def cairo_set_line_cap(self, cr, c): self.cap = {"CAIRO_LINE_CAP_ROUND": Qt.PenCapStyle.RoundCap, "CAIRO_LINE_CAP_SQUARE": Qt.PenCapStyle.SquareCap}.get(str(c), Qt.PenCapStyle.FlatCap)
    def cairo_set_line_join(self, cr, j): self.join = {"CAIRO_LINE_JOIN_ROUND": Qt.PenJoinStyle.RoundJoin, "CAIRO_LINE_JOIN_BEVEL": Qt.PenJoinStyle.BevelJoin}.get(str(j), Qt.PenJoinStyle.MiterJoin)
    def cairo_select_font_face(self, cr, fam, sl, wt): pass
    def cairo_set_font_size(self, cr, s): self.fs = float(s)
    # path
    @staticmethod
    def _newpath():
        p = QPainterPath(); p.setFillRule(Qt.FillRule.WindingFill)   # Cairo's default rule
        return p
    def cairo_new_path(self, cr): self.path = self._newpath(); self.cur = None
    def cairo_new_sub_path(self, cr): self.sub = True
    def cairo_move_to(self, cr, x, y): self.path.moveTo(x, y); self.cur = (x, y); self.sub = False
    def cairo_line_to(self, cr, x, y):
        if self.cur is None: self.path.moveTo(x, y)
        else: self.path.lineTo(x, y)
        self.cur = (x, y); self.sub = False
    def cairo_close_path(self, cr): self.path.closeSubpath()
    def cairo_rectangle(self, cr, x, y, w, h): self.path.addRect(x, y, w, h); self.cur = (x, y)
    def cairo_arc(self, cr, xc, yc, r, a0, a1):
        if a1 < a0: a1 += 2 * math.pi * math.ceil((a0 - a1) / (2 * math.pi))
        n = max(8, int(abs(a1 - a0) / (math.pi / 36)))
        pts = [(xc + r * math.cos(a0 + (a1 - a0) * i / n), yc + r * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]
        if self.cur is None or self.sub: self.path.moveTo(*pts[0])
        else: self.path.lineTo(*pts[0])
        for q in pts[1:]: self.path.lineTo(*q)
        self.cur, self.sub = pts[-1], False
    def cairo_clip(self, cr): self.p.setClipPath(self.path, Qt.ClipOperation.IntersectClip); self.cairo_new_path(cr)
    # paint
    def _brush(self):
        return self.src.brush() if isinstance(self.src, Pat) else QBrush(self._color())
    def _color(self):
        r, g, b, a = self.src
        return QColor.fromRgbF(*(max(0.0, min(1.0, float(v))) for v in (r, g, b, a)))
    def cairo_fill_preserve(self, cr):
        self.p.setPen(Qt.PenStyle.NoPen); self.p.setBrush(self._brush()); self.p.drawPath(self.path)
    def cairo_fill(self, cr): self.cairo_fill_preserve(cr); self.cairo_new_path(cr)
    def cairo_stroke_preserve(self, cr):
        pen = QPen(self._brush(), max(0.01, float(self.lw))); pen.setCapStyle(self.cap); pen.setJoinStyle(self.join)
        self.p.setPen(pen); self.p.setBrush(Qt.BrushStyle.NoBrush); self.p.drawPath(self.path)
    def cairo_stroke(self, cr): self.cairo_stroke_preserve(cr); self.cairo_new_path(cr)
    # text
    def _font(self): f = QFont("DejaVu Sans"); f.setPixelSize(max(1, int(self.fs))); return f
    def cairo_text_extents(self, cr, text, ext):
        fm = QFontMetricsF(self._font()); r = fm.tightBoundingRect(str(text))
        ext["width"], ext["height"], ext["x_bearing"], ext["y_bearing"] = r.width(), r.height(), r.x(), r.y()
    def cairo_show_text(self, cr, text):
        if self.cur is None: return
        self.p.setFont(self._font()); self.p.setPen(self._color()); self.p.drawText(QPointF(*self.cur), str(text))


def _node_for(spec, overrides=None):
    props = spec.defaults(); props.update(overrides or {})
    return NodeInstance(id=new_id("n"), type=spec.type, x=0, y=0, props=props)

def _ctx(node):
    p = Project(); p.add_node(node); return lua_gen.ResolveContext(p)

def _new_lua(t):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.globals().__T = t
    lua.execute(PRELUDE)
    return lua

def run_logic(spec, overrides=None, t=0.0):
    node = _node_for(spec, overrides)
    expr = lua_gen._LOGIC_GENERATORS[spec.type](node, _ctx(node))
    return _new_lua(t).execute("return " + expr), expr

def run_visual(spec, overrides=None, t=0.0, size=(360, 360)):
    node = _node_for(spec, overrides)
    code = lua_gen._VISUAL_GENERATORS[spec.type](node, _ctx(node))
    fn_name = f"draw_node_{lua_gen.lua_safe_id(node.id)}"
    lua = _new_lua(t); sh = Shim(lua, *size)
    try:
        lua.execute(code + f"\n__draw = {fn_name}")
        lua.globals().__draw(object(), size[0], size[1])
    finally:
        img = sh.finish()
    return img, code

def montage(images, cols, cell, out, bg="#0d1117"):
    rows = (len(images) + cols - 1) // cols
    m = QImage(cols * cell[0], rows * cell[1], QImage.Format.Format_ARGB32_Premultiplied); m.fill(QColor(bg))
    p = QPainter(m)
    for i, im in enumerate(images):
        p.drawImage((i % cols) * cell[0], (i // cols) * cell[1], im.scaled(*cell, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    p.end(); m.save(str(out))

def check_stage(spec):
    from conkystudio.ui.studio.position_stage import _position_keys, _estimate_size
    n = _node_for(spec)
    k = _position_keys(n)
    return (None if k is None else (k, _estimate_size(n)))

def check_plugin(spec, outdir=None):
    problems = []
    if spec.category == "logic":
        cases = [None]
        for p in spec.properties:
            if p.kind == "enum" and p.choices:
                cases += [{p.key: c} for c in p.choices]
        for ov in cases:
            try:
                val, _ = run_logic(spec, ov)
                ok = (isinstance(val, str) if spec.output_kind == "text" else isinstance(val, (int, float)))
                if not ok: problems.append(f"{ov or 'defaults'}: returned {type(val).__name__} {val!r}, expected {spec.output_kind}")
            except Exception as e:
                problems.append(f"{ov or 'defaults'}: {str(e).splitlines()[0][:140]}")
    elif spec.category == "visual":
        imgs = []
        for t in (0.0, 1.3):
            try:
                im, _ = run_visual(spec, t=t); imgs.append(im)
            except Exception as e:
                problems.append(f"t={t}: {str(e).splitlines()[0][:140]}"); break
        if imgs and outdir:
            montage(imgs, len(imgs), (260, 260), Path(outdir) / f"{spec.type}.png")
        if check_stage(spec) is None:
            problems.append("no stage proxy (Position Stage cannot show/drag it: needs cx/cy or x/y position props)")
    return problems

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("manifest"); ap.add_argument("--render"); ap.add_argument("--only")
    a = ap.parse_args()
    if a.render: Path(a.render).mkdir(parents=True, exist_ok=True)
    manifest = PluginManifest.from_dict(json.load(open(a.manifest)), source=a.manifest)
    only = set(a.only.split(",")) if a.only else None
    bad = 0; total = 0
    for pl in manifest.plugins:
        if only and pl.id not in only: continue
        total += 1
        try:
            loader.register_plugin(pl, source=a.manifest)
        except Exception as e:
            print(f"FAIL {pl.id}\n     register: {e}"); bad += 1; continue
        probs = check_plugin(registry.get(pl.id), a.render)
        if probs:
            bad += 1; print(f"FAIL {pl.id}"); [print("     " + x) for x in probs]
        else:
            print(f"PASS {pl.id}")
    print(f"\n{total - bad}/{total} plugins passed")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
