"""holotype driver.

    python3 -m holotype build [dir]   # read build.zen, compile + link + run the exe
    python3 -m holotype check [dir]   # type-check report only, emit a C lib

Pipeline: parse -> insert into trie -> resolve refs -> infer/fits -> to_c.
Only well-typed functions are codegen'd.
"""
from __future__ import annotations
import sys, pathlib, subprocess
from .ast import (Struct, EnumDecl, Fn, Param, Prim, PrimT, NameT, PtrT, TVar,
                  Str, StructLit, Bin, Not, Field, Let, Call, MethodCall, EnumCtor, Match,
                  TraitDecl, Impl)
from .types import (Space, fits, infer, infer_block, subst, solve_call, match_type,
                    ret_type, TraitMethod, TypeErr)
from .lower import (c_struct, c_enum, c_proto, c_def, show, c_name, inst_name,
                    impl_cname, mangle)
from .parser import parse

BUILTIN = {"Option"}


# ───────────────────────── front end ────────────────────────────────────────
def load(root, skip=()):
    skip = set(skip) | {"build.zen"}        # build.zen is a build script, never a module
    files = {}
    for path in sorted(pathlib.Path(root).rglob("*.zen")):
        if path.name in skip:
            continue
        ns = ".".join(path.relative_to(root).with_suffix("").parts)
        files[ns] = parse(path.read_text(), ns)
    return files


def build_space(files):
    space = Space()
    space.impls = {}                      # (trait_path, type_path) -> {method: (Fn, scope)}
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Impl):       # impls have no name — registered in resolve()
                continue
            space.insert(f"{f.ns}.{d.name}", d)
    return space


def build_scopes(files):
    for f in files.values():
        sc = {}
        for imp in f.imports:
            for n in imp.names:
                sc[n] = f"{imp.module}.{n}"
        for d in f.decls:
            if not isinstance(d, Impl):
                sc[d.name] = f"{f.ns}.{d.name}"
        f.scope = sc


def trait_methods_scope(fn, base, space):
    """`base` scope plus, for every bound `T: Trait`, the trait's methods bound
    as TraitMethod entries — so a bounded body can call them by name."""
    sc = dict(base)
    for tp, trait_path in fn.bounds.items():
        trait = space.walk(trait_path).value
        for sig in trait.methods:
            sc[sig.name] = TraitMethod(tp, sig, trait_path)
    return sc


def resolve_type(t, scope, space, tparams=()):
    if isinstance(t, (PrimT, TVar)):
        return t
    if isinstance(t, PtrT):
        return PtrT(t.dir, resolve_type(t.pointee, scope, space, tparams))
    if isinstance(t, NameT):
        if t.path in tparams:                    # a bare name in scope as a type param
            return TVar(t.path)
        args = tuple(resolve_type(a, scope, space, tparams) for a in t.args)
        if t.path in BUILTIN:
            return NameT(t.path, args)
        qual = scope.get(t.path, t.path)
        space.walk(qual)
        return NameT(qual, args)
    raise TypeErr(f"unknown type node {t!r}")


def resolve(files, space):
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Struct):
                tp = set(d.tparams)
                for fld in d.fields:
                    fld.type = resolve_type(fld.type, f.scope, space, tp)
            elif isinstance(d, EnumDecl):
                tp = set(d.tparams)
                for v in d.variants:
                    if v.payload is not None:
                        v.payload = resolve_type(v.payload, f.scope, space, tp)
            elif isinstance(d, Fn):
                _resolve_fn(d, f.scope, space)
            elif isinstance(d, TraitDecl):
                for sig in d.methods:                       # Self is the implementor's type var
                    sig.params = tuple(resolve_type(p, f.scope, space, {"Self"}) for p in sig.params)
                    sig.ret = resolve_type(sig.ret, f.scope, space, {"Self"})
            elif isinstance(d, Impl):
                trait_path = f.scope.get(d.trait, d.trait)
                type_path = f.scope.get(d.type, d.type)
                space.walk(trait_path); space.walk(type_path)   # both must exist
                for m in d.methods:
                    _resolve_fn(m, f.scope, space)
                space.impls[(trait_path, type_path)] = {m.name: (m, f.scope) for m in d.methods}


