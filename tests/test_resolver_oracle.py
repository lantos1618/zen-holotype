"""FULL S1 MODULE RESOLVER oracle — import GRAPH + per-module NAMESPACES + transitive resolution.

tests/test_modules_oracle.py recovered cross-module type-checking with check_linked over a module's
DIRECT imports, flat-concatenated into one lib. That is correct for the real stdlib only because its
direct-import sets happen not to clash; it is NOT a real resolver, and a genuine cross-module name
CLASH would false-positive (a noted risk). This module builds + proves the real thing:

  GRAPH      module_graph()  parses every std/*.zen and compiler/*.zen import line into the name->defining-module map and
                             the module->imports adjacency (the DImport edges).
  ORDER      topo_order()    Kahn topological order of that graph; the parse_* cluster is a real cycle
                             and is reported as such (the rest is a DAG, dependency-first).
  NAMESPACE  resolve(t)      per-module world for t: the TRANSITIVE import closure, deduped per-NAME so
                             each top-level name resolves to ONE module — t's `eq` is str.eq, never
                             ast.eq, because only t's closure is present. Two modules' private helpers
                             that share a name (compiler/genjs + compiler/check_validate is_intrinsic) never collide.

Driven entirely by the committed `zenc` binary + cc (via _oracle.check_namespaced_count) — NO Python
compiler. The resolver itself (tests/_resolver.py) is pure harness text-processing; it touches no
compiler SOURCE, so there is zero bootstrap-fixpoint risk.

POSITIVE: every real std/compiler source type-checks against its REAL transitive imports through the namespaced
world with 0 errors (the whole stdlib is a well-typed inter-module unit — INCLUDING the parse cycle,
which the direct-import driver only handled by luck of its import sets). NEGATIVE / NAMESPACE: a real
cross-module name clash does NOT false-positive (and the naive flat-concat that DOES is shown for
contrast); a wrong cross-module call (arity / arg type), and a wrong call against a TRANSITIVELY
resolved import, are both caught.
"""
from pathlib import Path

import pytest

import _oracle
import _resolver

ROOT = Path(__file__).resolve().parent.parent
ALL_MODULES = _resolver.all_modules()


# ── the import GRAPH + topological ORDER ─────────────────────────────────────────────────────────
def test_graph_covers_every_module_and_resolves_known_edges():
    edges, origin = _resolver.module_graph()
    assert set(edges) == set(ALL_MODULES)
    # spot-check a few real edges: compiler/check_validate imports from compiler and std modules.
    assert set(edges["compiler/check_validate"]) >= {
        "compiler/genc", "compiler/check", "std/text/bytes", "std/mem/alloc", "std/text/str"
    }
    # and per-name origin: check_validate's `eq` comes from std/text/str (NOT std/internal/ast).
    assert origin["compiler/check_validate"]["eq"] == "std/text/str"


def test_topo_order_is_dependency_first_and_reports_the_parse_cycle():
    order, cycle = _resolver.topo_order()
    # the parse_* modules import each other -> a genuine cycle; everything else is a DAG. Kahn's
    # leftover set also holds any module DOWNSTREAM of the cycle: std/internal/resolve imports compiler/parse
    # (the loader's per-name dedup uses the parser's decl_span as its decl-boundary oracle), so it
    # can never reach in-degree 0 — it is unorderable, not itself cyclic.
    assert set(cycle) == {"compiler/parse", "compiler/parse_expr", "compiler/parse_stmt",
                          "compiler/parse_type", "std/internal/resolve"}
    assert set(order) | set(cycle) == set(ALL_MODULES)        # every module accounted for exactly once
    assert not (set(order) & set(cycle))
    edges, _ = _resolver.module_graph()
    pos = {m: i for i, m in enumerate(order)}
    # in the acyclic part every dependency precedes the module that imports it.
    for m in order:
        for dep in edges[m]:
            if dep in pos:
                assert pos[dep] < pos[m], f"{m} precedes its dependency {dep}"


