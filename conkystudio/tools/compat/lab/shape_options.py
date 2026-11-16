import sys, os; sys.path.insert(0,"/build/src/tools")
import plugin_harness as h
from conkystudio.nodes import registry
fails=[]; n=0
shapes=["visual.star","visual.triangle","visual.circle","visual.rectangle","visual.hline","visual.vline","visual.crosshair"]
for t in shapes:
    s=registry.get(t)
    cases=[{}]
    for p in s.properties:
        if p.kind=="enum": cases+= [{p.key:c} for c in p.choices]
        if p.kind=="bool": cases.append({p.key:not p.default})
    cases += [dict(free_corners=True,x1=0,y1=-50,x2=45,y2=40,x3=-45,y3=40)] if t=="visual.triangle" else []
    for ov in cases:
        n+=1
        try: h.run_visual(s,dict(ov),t=0.9,size=(260,260))
        except Exception as e: fails.append((t,ov,str(e).splitlines()[0][:100]))
print(os.environ["HARNESS_LUA"], f"{n} shape variants,", "failures:", fails)