def _resolve_fn(d, scope, space):
    tp = set(d.tparams)
    for p in d.params:
        p.type = resolve_type(p.type, scope, space, tp)
    if d.ret is not None:                                   # None -> inferred from the body later
        d.ret = resolve_type(d.ret, scope, space, tp)
    d.bounds = {k: (scope.get(v, v)) for k, v in d.bounds.items()}
    for trait_path in d.bounds.values():
        space.walk(trait_path)                              # the bound trait must exist


def _check_fn(qual, ns, d, scope, space, results, passing):
    if not d.body:
        return
    locals_ = {p.name: p.type for p in d.params}
    try:
        want = ret_type(qual, space) if qual in space.fn_scope else d.ret  # inferred or declared
        bt = infer_block(d.body, locals_, space, scope, want)
        if want is not None and not fits(bt, want):
            raise TypeErr("return type", bt, want)
        results.append((qual, True, "ok")); passing.add(qual)
    except TypeErr as ex:
        core = (f"{show(ex.given)}  ⊀  {show(ex.want)}"
                if ex.given is not None else str(ex))
        loc = f"{ns}:{ex.pos[0] + 1}:{ex.pos[1] + 1}: " if ex.pos else ""
        results.append((qual, False, loc + core))


def check(files, space):
    # maps for on-demand return-type inference: each top-level fn's defining
    # scope (trait-augmented if bounded), plus a guard against recursive inference.
    space.fn_scope = {f"{f.ns}.{d.name}": (trait_methods_scope(d, f.scope, space) if d.bounds else f.scope)
                      for f in files.values() for d in f.decls if isinstance(d, Fn)}
    space._inferring = set()

    results, passing = [], set()
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Fn):
                scope = trait_methods_scope(d, f.scope, space) if d.bounds else f.scope
                _check_fn(f"{f.ns}.{d.name}", f.ns, d, scope, space, results, passing)
            elif isinstance(d, Impl):
                _check_impl(d, f, space, results, passing)
    return results, passing


def _check_impl(d, f, space, results, passing):
    trait_path = f.scope.get(d.trait, d.trait)
    type_path = f.scope.get(d.type, d.type)
    trait = space.walk(trait_path).value
    sigs = {s.name: s for s in trait.methods}
    self_sub = {"Self": NameT(type_path, ())}
    for m in d.methods:
        tag = f"{d.trait} for {d.type}::{m.name}"
        # conformance: the method must match the trait signature with Self = the type
        sig = sigs.get(m.name)
        if sig is None:
            results.append((tag, False, f"{d.trait} has no method '{m.name}'")); continue
        want_params = [subst(p, self_sub) for p in sig.params]
        got_params = [p.type for p in m.params]
        if got_params != want_params or m.ret != subst(sig.ret, self_sub):
            results.append((tag, False, "signature does not match the trait")); continue
        _check_fn(tag, f.ns, m, f.scope, space, results, passing)
    missing = [name for name in sigs if name not in {m.name for m in d.methods}]
    if missing:
        results.append((f"{d.trait} for {d.type}", False,
                        f"missing method(s): {', '.join(missing)}"))


# ───────────────────────── monomorphization ─────────────────────────────────
class _Sink:
    """Three collectors the scanner feeds: generic-fn instances, trait-impl uses,
    and generic-struct instances."""
    __slots__ = ("fn", "impl", "struct")

    def __init__(self, fn, impl, struct):
        self.fn, self.impl, self.struct = fn, impl, struct


