import sys, os, json; sys.path.insert(0,"/build/src"); sys.path.insert(0,"/build/src/tools")
from PyQt6.QtWidgets import QApplication; _a=QApplication([])
import conkystudio.nodes
from conkystudio.nodes import registry
from conkystudio.model.project import Project, NodeInstance, new_id
from conkystudio.codegen import builder, theme_presets
from conkystudio.plugins import loader
from conkystudio.plugins.schema import PluginManifest
OUT="/build/themes"
for f in ("fixtures.json","neon_only.json"):
    for pl in PluginManifest.from_dict(json.load(open(f"{OUT}/{f}"))).plugins: loader.register_plugin(pl)
n=0
for t in theme_presets.list_themes():
    for tier in ("Simple","Showcase"):
        p=theme_presets.build_theme(Project(),t.id,tier); p.name=f"{t.id}-{tier}"
        builder.build_project(p,f"{OUT}/{t.id}_{tier}"); n+=1
# kitchen sink: every visual node type (built-in + plugin visuals) at default props, in a grid
p=Project(); p.name="kitchen-sink"
vis=[s for s in registry.by_category("visual")]
for i,s in enumerate(vis):
    props=s.defaults()
    for k in ("cx","x"): 
        if k in props: props[k]=60+(i%8)*110
    for k in ("cy","y"):
        if k in props: props[k]=60+(i//8)*110
    p.add_node(NodeInstance(id=new_id("n"),type=s.type,x=0,y=0,z=p.next_z(),props=props))
p.canvas.width=1000; p.canvas.height=900
builder.build_project(p,f"{OUT}/kitchen_sink"); n+=1
print("generated",n,"themes;",len(vis),"visual node types in kitchen sink")
