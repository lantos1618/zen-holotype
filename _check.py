"""Run modules.py over the 19 module test dirs with the REAL parser."""
import os, sys
from bootstrap import modules
from bootstrap.bootstrap import parser
P = parser()
T = "tests"
def positions(d):
    out = []
    for s in [d.span] + [n[0] for n in d.notes]:
        if s is not None:
            out.append("%s:%d:%d" % (s.file, s.start[0], s.start[1]))
    return out
bad = 0
for area in ("corpus", "must-fail"):
    base = os.path.join(T, area, "modules")
    for name in sorted(os.listdir(base)):
        d = os.path.join(base, name)
        if not os.path.isdir(d): continue
        g = modules.build(d, parse=P)
        got = [("%s:%d:%d" % (x.span.file, x.span.start[0], x.span.start[1]), x.message, positions(x))
               for x in g.diags]
        if area == "corpus":
            ok = not got
            why = "" if ok else str(got)
        else:
            lines = [l.strip() for l in open(os.path.join(d, ".expected")).read().splitlines() if l.strip()]
            msg, want_pos = lines[0], lines[1:]
            text = "\n".join("%s: %s" % (p, m) for p, m, _ in got)
            seen = [p for _, _, ps in got for p in ps]
            ok = bool(got) and msg in text and all(w in seen for w in want_pos)
            why = "" if ok else "want %r %s | got %s" % (msg, want_pos, got)
        bad += 0 if ok else 1
        print("%-5s %-28s %s" % ("OK" if ok else "FAIL", name, why))
print("failures:", bad)