def test_reachable_is_the_transitive_closure():
    # compiler/check_validate -> compiler/check reaches text + memory std modules transitively.
    # so `string`/allocator modules appear though check_validate imports neither directly.
    reach = set(_resolver.reachable("check_validate"))
    assert {"compiler/genc", "compiler/check", "std/text/str", "std/text/string",
            "std/text/bytes", "std/mem/alloc"} <= reach
    assert "std/mem/raw" not in reach
    assert "compiler/check_validate" not in reach               # a module is not in its own closure


# ── POSITIVE: the whole stdlib type-checks through the NAMESPACED resolver ────────────────────────
@pytest.mark.parametrize("module", ALL_MODULES)
def test_module_typechecks_through_namespaced_resolver(module):
    # The full S1 result: every std module composes with its REAL TRANSITIVE imports, resolved with
    # per-module namespacing (no clash), to 0 cross-module type errors. Covers the parse_* cycle that
    # the direct-import driver only passed by accident of its import sets, AND a module that CALLS a
    # cross-module generic (std.concurrent.cown -> std.mem.own's Own<T>/new<T>/own_get<T>): check_validate.call_errs
    # now skips the strict arg-TYPE check for an imported generic (its param types still carry the
    # unbound tparam `T`, which is uninferable here), exactly as a LOCAL generic call is monomorphized
    # away before this pass. Arity is still enforced, so a wrong-arity imported generic call is rejected.
    n = _oracle.check_namespaced_count(module)
    assert n == 0, f"{module}: {n} cross-module error(s) through the namespaced resolver " \
                   f"(reach={_resolver.reachable(module)})"


# ── NAMESPACE: a real cross-module name CLASH must NOT false-positive ─────────────────────────────
# Two modules each EXPORT `thing`, with different arities. The target imports `thing` from str_mod
# (2-arg) and calls it correctly; ast_mod's 1-arg `thing` must never enter the target's namespace.
_CLASH = {
    "str_mod": "thing* = (a: i32, b: i32) i32 { a + b }\n",
    "ast_mod": "thing* = (a: i32) i32 { a }\n",
}


def test_name_clash_resolves_to_the_imported_module_no_false_positive():
    app = dict(_CLASH, app="{ thing } = std.str_mod\nuse* = () i32 { thing(1, 2) }\n")
    assert _oracle.check_namespaced_count_src("app", app) == 0   # str_mod.thing(2 args) — correct


def test_name_clash_wrong_call_against_resolved_module_is_caught():
    # imported from str_mod (2-arg) but called with 1 -> rejected, proving the resolved sig is str_mod's.
    app = dict(_CLASH, app="{ thing } = std.str_mod\nuse* = () i32 { thing(1) }\n")
    assert _oracle.check_namespaced_count_src("app", app) > 0


def test_name_clash_resolves_the_other_way_too():
    # the SAME clash, importing from ast_mod (1-arg): a 1-arg call is accepted, a 2-arg call rejected —
    # the namespace truly follows the import, not a global first-definition.
    good = dict(_CLASH, app="{ thing } = std.ast_mod\nuse* = () i32 { thing(1) }\n")
    bad = dict(_CLASH, app="{ thing } = std.ast_mod\nuse* = () i32 { thing(1, 2) }\n")
    assert _oracle.check_namespaced_count_src("app", good) == 0
    assert _oracle.check_namespaced_count_src("app", bad) > 0


def test_naive_flat_concat_DOES_false_positive_on_the_clash():
    # CONTROL — the risk the resolver removes. Concatenating BOTH clashing modules into one flat lib
    # (the pre-resolver behaviour) puts two `thing` sigs in the header: dup_name + wrong resolution ->
    # the perfectly-valid 2-arg call false-positives. The namespaced resolver above returns 0 instead.
    lib_both = "thing = (a: i32, b: i32) i32 { a + b }\nthing = (a: i32) i32 { a }\n"
    target = "{ thing } = std.x\nuse* = () i32 { thing(1, 2) }\n"
    assert _oracle.check_linked_count_src(target, lib_both) > 0   # the false positive, proven
    # and the resolver's verdict on the same valid call is clean:
    app = dict(_CLASH, app="{ thing } = std.str_mod\nuse* = () i32 { thing(1, 2) }\n")
    assert _oracle.check_namespaced_count_src("app", app) == 0


