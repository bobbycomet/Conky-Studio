import sys, os, itertools, json, hashlib; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from conkystudio.hardware import discovery as d
CONKY_ALL="conky 1.19.6\n\nCompiled in features:\n X11:\n  * Xinerama extension (virtual display)\n  * ARGB visual\n Lua bindings:\n  * Cairo\n  * Imlib2\n"
CONKY_STD ="conky 1.19.6\n\nCompiled in features:\n X11:\n  * Xinerama extension (virtual display)\n  * ARGB visual\n"
CONKY_WL  ="conky 1.22.2\n\nCompiled in features:\n Wayland:\n  * Wayland\n Lua bindings:\n  * Cairo\n"
variants={"conky-all":("/usr/bin/conky",CONKY_ALL),"conky-std":("/usr/bin/conky",CONKY_STD),"conky-wayland":("/usr/bin/conky",CONKY_WL),"no-conky":(None,"")}
sess=["x11","wayland","tty","unspecified","mir",""]
desk=["","GNOME","ubuntu:GNOME","KDE","sway","Hyprland","XFCE","i3","COSMIC"]
rows=[]
for vname,(path,out) in variants.items():
    d.shutil.which=lambda n,p=path: p if n=="conky" else None
    d._run=lambda cmd,*a,**k: out
    for st,de,disp,wl in itertools.product(sess,desk,(0,1),(0,1)):
        for k in ("XDG_SESSION_TYPE","XDG_CURRENT_DESKTOP","DESKTOP_SESSION","DISPLAY","WAYLAND_DISPLAY"): os.environ.pop(k,None)
        if st: os.environ["XDG_SESSION_TYPE"]=st
        if de: os.environ["XDG_CURRENT_DESKTOP"]=de
        if disp: os.environ["DISPLAY"]=":0"
        if wl: os.environ["WAYLAND_DISPLAY"]="wayland-0"
        s=d.detect_session()
        rows.append([vname,st,de,disp,wl,s.display_server,s.severity,s.title,s.recommended_window_type,s.overlay_likely])
json.dump(rows,open(sys.argv[1],"w"))
if len(sys.argv) > 2:                      # python session_matrix.py out.json session_golden.json
    gold = json.load(open(sys.argv[2])); diff = [(g, r) for g, r in zip(gold, rows) if g != r]
    print(len(diff), "scenario(s) differ from the golden file")
    for g, r in diff[:10]: print("  golden:", g[:5], g[5:8], "\n  now:   ", r[:5], r[5:8])
    sys.exit(1 if diff else 0)
print(len(rows),"scenarios; md5",hashlib.md5(json.dumps(rows).encode()).hexdigest()[:10])
