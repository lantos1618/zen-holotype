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

  1. module_graph()  — parse every std/*.zen import line into the name->defining-module map and the
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

_IMPORT_RE = re.compile(r"^\s*\{(?P<names>[^}]*)\}\s*=\s*std\.(?P<mod>\w+)")
# A decl head is `name[<tparams>][*] =/:` — the optional `<…>` is a GENERIC head (`Own<T>:`,
# `new<T>* =`, `own_get<T>* =`); without it the generic stdlib exports (Own/new/clone/release/…)
# were invisible to split_decls, so a cross-module CONSUMER of them saw them as undefined.
_DECL_HEAD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(<[^>]*>)?(\*?)\s*[=:]")
# A method-impl head `Type.impl(Trait, { … })` is ALSO a top-level decl, but it has no `name =/:` head so
# _DECL_HEAD_RE misses it. It must survive resolution: a cross-module CONSUMER of a trait method (e.g.
# std.vec calling `a.acquire(…)` on an explicit Allocator, where acquire lives in std.alloc's
# `Malloc.impl(Allocator, …)`) needs the impl present so the checker's is_trait_method resolves the call —
# otherwise the method reads as undefined-name. The real loader (resolve.zen) always keeps impls; this
# mirrors that. Keyed per (Type, Trait) so two impls (many traits per type / many types per trait) never
# dedup each other away, while a re-import of the SAME module's impl still collapses to one.
_IMPL_HEAD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\.impl\(\s*([A-Za-z_][A-Za-z0-9_]*)")


def all_modules():
    """Every std module name (no .zen), sorted — the universe the graph is built over."""
    return sorted(p.stem for p in STD.glob("*.zen"))


def _src(mod):
    return (STD / (mod + ".zen")).read_text()


def import_edges(mod):
    """The `{ a, b } = std.X` imports of `mod`, as a list of (imported_name, source_module) pairs in
    source order. This is exactly std.resolve.is_import_line's classification, parsed for its names +
    target module — the per-name edge the graph needs (the flat imports_of only kept the module)."""
    out = []
    for line in _src(mod).splitlines():
        m = _IMPORT_RE.match(line)
        if not m:
            continue
        srcmod = m.group("mod")
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
    if modules is None:
        modules = all_modules()
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
    if modules is None:
        modules = all_modules()
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
           (stripped.startswith("{ ") and "= std." in l):
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
        name, star = m.group(1), m.group(3)      # group(2) is the optional <tparams>, group(3) the `*`
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
            if not seen_brace:           # a braceless single-line decl (foreign sig)
                break
        decls.append((name, star == "*", "\n".join(lines[start:i])))
    return decls


# ── in-memory variant: resolve over a synthetic module map (for the clash / transitive tests) ─────
# Same algorithm as the real-file path, but the module bodies come from a {name: source} dict instead
# of zen/std/*.zen, so a test can construct a deliberate name CLASH or a re-export CHAIN and prove the
# resolver namespaces / transitively-resolves it. Mirrors module_graph/reachable/resolve exactly.
def _import_edges_src(src):
    out = []
    for line in src.splitlines():
        m = _IMPORT_RE.match(line)
        if m:
            for nm in m.group("names").split(","):
                nm = nm.strip()
                if nm:
                    out.append((nm, m.group("mod")))
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


# ── STRETCH: wiring bootstrap/main.c --build-self to the resolver (PLAN, not yet done) ────────────
# --build-self today flat-concats a HARDCODED SOURCES list (genc, genc_mono, genc_emit, lex,
# parse_expr, parse_type, parse_stmt, parse, check) with imports stripped, then parse->resolve->emit,
# and the bootstrap FIXPOINT (tests/test_bootstrap.py) requires the result be BYTE-EXACT.
#
# Why a topo-order substitution can't be a drop-in (verified):
#   * genModule emits decls in SOURCE ORDER, so the flat concatenation order is load-bearing — change
#     it and the emitted C changes, breaking the fixpoint.
#   * topo_order(SOURCES) != the hardcoded order (it puts `check` before the parse_* modules), and the
#     parse_* SOURCES form a CYCLE (no canonical topological position). So "order = topo_order()" alone
#     reorders decls and diverges. (build_self_self_test below proves the concats differ.)
#
# The correct wiring (a real follow-up, kept out of this PR to protect the fixpoint):
#   1. Add a Zen entry `compiler_source*(a, roots: [str]) str` to std.resolve that, given the SOURCE
#      file BODIES (read by std.io), reproduces build_self_source: for each file in a fixed order,
#      strip imports (already in std.resolve.strip_imports) and concat with '\n' (concat_files). This
#      already exists in prototype form — strip_imports/concat_files are the primitives.
#   2. Have it DISCOVER the file set + order from the import GRAPH instead of a hardcoded list, but
#      pin the order to a STABLE topo that ties the parse_* cycle deterministically to the CURRENT
#      hardcoded order (e.g. SCC-condense the graph, topo-order the condensation, and within each SCC
#      keep the committed file order). That yields the same concatenation the hardcoded list does, so
#      the fixpoint stays byte-exact while the SOURCES list is now graph-derived, not hand-maintained.
#   3. Replace bootstrap/main.c's SOURCES[]/build_self_source with a call into that Zen entry (the C
#      side shrinks to: read roots, call compiler_source, emit). Then run `make regen` + the fixpoint
#      test; iterate the SCC tie-breaker until byte-exact.
# Until step 2's order-pinning is proven byte-exact, --build-self is LEFT AS-IS (per the task's
# fallback): the resolver + the complete namespaced cross-module CHECK below ship now; the build wiring
# is this plan.


def _build_self_order_differs():
    """Evidence for the plan above: a topo concat of the bootstrap SOURCES is NOT byte-identical to the
    hardcoded-order concat, so reordering --build-self by topo alone would break the fixpoint. Returns
    True (they differ) — asserted by test_resolver_oracle so the claim can't silently rot."""
    sources = ["genc", "genc_mono", "genc_emit", "lex",
               "parse_expr", "parse_type", "parse_stmt", "parse", "check"]

    def strip(m):
        return "\n".join(l for l in _src(m).splitlines()
                         if not (l.strip().startswith("{ ") and "= std." in l))
    hard = "\n".join(strip(m) for m in sources)
    order, cycle = topo_order(sources)
    topo = "\n".join(strip(m) for m in (order + cycle))
    return hard != topo
