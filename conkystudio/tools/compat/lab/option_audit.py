import sys, hashlib; sys.path.insert(0,"/build/src/tools")
import plugin_harness as h
from conkystudio.nodes import registry
def sig(im): 
    ba=im.bits(); ba.setsize(im.sizeInBytes()); return hashlib.md5(bytes(ba)).hexdigest()
shapes=["visual.star","visual.triangle","visual.circle","visual.rectangle","visual.hline","visual.vline","visual.crosshair"]
for t in shapes:
    s=registry.get(t); base={}
    for k in ("cx","cy"): 
        if s.prop(k): base[k]=130
    if s.prop("x") and not s.prop("cx"): base.update(x=60,y=100)
    h_ = sig(h.run_visual(s,base,t=0.7,size=(260,260))[0]); inert=[]; err=[]
    for p in s.properties:
        if p.key in base or p.key in ("scale","blend_mode"): continue
        variants=[]
        if p.kind=="enum": variants=[c for c in p.choices if c!=p.default]
        elif p.kind=="bool": variants=[not p.default]
        elif p.kind in("float","int"): variants=[p.minimum if p.default!=p.minimum else p.maximum, (p.maximum+p.minimum)/2 if p.default!=(p.maximum+p.minimum)/2 else p.maximum]
        elif p.kind=="color": variants=["#ff0000" if str(p.default).lower()!="#ff0000" else "#00ff00"]
        if not variants: continue
        changed=False
        for v in variants:
            try:
                if sig(h.run_visual(s,dict(base,**{p.key:v}),t=0.7,size=(260,260))[0])!=h_: changed=True
            except Exception as e: err.append((p.key,v,str(e).splitlines()[0][:80]))
        if not changed: inert.append(p.key)
    print(f"{t:20s} no-visible-effect: {inert}   errors: {err}")
