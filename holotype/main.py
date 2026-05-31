"""holotype driver.

    python3 -m holotype build [dir]   # read build.zen, compile + link + run the exe
    python3 -m holotype check [dir]   # type-check report only, emit a C lib

Pipeline: parse -> insert into trie -> resolve refs -> infer/fits -> to_c.
Only well-typed functions are codegen'd.
"""
from __future__ import annotations
import sys, pathlib, subprocess
from .ast import (Struct, EnumDecl, Fn, Param, Prim, PrimT, NameT, PtrT, TVar,
                  Str, StructLit, Bin, Field, Let, Call, MethodCall, EnumCtor, Match)
from .types import Space, fits, infer, infer_block, subst, solve_call, TypeErr
from .lower import c_struct, c_enum, c_proto, c_def, show, c_name, inst_name
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
    for f in files.values():
        for d in f.decls:
            space.insert(f"{f.ns}.{d.name}", d)
    return space


def build_scopes(files):
    for f in files.values():
        sc = {}
        for imp in f.imports:
            for n in imp.names:
                sc[n] = f"{imp.module}.{n}"
        for d in f.decls:
            sc[d.name] = f"{f.ns}.{d.name}"
        f.scope = sc


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
                tp = set(d.tparams)
                for p in d.params:
                    p.type = resolve_type(p.type, f.scope, space, tp)
                d.ret = resolve_type(d.ret, f.scope, space, tp)


def check(files, space):
    results, passing = [], set()
    for f in files.values():
        for d in f.decls:
            if not isinstance(d, Fn):
                continue
            qual = f"{f.ns}.{d.name}"
            if not d.body:
                continue
            locals_ = {p.name: p.type for p in d.params}
            try:
                bt = infer_block(d.body, locals_, space, f.scope, d.ret)
                if not fits(bt, d.ret):
                    raise TypeErr("return type", bt, d.ret)
                results.append((qual, True, "ok")); passing.add(qual)
            except TypeErr as ex:
                core = (f"{show(ex.given)}  ⊀  {show(ex.want)}"
                        if ex.given is not None else str(ex))
                loc = f"{f.ns}:{ex.pos[0] + 1}:{ex.pos[1] + 1}: " if ex.pos else ""
                results.append((qual, False, loc + core))
    return results, passing


# ───────────────────────── monomorphization ─────────────────────────────────
def _scan_expr(e, locals_, space, scope, add):
    """Walk an expression; record every generic-call instance (callee, type-args)."""
    if isinstance(e, Bin):
        _scan_expr(e.l, locals_, space, scope, add)
        _scan_expr(e.r, locals_, space, scope, add)
    elif isinstance(e, Field):
        _scan_expr(e.obj, locals_, space, scope, add)
    elif isinstance(e, StructLit):
        for _, v in e.fields:
            _scan_expr(v, locals_, space, scope, add)
    elif isinstance(e, EnumCtor):
        for a in e.args:
            _scan_expr(a, locals_, space, scope, add)
    elif isinstance(e, Match):
        _scan_expr(e.subject, locals_, space, scope, add)
        st = infer(e.subject, locals_, space, scope)
        decl = space.walk(st.path).value
        sub = dict(zip(decl.tparams, st.args)) if decl.tparams else {}
        variants = {v.name: v for v in decl.variants}
        for arm in e.arms:
            al = locals_
            if arm.variant is not None and arm.binding is not None:
                al = {**locals_, arm.binding: subst(variants[arm.variant].payload, sub)}
            _scan_expr(arm.body, al, space, scope, add)
    elif isinstance(e, Call):
        for a in e.args:
            _scan_expr(a, locals_, space, scope, add)
        if e.callee == "addr":
            return
        callee = space.walk(scope[e.callee]).value
        if isinstance(callee, Fn) and callee.tparams:
            s = solve_call(callee, [infer(a, locals_, space, scope) for a in e.args])
            add(scope[e.callee], tuple(s[n] for n in callee.tparams))


def _scan_block(stmts, locals_, space, scope, add):
    locals_ = dict(locals_)
    for s in stmts:
        if isinstance(s, Let):
            _scan_expr(s.value, locals_, space, scope, add)
            locals_[s.name] = infer(s.value, locals_, space, scope)
        else:
            _scan_expr(s, locals_, space, scope, add)


def specialize(fn, s):
    """A concrete copy of a generic fn with its type-args substituted in."""
    return Fn(fn.name, [Param(p.name, subst(p.type, s)) for p in fn.params],
              subst(fn.ret, s), fn.body, fn.pub, ())


def collect_instances(files, passing, space):
    """Every concrete (qual, type-args) of a generic fn reachable from the
    non-generic passing functions, transitively. -> {(qual, targs): (spec, scope)}"""
    decl_scope = {f"{f.ns}.{d.name}": f.scope for f in files.values() for d in f.decls}
    insts, work = {}, []

    def add(qual, targs):
        if (qual, targs) in insts:
            return
        fn = space.walk(qual).value
        spec = specialize(fn, dict(zip(fn.tparams, targs)))
        insts[(qual, targs)] = (spec, decl_scope[qual])
        work.append((spec, decl_scope[qual]))

    for f in files.values():
        for d in f.decls:
            if isinstance(d, Fn) and not d.tparams and f"{f.ns}.{d.name}" in passing:
                _scan_block(d.body, {p.name: p.type for p in d.params}, space, f.scope, add)
    while work:
        spec, sc = work.pop()
        _scan_block(spec.body, {p.name: p.type for p in spec.params}, space, sc, add)
    return insts


def emit_c(files, passing, space, extra=""):
    # Integrity: codegen lowers Struct, EnumDecl, Fn. Anything else fails loudly
    # rather than silently dropping it from the output.
    for f in files.values():
        for d in f.decls:
            if not isinstance(d, (Struct, EnumDecl, Fn)):
                raise NotImplementedError(
                    f"cannot lower {type(d).__name__} '{f.ns}.{d.name}' to C yet "
                    f"(codegen supports struct + enum + fn)")
    insts = collect_instances(files, passing, space)

    lines = ["#include <stdint.h>", "#include <stdbool.h>", ""]
    for f in files.values():                             # types (generic templates emit nothing)
        for d in f.decls:
            if isinstance(d, Struct) and not d.tparams:
                lines.append(c_struct(f"{f.ns}.{d.name}", d))
            elif isinstance(d, EnumDecl) and not d.tparams:
                lines.append(c_enum(f"{f.ns}.{d.name}", d))
    lines.append("")
    for f in files.values():                             # prototypes: concrete fns…
        for d in f.decls:
            if isinstance(d, Fn) and not d.tparams and f"{f.ns}.{d.name}" in passing:
                lines.append(c_proto(f"{f.ns}.{d.name}", d))
    for (qual, targs), (spec, _) in insts.items():       # …and each monomorphized instance
        lines.append(c_proto(qual, spec, inst_name(qual, targs)))
    lines.append("")
    for f in files.values():                             # definitions
        for d in f.decls:
            if isinstance(d, Fn) and not d.tparams and f"{f.ns}.{d.name}" in passing:
                lines.append(c_def(f"{f.ns}.{d.name}", d, space, f.scope))
    for (qual, targs), (spec, sc) in insts.items():
        lines.append(c_def(qual, spec, space, sc, inst_name(qual, targs)))
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
