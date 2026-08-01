"""
Headless smoke tests. Run with: python3 -m pytest tests/ -v
(or just `python3 tests/test_codegen_smoke.py` -- it also works as a
plain script with no pytest dependency, since CI for a project like this
shouldn't require installing a test framework just to sanity-check that
the code generator still produces valid Lua).

What's checked, cheapest first:
  1. every registered visual node type has a Lua generator (nodes you
     can drag onto the canvas can never silently compile to nothing)
  2. every bundled template builds with zero warnings
  3. every bundled template's render.lua is valid Lua (via luac -p,
     skipped with a note if luac isn't on PATH)
  4. (optional, needs a real X display + conky installed) an actual
     built project renders non-trivial pixel content -- this is the
     same Xvfb + ImageMagick check used while building the app, kept
     here so a real behavior change gets caught, not just a syntax slip
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import conkystudio.nodes  # noqa: F401 -- populates the registry
from conkystudio.nodes import registry
from conkystudio.model.project import Project
from conkystudio.codegen import lua_gen, builder

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(REPO_ROOT, "templates")


def test_every_visual_node_has_a_generator():
    lua_gen.assert_full_coverage()


def test_templates_build_and_produce_valid_lua():
    luac = shutil.which("luac5.1") or shutil.which("luac")
    template_paths = sorted(glob.glob(os.path.join(TEMPLATES_DIR, "*.json")))
    assert template_paths, f"No templates found in {TEMPLATES_DIR}"

    with tempfile.TemporaryDirectory(prefix="conky-studio-test-") as tmp:
        for path in template_paths:
            name = os.path.splitext(os.path.basename(path))[0]
            project = Project.load(path)
            out_dir = os.path.join(tmp, name)
            result = builder.build_project(project, out_dir)
            assert not result.warnings, f"{name}: unexpected build warnings: {result.warnings}"
            assert os.path.isfile(result.conky_conf_path)
            assert os.path.isfile(result.render_lua_path)
            assert os.path.isfile(result.start_sh_path)

            if luac:
                proc = subprocess.run([luac, "-p", result.render_lua_path], capture_output=True, text=True)
                assert proc.returncode == 0, f"{name}: invalid Lua -- {proc.stderr}"


def test_custom_project_covering_every_node_type_builds():
    """Exercises one instance of every registered node type in a single
    project, wired together where kinds allow -- catches interactions
    between node types that per-template tests might not happen to hit."""
    from conkystudio.model.project import NodeInstance, new_id

    p = Project(name="Coverage Test")
    p.ensure_canvas_node()
    sources = {}
    for spec in registry.by_category("source"):
        props = dict(spec.defaults())
        if spec.type == "source.custom_script":
            props["script_path"] = "/bin/echo"
        n = p.add_node(NodeInstance(id=new_id("n"), type=spec.type, props=props))
        sources[spec.type] = n

    numeric_source = sources["source.cpu_percent"]
    category_source = sources["source.weather_category"]

    logic_nodes = {}
    for spec in registry.by_category("logic"):
        n = p.add_node(NodeInstance(id=new_id("n"), type=spec.type, props=dict(spec.defaults())))
        logic_nodes[spec.type] = n
        for pspec in spec.bindable_properties():
            if pspec.accepts and registry.KIND_CATEGORY in pspec.accepts:
                p.add_edge(category_source.id, n.id, pspec.key)
            elif pspec.accepts:
                p.add_edge(numeric_source.id, n.id, pspec.key)

    # a couple of visuals fed from logic-node outputs, not just raw sources,
    # so the topological-order path in refresh_sources() gets exercised too
    if "logic.math" in logic_nodes:
        math_node = logic_nodes["logic.math"]
        gauge = p.add_node(NodeInstance(id=new_id("n"), type="visual.arc_gauge", props=registry.get("visual.arc_gauge").defaults()))
        p.add_edge(math_node.id, gauge.id, "value")
    if "logic.string_format" in logic_nodes:
        fmt_node = logic_nodes["logic.string_format"]
        label = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", props=registry.get("visual.text").defaults()))
        p.add_edge(fmt_node.id, label.id, "value")

    for spec in registry.by_category("visual"):
        n = p.add_node(NodeInstance(id=new_id("n"), type=spec.type, props=dict(spec.defaults())))
        for pspec in spec.bindable_properties():
            if pspec.accepts and registry.KIND_CATEGORY in pspec.accepts:
                p.add_edge(category_source.id, n.id, pspec.key)
            elif pspec.accepts:
                p.add_edge(numeric_source.id, n.id, pspec.key)

    with tempfile.TemporaryDirectory(prefix="conky-studio-coverage-") as tmp:
        result = builder.build_project(p, tmp)
        luac = shutil.which("luac5.1") or shutil.which("luac")
        if luac:
            proc = subprocess.run([luac, "-p", result.render_lua_path], capture_output=True, text=True)
            assert proc.returncode == 0, f"Coverage project produced invalid Lua -- {proc.stderr}"


def test_render_produces_visible_pixels_if_display_available():
    """Best-effort: skips quietly if conky/Xvfb/ImageMagick aren't
    installed rather than failing CI on machines that don't have a
    virtual display set up."""
    conky = shutil.which("conky")
    xvfb = shutil.which("Xvfb")
    imagemagick = shutil.which("import")
    if not (conky and xvfb and imagemagick):
        print("SKIPPED (needs conky + Xvfb + ImageMagick 'import' on PATH)")
        return

    project = Project.load(os.path.join(TEMPLATES_DIR, "glow_radial_gauge.json"))
    with tempfile.TemporaryDirectory(prefix="conky-studio-render-test-") as tmp:
        builder.build_project(project, tmp)
        screenshot = os.path.join(tmp, "_test_screenshot.png")
        display_num = 70 + (os.getpid() % 20)  # avoid colliding with a concurrently-running Xvfb
        script = (
            f'Xvfb :{display_num} -screen 0 400x400x24 -ac >/dev/null 2>&1 & sleep 1; '
            f'cd "{tmp}" && DISPLAY=:{display_num} conky -c conky.conf >/dev/null 2>&1 & sleep 3; '
            f'DISPLAY=:{display_num} import -window root "{screenshot}"; '
            f'pkill -9 conky >/dev/null 2>&1; pkill -9 -f "Xvfb :{display_num}" >/dev/null 2>&1; true'
        )
        subprocess.run(["bash", "-c", script], timeout=20)
        assert os.path.isfile(screenshot), "Screenshot was not produced -- Conky likely failed to start"
        assert os.path.getsize(screenshot) > 1000, "Screenshot suspiciously small"


def test_plugin_system_registers_and_generates_valid_lua():
    from conkystudio.plugins.schema import PluginNode, PluginProperty
    from conkystudio.plugins import loader as plugin_loader
    from conkystudio.model.project import NodeInstance, new_id

    clamp = PluginNode(
        id="logic._test_clamp", category="logic", label="Test Clamp",
        output_kind=registry.KIND_NUMBER,
        properties=[
            PluginProperty(key="input", label="Input", kind="float", default=0.0, bindable=True,
                            accepts=[registry.KIND_NUMBER, registry.KIND_PERCENT]),
            PluginProperty(key="lo", label="Min", kind="float", default=0.0),
            PluginProperty(key="hi", label="Max", kind="float", default=100.0),
        ],
        lua_expr="clamp(({input}), ({lo}), ({hi}))",
    )
    dot = PluginNode(
        id="visual._test_dot", category="visual", label="Test Dot",
        properties=[PluginProperty(key="radius", label="Radius", kind="int", default=8)],
        lua_draw_body="    cairo_arc(cr, 10, 10, {radius}, 0, 2*math.pi)\n    cairo_fill(cr)",
    )
    plugin_loader.register_plugin(clamp)
    plugin_loader.register_plugin(dot)
    assert registry.has("logic._test_clamp") and registry.has("visual._test_dot")
    lua_gen.assert_full_coverage()

    p = Project(name="Plugin Coverage")
    p.ensure_canvas_node()
    cpu = p.add_node(NodeInstance(id=new_id("n"), type="source.cpu_percent"))
    clamp_node = p.add_node(NodeInstance(id=new_id("n"), type="logic._test_clamp"))
    label = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=0))
    p.add_node(NodeInstance(id=new_id("n"), type="visual._test_dot", z=1))
    p.add_edge(cpu.id, clamp_node.id, "input")
    p.add_edge(clamp_node.id, label.id, "value")

    lua_code = lua_gen.build_render_lua(p, {}, header_comment="-- plugin coverage test")
    luac = shutil.which("luac5.1") or shutil.which("luac")
    if luac:
        with tempfile.NamedTemporaryFile(suffix=".lua", mode="w", delete=False) as f:
            f.write(lua_code)
            path = f.name
        proc = subprocess.run([luac, "-p", path], capture_output=True, text=True)
        os.remove(path)
        assert proc.returncode == 0, f"Plugin-generated Lua was invalid -- {proc.stderr}"


def test_mouse_click_handler_fires_correctly():
    """Conky's lua_mouse_hook calls the configured function name LITERALLY,
    with no 'conky_' prefix -- unlike lua_draw_hook_post/_pre, which DO
    prepend it. That inconsistency was only caught by empirically
    xdotool-clicking a real Conky window; this test locks the fix in
    place by loading the generated file (with a stub cairo module, since
    a bare lua5.1 interpreter has no Cairo binding) and calling the
    handler directly -- isolating the logic from X11/window-manager
    noise, which turned out to make raw-Xvfb click delivery unreliable
    for reasons unrelated to the generated code."""
    from conkystudio.model.project import NodeInstance, new_id

    luac_dir = shutil.which("lua5.1")
    if not luac_dir:
        print("SKIPPED (needs lua5.1 on PATH)")
        return

    p = Project(name="Click Test")
    p.ensure_canvas_node()
    btn = p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=0,
                      props={"value": "[Click Me]", "x": 50, "y": 50}))
    marker = tempfile.mktemp(prefix="conky-studio-click-test-")
    btn.on_click_command = f"touch {marker}"
    btn.click_x, btn.click_y, btn.click_w, btn.click_h = 40, 30, 100, 40

    assert lua_gen.has_clickable_nodes(p)

    with tempfile.TemporaryDirectory(prefix="conky-studio-mousetest-") as tmp:
        result = builder.build_project(p, tmp)
        assert "lua_mouse_hook" in open(result.conky_conf_path).read()

        stub_dir = os.path.join(tmp, "_luastub")
        os.makedirs(stub_dir, exist_ok=True)
        with open(os.path.join(stub_dir, "cairo.lua"), "w") as f:
            f.write("return {}\n")

        driver = os.path.join(tmp, "_driver.lua")
        with open(driver, "w") as f:
            f.write(
                "conky_window = { width = 300, height = 200 }\n"
                "function conky_parse(s) return '0' end\n"
                f"dofile('{result.render_lua_path}')\n"
                "mouse_handler({ type = 'button_down', button = 'left', x = 80, y = 50 })\n"
            )
        env = dict(os.environ)
        env["LUA_PATH"] = f"{stub_dir}/?.lua;;"
        proc = subprocess.run(["lua5.1", driver], capture_output=True, text=True, env=env, cwd=tmp)
        assert proc.returncode == 0, f"mouse handler script errored: {proc.stderr}"
        assert os.path.isfile(marker), "clicking inside the region did not fire on_click_command"
        os.remove(marker)


def test_large_project_does_not_hit_lua_upvalue_limit():
    """Lua 5.1 hard-limits a function to 60 upvalues. A large real-world
    project (a legacy theme import easily has 70+ visual nodes) used to
    blow past that because main_draw_impl called each draw_node_X
    function by name, making every single one an upvalue -- caught by
    actually running luac against an imported 97-node real theme, not
    just by re-reading the generator code. Locks that fix in with a
    smaller synthetic project (70 Text nodes) so this doesn't need the
    original theme file to regress-test."""
    from conkystudio.model.project import NodeInstance, new_id

    p = Project(name="Upvalue Limit Test")
    p.ensure_canvas_node()
    for i in range(70):
        p.add_node(NodeInstance(id=new_id("n"), type="visual.text", z=i, props={"value": f"Line {i}"}))

    lua_code = lua_gen.build_render_lua(p, {}, header_comment="-- upvalue limit test")
    luac = shutil.which("luac5.1") or shutil.which("luac")
    if not luac:
        print("SKIPPED (needs luac5.1 on PATH)")
        return
    with tempfile.NamedTemporaryFile(suffix=".lua", mode="w", delete=False) as f:
        f.write(lua_code)
        path = f.name
    proc = subprocess.run([luac, "-p", path], capture_output=True, text=True)
    os.remove(path)
    assert proc.returncode == 0, f"70-node project produced invalid Lua -- {proc.stderr}"
    assert "DRAW_ORDER" in lua_code, "expected the DRAW_ORDER table pattern to be in use"


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_") and callable(obj)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
    sys.exit(1 if failures else 0)
