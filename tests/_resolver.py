"""S1 FULL MODULE RESOLVER — the import GRAPH + per-module NAMESPACES the flat check_linked lacks.

`tests/_oracle.check_linked_count` recovered cross-module type-checking by flat-concatenating the
import-stripped bodies of a module's DIRECT imports into one lib and reducing it to a header. That is
enough for the real stdlib only because its direct-import sets happen not to clash — but it is NOT a
real resolver:

  * NO transitive imports. If A imports B and B imports a type from C, A's lib (B's body only) lacks
    C's definition; a re-exported name would resolve to nothing.
  * NO per-module namespacing. Two modules that each define a private helper `is_intrinsic` (genjs +
    check_validate) or each EXPORT `eq` (str + ast) collide the moment both land in one flat lib:
    check_validate's dup_name_errs fires on the second `eq` and the module false-positives. The flat
    driver dodges this only by never pulling two clashing modules into the same lib — a genuine
    cross-module clash IS a noted false-positive risk.

THE REAL THING, built here (pure harness — touches NO compiler SOURCE, so zero fixpoint risk):

  1. module_graph()  — parse every std/compiler import line into the name->defining-module map and the
                       module->[imported modules] edge set (the DImport graph).
  2. topo_order()    — Kahn topological sort of that graph (cycle-tolerant: a back edge is reported).
  3. resolve(target) — the per-module NAMESPACED world for `target`: the transitive closure of the
                       modules `target` reaches, then DEDUPLICATED so each top-level NAME survives
                       exactly once, as the decl from the module the import chain resolves it to. A
                       private helper that two modules share collapses to one (harmless — headers are
                       bodyless sigs); two modules that export the same name never both leak, because
                       only the modules on `target`'s real import closure are present. That dedup IS
                       the per-module namespace: `target`'s `eq` is str.eq, never ast.eq.

The resolved world is handed to check_linked as the `lib`; the binary's module_header reduces it to
signatures and check_module verifies `target`'s imported calls against the RESOLVED definitions. NO
Python compiler runs — only the committed `zenc` binary + cc, via _oracle.

A top-level decl is split brace-aware (depth back to 0). This is harness text-processing, not a Zen
parser; the stdlib's top-level forms (foreign sig line, `name* = (..) ret { .. }`, `Name*: { .. }`,
`Name*: A(..) | B`) are all covered, and the split is validated against the binary (every real module
must still type-check through the resolved world with 0 errors).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STD = ROOT / "zen" / "std"
COMPILER = ROOT / "zen" / "compiler"

_IMPORT_RE = re.compile(r"^\s*\{(?P<names>[^}]*)\}\s*=\s*(?P<ns>std|compiler)\.(?P<mod>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)", re.S)
# A decl head is `name[*][<tparams>][*] =/:` — the optional `<…>` is a GENERIC head. The language
# accepts both public-generic spellings used in the tree (`Vec*<T>:` and older `new<T>* =`), so the
# splitter must keep both. Without this, generic stdlib exports are invisible to cross-module checks.
_DECL_HEAD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\*?)(<[^>]*>)?(\*?)\s*[=:]")
# A method-impl head `Type.impl(Trait, { … })` is ALSO a top-level decl, but it has no `name =/:` head so
# _DECL_HEAD_RE misses it. It must survive resolution: a cross-module CONSUMER of a trait method (e.g.
# std.collections.vec calling `a.acquire(…)` on an explicit Allocator, where acquire lives in std.mem.alloc's
# `Heap.impl(Allocator, …)`) needs the impl present so the checker's is_trait_method resolves the call —
# otherwise the method reads as undefined-name. The real loader (resolve.zen) always keeps impls; this
# mirrors that. Keyed per (Type, Trait) so two impls (many traits per type / many types per trait) never
# dedup each other away, while a re-import of the SAME module's impl still collapses to one.
_IMPL_HEAD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.impl\(\s*([A-Za-z_][A-Za-z0-9_]*)")


def _module_id(ns, mod):
    return ns + "/" + mod.replace(".", "/")


def _real_id(mod):
    """Normalize a real on-disk module name to `std/name` or `compiler/name`."""
    if "/" in mod:
        return mod
    for p in STD.rglob(mod + ".zen"):
        return "std/" + p.relative_to(STD).with_suffix("").as_posix()
    if (COMPILER / (mod + ".zen")).exists():
        return _module_id("compiler", mod)
    return mod


def module_relpath(mod):
    mid = _real_id(mod)
    if "/" in mid:
        ns, name = mid.split("/", 1)
        return "zen/" + ns + "/" + name + ".zen"
    return "zen/std/" + mid + ".zen"


def _module_path(mod):
    return ROOT / module_relpath(mod)


def _normalize_modules(modules):
    if modules is None:
        return all_modules()
    return [_real_id(m) for m in modules]


def all_modules():
    """Every real std/compiler module id, sorted — the universe the graph is built over."""
    return sorted(["std/" + p.relative_to(STD).with_suffix("").as_posix() for p in STD.rglob("*.zen")] +
                  [_module_id("compiler", p.stem) for p in COMPILER.glob("*.zen")])


def _src(mod):
    return _module_path(mod).read_text()


def import_edges(mod):
    """The `{ a, b } = std.X` / `compiler.X` imports of `mod`, as a list of
    (imported_name, source_module_id) pairs in source order. This is exactly std.internal.resolve.is_import_line's
    classification, parsed for its names + target module — the per-name edge the graph needs."""
    out = []
    lines = _src(mod).splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.lstrip().startswith("{ "):
            continue
        block = line
        while ("}" not in block or not re.search(r"}\s*=\s*(std|compiler)\.", block, re.S)) and i < len(lines):
            block += "\n" + lines[i]
            i += 1
        m = _IMPORT_RE.match(block)
        if not m:
            continue
        srcmod = _module_id(m.group("ns"), m.group("mod"))
        for nm in m.group("names").split(","):
            nm = nm.strip()
            if nm:
                out.append((nm, srcmod))
    return out


def module_graph(modules=None):
    """The whole-stdlib import graph. Returns (edges, name_origin):
      edges[mod]        = ordered, de-duplicated list of modules `mod` imports (the adjacency list).
      name_origin[mod]  = { imported_name : defining_module } for `mod` (per-name resolution).
    Built once over every std module so a new module joins the graph automatically."""
    modules = _normalize_modules(modules)
    modset = set(modules)
    edges = {}
    name_origin = {}
    for mod in modules:
        seen, adj, origin = set(), [], {}
        for nm, srcmod in import_edges(mod):
            origin[nm] = srcmod
            if srcmod in modset and srcmod not in seen:
                seen.add(srcmod)
                adj.append(srcmod)
        edges[mod] = adj
        name_origin[mod] = origin
    return edges, name_origin


def topo_order(modules=None):
    """Kahn topological order of the import graph: a module appears AFTER every module it imports
    (dependency-first — the order build_self would concat in). Returns (order, cycle_nodes); a
    self-loop / cycle leaves its members in cycle_nodes (the stdlib graph is a DAG, so it's empty).
    Edge direction: mod -> dep means `mod imports dep`; we want deps emitted first."""
    modules = _normalize_modules(modules)
    edges, _ = module_graph(modules)
    # indegree counted on the DEPENDED-UPON node would invert; instead build reverse adjacency:
    # dep -> [modules that import dep], and indegree[mod] = number of deps mod still waits on.
    indeg = {m: 0 for m in modules}
    revadj = {m: [] for m in modules}
    for mod in modules:
        for dep in edges[mod]:
            indeg[mod] += 1
            revadj[dep].append(mod)
    ready = sorted(m for m in modules if indeg[m] == 0)
    order = []
    while ready:
        m = ready.pop(0)
        order.append(m)
        for dependent in sorted(revadj[m]):
            indeg[dependent] -= 1
            if indeg[dependent] == 0:
                ready.append(dependent)
        ready.sort()
    cycle_nodes = [m for m in modules if m not in order]
    return order, cycle_nodes


def reachable(target, modules=None):
    """The transitive import closure of `target` (every module `target` reaches through imports,
    EXCLUDING `target` itself), in a deterministic dependency-first order. This is the set of modules
    whose definitions `target`'s imported names can resolve to — the world the resolver namespaces."""
    target = _real_id(target)
    edges, _ = module_graph(modules)
    if target not in edges:
        return []
    order, _cyc = topo_order(modules)
    pos = {m: i for i, m in enumerate(order)}
    seen, stack, out = set(), list(edges[target]), []
    while stack:
        m = stack.pop()
        if m in seen or m == target:
            continue
        seen.add(m)
        out.append(m)
        for dep in edges.get(m, []):
            if dep not in seen:
                stack.append(dep)
    # dependency-first: a module before everything that imports it (topo position).
    return sorted(out, key=lambda m: pos.get(m, 1 << 30))


# ── brace-aware top-level decl splitter ─────────────────────────────────────────────────────────
# Net brace delta of a physical line, counting ONLY real `{`/`}` — those inside a `//` comment, a
# '…' char literal, or a "…" string literal are skipped. The parse_* modules use `'{'`/`'}'` char
# literals and brace-mentioning comments heavily, so a naive count corrupts depth and swallows decls.
def _brace_delta(line):
    delta, i, n = 0, 0, len(line)
    while i < n:
        c = line[i]
        if c == "/" and i + 1 < n and line[i + 1] == "/":
            break                                   # rest of line is a comment
        if c == "'":                                # char literal: '\n', '{', '\'' …
            i += 1
            if i < n and line[i] == "\\":
                i += 1
            i += 1                                  # the char
            if i < n and line[i] == "'":
                i += 1
            continue
        if c == '"':                                # string literal
            i += 1
            while i < n and line[i] != '"':
                i += 2 if line[i] == "\\" else 1
            i += 1
            continue
        if c == "{":
            delta += 1
        elif c == "}":
            delta -= 1
        i += 1
    return delta


# A top-level decl starts at a column-0, non-comment, non-import line whose head matches `name[*] =/:`
# and runs to where `{`/`}` balance back to 0 (a braceless foreign-sig / single-line decl is one
# line). Returns [(name, exported, text)].
def split_decls(src):
    lines = src.splitlines()
    decls = []
    i, n = 0, len(lines)
    while i < n:
        l = lines[i]
        stripped = l.lstrip()
        if (not l) or l[0].isspace() or stripped.startswith("//") or \
           (stripped.startswith("{ ") and ("= std." in l or "= compiler." in l)):
            i += 1
            continue
        mi = _IMPL_HEAD_RE.match(l)
        if mi:
            # a `Type.impl(Trait, {…})` block: capture it brace-balanced, keyed uniquely so it is never
            # deduped against a real decl or another impl. Impls are always public (kept in the lib).
            name = f"{mi.group(1)}.impl({mi.group(2)})"
            start = i
            depth, seen_brace = 0, False
            while i < n:
                d = _brace_delta(lines[i])
                depth += d
                if d != 0:
                    seen_brace = True
                i += 1
                if seen_brace and depth <= 0:
                    break
                if not seen_brace:
                    break
            decls.append((name, True, "\n".join(lines[start:i])))
            continue
        m = _DECL_HEAD_RE.match(l)
        if not m:
            i += 1
            continue
        name = m.group(1)
        star = (m.group(2) == "*") or (m.group(4) == "*")   # public marker before or after <tparams>
        start = i
        depth, seen_brace = 0, False
        while i < n:
            d = _brace_delta(lines[i])
            depth += d
            if d != 0:
                seen_brace = True
            i += 1
            if seen_brace and depth <= 0:
                break
            if not seen_brace:           # a braceless decl (foreign sig / enum)
                # absorb indented `| Variant(…)` continuation lines: an enum may wrap, e.g.
                #   Expr*: Int(i64) | … | Arrow(ArrowData)
                #        | MakeEnum(MakeEnumData) | …
                # (was: only the head line survived, silently truncating the variant list)
                while i < n and lines[i][:1].isspace() and lines[i].lstrip().startswith("|"):
                    i += 1
                break
        decls.append((name, star, "\n".join(lines[start:i])))
    return decls


# ── in-memory variant: resolve over a synthetic module map (for the clash / transitive tests) ─────
# Same algorithm as the real-file path, but the module bodies come from a {name: source} dict instead
# of on-disk modules, so a test can construct a deliberate name CLASH or a re-export CHAIN and prove the
# resolver namespaces / transitively-resolves it. Mirrors module_graph/reachable/resolve exactly.
def _import_edges_src(src):
    out = []
    for line in src.splitlines():
        m = _IMPORT_RE.match(line)
        if m:
            for nm in m.group("names").split(","):
                nm = nm.strip()
                if nm:
                    out.append((nm, m.group("mod").replace(".", "/")))
    return out


def resolve_src(target, mods):
    """The namespaced resolved lib for `target` over an in-memory module map `mods` = {name: source}.
    Transitive closure of `target`'s imports, dependency-first, then per-NAME deduped to one decl —
    the same per-module namespace the real resolve() builds, but for synthetic modules."""
    edges = {m: [] for m in mods}
    for m, src in mods.items():
        seen = set()
        for _nm, srcmod in _import_edges_src(src):
            if srcmod in mods and srcmod not in seen and srcmod != m:
                seen.add(srcmod)
                edges[m].append(srcmod)
    # transitive closure of target (excluding target), dependency-first via a simple DFS post-order.
    order, visited = [], set()

    def visit(m):
        if m in visited:
            return
        visited.add(m)
        for dep in edges.get(m, []):
            visit(dep)
        order.append(m)
    for dep in edges.get(target, []):
        visit(dep)
    seen_names, chunks = set(), []
    for m in order:
        if m == target:
            continue
        for name, _e, text in split_decls(mods[m]):
            if name in seen_names:
                continue
            seen_names.add(name)
            chunks.append(text)
    return "\n".join(chunks)


def resolve(target, modules=None):
    """THE per-module NAMESPACED resolution for std module `target`. Builds the lib SOURCE the binary's
    module_header reduces to a cross-module signature header:

      * transitive closure of the modules `target` imports (dependency-first);
      * each module's top-level decls split out, then DEDUPLICATED across the closure so each NAME
        appears once — the per-module namespace (str.eq survives for a target importing eq from str;
        ast.eq never enters because ast is not on str-importer's closure).

    Returns the resolved lib text. Feeding it to check_linked checks `target`'s imported calls against
    the resolved definitions, with no clash false-positive and full transitive reach."""
    target = _real_id(target)
    libmods = reachable(target, modules)
    seen_names = set()
    chunks = []
    for mod in libmods:
        for name, _exported, text in split_decls(_src(mod)):
            if name in seen_names:
                continue        # already resolved by a nearer module on the closure — namespace dedup
            seen_names.add(name)
            chunks.append(text)
    return "\n".join(chunks)


# ── bootstrap/sources.txt graph order ─────────────────────────────────────────────────────────────
# --build-self still consumes an explicit manifest because the committed C seed must be buildable before
# any Zen compiler exists. The manifest is no longer a hidden/manual order: tests derive the expected
# source SET from bootstrap roots + runtime-provided std exclusions, then derive the expected ORDER by
# SCC-condensing the import graph and sorting deterministically inside each SCC.

_BOOTSTRAP_ROOTS = ["compiler/genc_emit", "compiler/parse", "compiler/check_validate", "std/internal/resolve", "compiler/diagnostic"]
_BOOTSTRAP_RUNTIME_MODULES = {"std/mem/raw", "std/text/str", "std/text/string"}


def _bootstrap_manifest_modules():
    mods = []
    for raw in (ROOT / "bootstrap" / "sources.txt").read_text().splitlines():
        rel = raw.strip()
        if not rel or rel.startswith("#"):
            continue
        p = Path(rel)
        if len(p.parts) >= 3 and p.parts[0] == "zen" and p.parts[1] in ("std", "compiler") and p.suffix == ".zen":
            mods.append(p.parts[1] + "/" + Path(*p.parts[2:]).with_suffix("").as_posix())
    return mods


def _bootstrap_source_set():
    edges, _ = module_graph()
    seen = set()

    def walk(mod):
        mod = _real_id(mod)
        if mod in seen or mod in _BOOTSTRAP_RUNTIME_MODULES:
            return
        seen.add(mod)
        for dep in edges.get(mod, []):
            walk(dep)

    for root in _BOOTSTRAP_ROOTS:
        walk(root)
    return seen


def _scc_graph_order(modules):
    modules = sorted(_real_id(m) for m in modules)
    edges, _ = module_graph(modules)
    index = 0
    stack = []
    on_stack = set()
    idx = {}
    low = {}
    comps = []

    def strongconnect(v):
        nonlocal index
        idx[v] = index
        low[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)
        for w in sorted(edges[v]):
            if w not in idx:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                comp.append(w)
                if w == v:
                    break
            comps.append(sorted(comp))

    for mod in modules:
        if mod not in idx:
            strongconnect(mod)

    comp_of = {m: i for i, comp in enumerate(comps) for m in comp}
    comp_edges = {i: set() for i in range(len(comps))}
    indeg = {i: 0 for i in range(len(comps))}
    for mod in modules:
        for dep in edges[mod]:
            a = comp_of[dep]
            b = comp_of[mod]
            if a != b and b not in comp_edges[a]:
                comp_edges[a].add(b)
                indeg[b] += 1

    ready = sorted((i for i, n in indeg.items() if n == 0), key=lambda i: comps[i][0])
    out = []
    while ready:
        comp = ready.pop(0)
        out.extend(comps[comp])
        for nxt in sorted(comp_edges[comp], key=lambda i: comps[i][0]):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                ready.append(nxt)
        ready.sort(key=lambda i: comps[i][0])
    return out


def _bootstrap_graph_order():
    return _scc_graph_order(_bootstrap_source_set())
