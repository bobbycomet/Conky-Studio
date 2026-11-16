import sys, os, shutil; sys.path.insert(0,"/build/src")
from PyQt6.QtWidgets import QApplication; _a=QApplication([])
import conkystudio.nodes
from conkystudio.nodes import registry
from conkystudio.model.project import Project, NodeInstance, new_id
from conkystudio.codegen import builder
OUT="/build/fuzz"; shutil.rmtree(OUT,ignore_errors=True); os.makedirs(OUT)
natives=[s for s in registry.by_category("source") if s.script_family is None and not s.scripted]
n=0; names=[]
for s in natives:
    variants=[("default",{})]
    for p in s.properties:
        if p.kind=="enum": variants+= [(f"{p.key}={c}",{p.key:c}) for c in p.choices if c!=p.default]
        elif p.kind in("string","path"): variants+= [(f"{p.key}={v!r}",{p.key:v}) for v in ("nonexistent0","/nonexistent","BAT9","")]
    for label,ov in variants:
        pr=Project(); pr.name="fz"; pr.canvas.width=300; pr.canvas.height=80
        src=pr.add_node(NodeInstance(id=new_id("n"),type=s.type,x=0,y=0,props={**s.defaults(),**ov}))
        txt=pr.add_node(NodeInstance(id=new_id("n"),type="visual.text",x=0,y=0,z=pr.next_z(),props={"x":10,"y":30,"value":""}))
        pr.add_edge(src.id,txt.id,"value")
        name=f"{n:03d}"; builder.build_project(pr,f"{OUT}/{name}"); open(f"{OUT}/{name}/LABEL","w").write(f"{s.type} {label}"); names.append(name); n+=1
print(n,"scenarios over",len(natives),"native source types")
