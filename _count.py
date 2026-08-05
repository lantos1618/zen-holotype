from bootstrap import modules
from bootstrap.bootstrap import parser
g = modules.build("/tmp/zenstd", parse=parser())
print("modules.py diagnostics:", len(g.diags))
for d in g.diags:
    print("   %s:%d:%d %s" % (d.span.file, d.span.start[0], d.span.start[1], d.message))
def show(m, n):
    i = g.module("src."+m)
    print("  %-26s %-9s decls=%d exports=%d scope=%d" % (m, n, len(i.decls.get(n,())),
          len(i.exports.get(n,())), len(i.scope.get(n,()))))
show("std.core.loop.loop_iter","loop"); show("std.core.loop.loop","loop")
show("std.core.core","loop"); show("std.text.text_utf8","loop"); show("main","loop")
show("std.core.result","Res"); show("std.core.core","Res"); show("main","Res")
show("std.core.result","Ok");  show("std.core.core","Ok");  show("main","Ok")
show("std.core.core","Display"); show("std.std","Display")
print("entities Res:", {k: len(v) for k,v in g.entities.items() if k.endswith('::Res')})