def _scan_expr(e, locals_, space, scope, sink):
    """Walk an expression, feeding every monomorphization site to `sink`."""
    if isinstance(e, Bin):
        _scan_expr(e.l, locals_, space, scope, sink)
        _scan_expr(e.r, locals_, space, scope, sink)
    elif isinstance(e, Not):
        _scan_expr(e.operand, locals_, space, scope, sink)
    elif isinstance(e, Field):
        _scan_expr(e.obj, locals_, space, scope, sink)
    elif isinstance(e, StructLit):
        for _, v in e.fields:
            _scan_expr(v, locals_, space, scope, sink)
        st = infer(e, locals_, space, scope)             # record AFTER children (inner-first)
        if space.walk(st.path).value.tparams:
            sink.struct(st.path, st.args)
    elif isinstance(e, EnumCtor):
        for a in e.args:
            _scan_expr(a, locals_, space, scope, sink)
    elif isinstance(e, Match):
        _scan_expr(e.subject, locals_, space, scope, sink)
        st = infer(e.subject, locals_, space, scope)
        if isinstance(st, PrimT):                         # literal match: arms bind nothing
            for arm in e.arms:
                _scan_expr(arm.body, locals_, space, scope, sink)
            return
        decl = space.walk(st.path).value
        sub = dict(zip(decl.tparams, st.args)) if decl.tparams else {}
        variants = {v.name: v for v in decl.variants}
        for arm in e.arms:
            al = locals_
            if arm.variant is not None and arm.binding is not None:
                al = {**locals_, arm.binding: subst(variants[arm.variant].payload, sub)}
            _scan_expr(arm.body, al, space, scope, sink)
    elif isinstance(e, Call):
        for a in e.args:
            _scan_expr(a, locals_, space, scope, sink)
        if e.callee == "addr":
            return
        target = scope.get(e.callee)
        if isinstance(target, TraitMethod):              # resolve concrete Self -> impl used
            s = {}
            for p, a in zip(target.sig.params, e.args):
                match_type(p, infer(a, locals_, space, scope), s)
            if isinstance(s.get("Self"), NameT):
                sink.impl(target.trait, s["Self"].path)
            return
        callee = space.walk(target).value
        if isinstance(callee, Fn) and callee.tparams:
            s = solve_call(callee, [infer(a, locals_, space, scope) for a in e.args])
            sink.fn(target, tuple(s[n] for n in callee.tparams))


def _scan_block(stmts, locals_, space, scope, sink):
    locals_ = dict(locals_)
    for s in stmts:
        if isinstance(s, Let):
            _scan_expr(s.value, locals_, space, scope, sink)
            locals_[s.name] = infer(s.value, locals_, space, scope)
        else:
            _scan_expr(s, locals_, space, scope, sink)


def specialize(fn, s):
    """A concrete copy of a generic fn with its type-args substituted in (bounds
    kept so its body's trait-method calls still resolve)."""
    return Fn(fn.name, [Param(p.name, subst(p.type, s)) for p in fn.params],
              subst(fn.ret, s), fn.body, fn.pub, (), fn.bounds)


def collect_instances(files, passing, space):
    """Reachable from the non-generic passing functions, transitively: every
    concrete generic-fn instance, trait impl, and generic-struct instance used.
    -> (fn_insts, impls_used, struct_insts)"""
    decl_scope = {f"{f.ns}.{d.name}": f.scope
                  for f in files.values() for d in f.decls if not isinstance(d, Impl)}
    insts, impls_used, struct_insts, work = {}, set(), {}, []

    def add(qual, targs):
        if (qual, targs) in insts:
            return
        fn = space.walk(qual).value
        sc = trait_methods_scope(fn, decl_scope[qual], space)
        spec = specialize(fn, dict(zip(fn.tparams, targs)))
        insts[(qual, targs)] = (spec, sc)
        work.append((spec, sc))

    def add_impl(trait_path, type_path):
        if (trait_path, type_path) in impls_used:
            return
        impls_used.add((trait_path, type_path))
        for mfn, msc in space.impls[(trait_path, type_path)].values():
            work.append((mfn, msc))

    def add_struct(qual, targs):              # inner-first insertion → emit order is valid
        struct_insts.setdefault((qual, targs), dict(zip(space.walk(qual).value.tparams, targs)))

    sink = _Sink(add, add_impl, add_struct)
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Fn) and not d.tparams and f"{f.ns}.{d.name}" in passing:
                sc = trait_methods_scope(d, f.scope, space) if d.bounds else f.scope
                _scan_block(d.body, {p.name: p.type for p in d.params}, space, sc, sink)
    while work:
        fn, sc = work.pop()
        _scan_block(fn.body, {p.name: p.type for p in fn.params}, space, sc, sink)
    return insts, impls_used, struct_insts


