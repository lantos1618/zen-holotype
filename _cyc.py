from bootstrap import modules
from bootstrap.bootstrap import parser
g = modules.build("/tmp/zenstd", parse=parser())
# is the import cycle still structurally there?
seen, stack = [], [("src.std.core.core", ["core"])]
while stack:
    d, path = stack.pop()
    for dep in g.module(d).deps:
        nm = g.module(dep).name
        if dep == "src.std.core.core":
            print("import cycle present and ACCEPTED:", " -> ".join(path + [nm])); stack = []; break
        if dep not in seen:
            seen.append(dep); stack.append((dep, path + [nm]))
print("init-dependency edges between modules:",
      sum(len(v) for v in modules._init_edges(g).values()))
