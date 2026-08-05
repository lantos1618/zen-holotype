from bootstrap import modules
from bootstrap.bootstrap import parser
g = modules.build("/tmp/zengate", parse=parser())
print("modules.py diagnostics:", len(g.diags))
for d in g.diags:
    print("   %s:%d:%d %s" % (d.span.file, d.span.start[0], d.span.start[1], d.message))