def emit_c(files, passing, space, extra=""):
    # Integrity: codegen lowers struct/enum/fn directly and trait impls on demand.
    # A trait declaration emits nothing; anything else fails loudly.
    for f in files.values():
        for d in f.decls:
            if not isinstance(d, (Struct, EnumDecl, Fn, TraitDecl, Impl)):
                raise NotImplementedError(
                    f"cannot lower {type(d).__name__} '{getattr(d, 'name', '?')}' to C yet "
                    f"(codegen supports struct + enum + fn + trait/impl)")
    insts, impls_used, struct_insts = collect_instances(files, passing, space)
    impl_fns = [(impl_cname(tp, ty, m), mfn, msc)         # the trait methods actually used
                for (tp, ty) in impls_used
                for m, (mfn, msc) in space.impls[(tp, ty)].items()]

    lines = ["#include <stdint.h>", "#include <stdbool.h>", ""]
    for f in files.values():                             # types (generic templates emit nothing)
        for d in f.decls:
            if isinstance(d, Struct) and not d.tparams:
                lines.append(c_struct(f"{f.ns}.{d.name}", d))
            elif isinstance(d, EnumDecl) and not d.tparams:
                lines.append(c_enum(f"{f.ns}.{d.name}", d))
    for (qual, targs), sub in struct_insts.items():      # monomorphized generic structs
        lines.append(c_struct(qual, space.walk(qual).value, sub, mangle(NameT(qual, targs))))
    lines.append("")
    for f in files.values():                             # prototypes: concrete fns…
        for d in f.decls:
            if isinstance(d, Fn) and not d.tparams and f"{f.ns}.{d.name}" in passing:
                lines.append(c_proto(f"{f.ns}.{d.name}", d))
    for (qual, targs), (spec, _) in insts.items():       # …monomorphized instances…
        lines.append(c_proto(qual, spec, inst_name(qual, targs)))
    for cn, mfn, _ in impl_fns:                          # …and trait-impl methods
        lines.append(c_proto(cn, mfn, cn))
    lines.append("")
    for f in files.values():                             # definitions
        for d in f.decls:
            if isinstance(d, Fn) and not d.tparams and f"{f.ns}.{d.name}" in passing:
                lines.append(c_def(f"{f.ns}.{d.name}", d, space, f.scope))
    for (qual, targs), (spec, sc) in insts.items():
        lines.append(c_def(qual, spec, space, sc, inst_name(qual, targs)))
    for cn, mfn, msc in impl_fns:
        lines.append(c_def(cn, mfn, space, msc, cn))
    return "\n".join(lines) + "\n" + extra


# ───────────────────────── build.zen interpreter ────────────────────────────
def sval(e):
    return e.s if isinstance(e, Str) else None


def interpret_build(bf):
    """Statically read the build() graph into a config dict (like reading build.zig).

    The CST chains the trailing `.Ok(...)` onto the last `b.add(...)`, so we walk
    method-call receivers to find every `b.add(Component {...})`.
    """
    cfg = {"name": "a.out", "main": "main.zen", "out_dir": ".", "tests": []}
    fn = next((d for d in bf.decls if isinstance(d, Fn) and d.name == "build"), None)
    if fn is None:
        raise SystemExit("build.zen: no build() function")

    def handle_add(arg):
        if not isinstance(arg, StructLit):
            return
        f = {n: v for n, v in arg.fields}
        if arg.type == "Executable":
            cfg["name"] = sval(f.get("name")) or cfg["name"]
            cfg["main"] = sval(f.get("main")) or cfg["main"]
            cfg["out_dir"] = sval(f.get("out_dir")) or cfg["out_dir"]
        elif arg.type == "Test":
            if (r := sval(f.get("root"))):
                cfg["tests"].append(r)

    def visit(node):
        if isinstance(node, MethodCall):
            if node.method == "add" and node.args:
                handle_add(node.args[0])
            visit(node.recv)
            for a in node.args:
                visit(a)
        elif isinstance(node, EnumCtor):
            for a in node.args:
                visit(a)

    for stmt in fn.body:
        visit(stmt)
    return cfg


def is_test_fn(d) -> bool:
    """A test is a no-arg function returning bool — true means the test passed."""
    return (isinstance(d, Fn) and not d.params
            and isinstance(d.ret, PrimT) and d.ret.prim is Prim.BOOL)


