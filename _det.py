from bootstrap import modules
from bootstrap.bootstrap import parser
sig = None
for i in range(3):
    g = modules.build("/tmp/zenstd", parse=parser())
    s = (tuple((d.span.file, d.span.start, d.message) for d in g.diags),
         tuple(g.order),
         tuple((k, len(v)) for k, v in g.entities.items()))
    assert sig is None or s == sig, "NONDETERMINISTIC"
    sig = s
print("3 builds identical:", len(sig[1]), "modules,", len(sig[2]), "qualified names,", len(sig[0]), "diags")