# ── TRANSITIVE: an import re-export chain resolves through the graph ──────────────────────────────
# app imports `make` from std.mid; mid's `make` returns a Pt it imported from std.base. base is NOT a
# direct import of app — the resolver must pull it in transitively so Pt's definition is present.
_CHAIN = {
    "base": "Pt*: { x: i32, y: i32 }\n",
    "mid": "{ Pt } = std.base\nmake* = (v: i32) Pt { Pt(x: v, y: v) }\n",
}


def test_transitive_reexport_resolves():
    app = dict(_CHAIN, app="{ make } = std.mid\nuse* = () i32 { (make(3)).x }\n")
    # std.base is two hops away (app -> mid -> base) yet its Pt is in app's namespaced world.
    assert _oracle.check_namespaced_count_src("app", app) == 0


def test_transitive_call_is_arity_checked():
    # make takes 1 arg; called with 2 against the transitively-resolved sig -> rejected.
    app = dict(_CHAIN, app="{ make } = std.mid\nuse* = () i32 { (make(3, 4)).x }\n")
    assert _oracle.check_namespaced_count_src("app", app) > 0


# ── NEGATIVE: wrong cross-module calls through the resolver ───────────────────────────────────────
_LIB = {"lib": "f* = (a: i32, b: i32) i32 { a + b }\n"}


def test_wrong_arity_against_resolved_import_is_rejected():
    app = dict(_LIB, app="{ f } = std.lib\nbad* = () i32 { f(1, 2, 3) }\n")
    assert _oracle.check_namespaced_count_src("app", app) > 0


def test_wrong_arg_type_against_resolved_import_is_rejected():
    app = dict(_LIB, app='{ f } = std.lib\nbad* = () i32 { f("hi", "there") }\n')
    assert _oracle.check_namespaced_count_src("app", app) > 0


def test_correct_call_against_resolved_import_is_accepted():
    app = dict(_LIB, app="{ f } = std.lib\nok* = () i32 { f(1, 2) }\n")
    assert _oracle.check_namespaced_count_src("app", app) == 0


# ── the decl splitter the resolver relies on must cover every top-level decl ──────────────────────
@pytest.mark.parametrize("module", ALL_MODULES)
def test_splitter_covers_every_top_level_decl(module):
    # The namespace dedup is by top-level NAME; if the brace-aware splitter dropped a decl (e.g. a
    # parse_* fn whose body uses `'{'` char literals), a real signature would silently vanish from the
    # header and an imported call would go unchecked. Assert the split names match a column-0 head scan.
    import re
    src = _resolver._src(module)
    split_names = {n for n, _e, _t in _resolver.split_decls(src)}
    head_names = set()
    impl_depth = 0   # >0 ⇒ inside a `Type.impl(Trait, {…})` body; its methods are NOT top-level decls
    for l in src.splitlines():
        if impl_depth > 0:                                   # skip the impl body (its method heads, e.g.
            impl_depth += _resolver._brace_delta(l)          # runtime's column-0 `suspend = …`, aren't decls)
            continue
        if l and not l[0].isspace() and not l.lstrip().startswith("//") \
           and not (l.lstrip().startswith("{ ") and ("= std." in l or "= compiler." in l)):
            if _resolver._IMPL_HEAD_RE.match(l):             # an impl head: consume its brace-balanced body
                impl_depth = _resolver._brace_delta(l)
                continue
            m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\*?\s*[=:]", l)
            if m:
                head_names.add(m.group(1))
    assert head_names <= split_names, f"{module}: splitter dropped {head_names - split_names}"


def test_bootstrap_manifest_is_graph_derived_scc_order():
    # The C bootstrap still reads a manifest, but the order is now derived from the import graph:
    # roots + runtime-provided exclusions define the set, SCC topo defines the order.
    assert _resolver._bootstrap_manifest_modules() == _resolver._bootstrap_graph_order()


def test_resolver_oracle_has_no_python_frontend_dependency():
    # Same guarantee as the other oracles: the whole net runs on the BINARY (cc + the committed zenc),
    # never on a Python reference frontend. There is no zen.* compiler import anywhere in the loop.
    import sys
    assert "zen.main" not in sys.modules
    assert not any(m == "zen" or m.startswith("zen.") for m in sys.modules)