def run_test_root(root, test_rel):
    """Compile the test root together with the project modules and run each
    bool-returning no-arg test, reporting PASS/FAIL from its return value."""
    test_ns = pathlib.Path(test_rel).with_suffix("").as_posix().replace("/", ".")
    files = load(root)                       # includes the test root (skips only build.zen)
    space = build_space(files)
    build_scopes(files); resolve(files, space)
    _, passing = check(files, space)

    tf = files.get(test_ns)
    tests = [d for d in (tf.decls if tf else []) if is_test_fn(d)]
    runnable = [d for d in tests if f"{test_ns}.{d.name}" in passing]

    calls = "\n".join(
        f'    printf("   %s  {test_ns}.{d.name}\\n", '
        f'{c_name(f"{test_ns}.{d.name}")}() ? "PASS \\u2713" : "FAIL \\u2717");'
        for d in runnable)
    harness = f'\n#include <stdio.h>\nint main(void) {{\n{calls}\n    return 0;\n}}\n'

    out_dir = pathlib.Path(root) / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath, bpath = out_dir / f"{test_ns}_test.c", out_dir / f"{test_ns}_test"
    cpath.write_text(emit_c(files, passing, space, harness))
    subprocess.run(["cc", "-Wall", "-Wextra", str(cpath), "-o", str(bpath)], check=True)
    print(f"\n── tests: {test_rel} ──")
    skipped = [d.name for d in tests if d not in runnable]
    print(subprocess.run([str(bpath)], capture_output=True, text=True).stdout, end="")
    for name in skipped:
        print(f"   SKIP    {test_ns}.{name}  (did not type-check)")


# ───────────────────────── commands ─────────────────────────────────────────
def cmd_check(root):
    files = load(root)
    space = build_space(files)
    build_scopes(files); resolve(files, space)
    results, passing = check(files, space)
    print(f"── check {root} ──")
    for qual, ok, why in results:
        print(f"   {'PASS ✓' if ok else 'FAIL ✗'}  {qual:<14} {'' if ok else why}")
    pathlib.Path("out.c").write_text(emit_c(files, passing, space))
    print("   -> wrote out.c")


def cmd_build(root):
    bf = parse((pathlib.Path(root) / "build.zen").read_text(), "build")
    cfg = interpret_build(bf)
    print(f"── build.zen graph ──\n   Executable {cfg['name']}  (main={cfg['main']}, out={cfg['out_dir']})")
    for t in cfg["tests"]:
        print(f"   Test {t}  (declared)")

    files = load(root, skip={"build.zen"} | set(cfg["tests"]))
    space = build_space(files)
    build_scopes(files); resolve(files, space)
    results, passing = check(files, space)
    print("\n── type checks ──")
    for qual, ok, why in results:
        print(f"   {'PASS ✓' if ok else 'FAIL ✗'}  {qual:<14} {'' if ok else why}")

    entry_ns = pathlib.Path(cfg["main"]).with_suffix("").as_posix().replace("/", ".")
    entry = f"{entry_ns}.main"
    if entry not in passing:
        raise SystemExit(f"\nentry '{entry}' did not type-check — nothing to run")

    harness = (f'\n#include <stdio.h>\nint main(void) {{\n'
               f'    printf("{cfg["name"]} -> %d\\n", {c_name(entry)}());\n'
               f'    return 0;\n}}\n')
    out_dir = pathlib.Path(root) / cfg["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath, bpath = out_dir / f"{cfg['name']}.c", out_dir / cfg["name"]
    cpath.write_text(emit_c(files, passing, space, harness))

    print(f"\n── compiling {cpath} ──")
    subprocess.run(["cc", "-Wall", "-Wextra", str(cpath), "-o", str(bpath)], check=True)
    print(f"── running {bpath} ──")
    print(subprocess.run([str(bpath)], capture_output=True, text=True).stdout, end="")

    for t in cfg["tests"]:
        run_test_root(root, t)


def cli(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "build"
    arg = argv[1] if len(argv) > 1 else "examples"
    (cmd_build if cmd == "build" else cmd_check)(arg)


if __name__ == "__main__":
    cli()
