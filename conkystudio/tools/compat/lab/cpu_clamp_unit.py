# unit-test studio_cpu_count() parsing for real-world /sys formats, on every Lua runtime
import re, importlib, sys
sys.path.insert(0,"/build/src")
from conkystudio.codegen import lua_framework as lf
src=lf.FRAMEWORK_LUA
m=re.search(r"local _studio_cpu_count = nil.*?\n    return n\nend\n", src, re.S); fn=m.group(0)
cases={"0":1,"0-7":8,"0,2-5":6,"0-63":64,"0-3,8-11":12,"":1}
for mod in ("lupa.lua51","lupa.luajit21","lupa.lua53","lupa.lua54"):
    L=importlib.import_module(mod).LuaRuntime(); bad=[]
    for text,want in cases.items():
        L.execute("io.open=function(p,m) if p=='/sys/devices/system/cpu/present' then if %s then return nil end local d=%r return {read=function() return d end, close=function() end} end return nil end" % ("false" if text else "true", text))
        got=L.execute(fn+"\nreturn studio_cpu_count()")
        if got!=want: bad.append((text,got,want))
    print(mod,"OK" if not bad else bad)
