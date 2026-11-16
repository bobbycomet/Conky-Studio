import sys; sys.path.insert(0,"/build/src/tools")
import plugin_harness as h
from conkystudio.nodes import registry
s=registry.get("visual.star")
styles=s.prop("style").choices; print(styles)
base=dict(cx=130,cy=130,radius=100,line_width=2.5,fill=True)
imgs=[h.run_visual(s,dict(base,style=st),size=(260,260))[0] for st in styles]
imgs.append(h.run_visual(s,dict(base,style="regular",points=7,inner_ratio=0.5),size=(260,260))[0])   # points/inner still work
imgs.append(h.run_visual(s,dict(base,style="pentagram",rotation_deg=-60),size=(260,260))[0])        # rotation works on styles
h.montage(imgs,4,(230,230),sys.argv[1])
