#!/usr/bin/env python3
"""Replace (or add) a plugin in plugins.json by id:
    python merge_plugin.py plugins.json neon_geometry.plugin.json
A .bak copy of plugins.json is written first."""
import json, shutil, sys
man, new = sys.argv[1], sys.argv[2]
d = json.load(open(man, encoding="utf-8")); n = json.load(open(new, encoding="utf-8"))
shutil.copy(man, man + ".bak")
for i, p in enumerate(d["plugins"]):
    if p.get("id") == n["id"]:
        d["plugins"][i] = n; print("replaced", n["id"]); break
else:
    d["plugins"].append(n); print("added", n["id"])
json.dump(d, open(man, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
