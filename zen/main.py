"""zen driver.

    python3 -m zen build [dir]        # read build.zen, compile + link + run the exe
    python3 -m zen check [dir]        # type-check, report only (--emit writes out.c)
    python3 -m zen dump  [dir]        # canonical AST dump + hash of each .zen module

Pipeline: parse -> insert into trie -> resolve refs -> infer/fits -> to_c.
Only well-typed functions are codegen'd. The phases live in their own modules —
resolve.py (resolution + desugar), emit.py (monomorphization + C), build.py (the
build.zen system); this file is the loader, the type-check pass, and the CLI, and
re-exports the public surface so `from zen.main import …` keeps working.
"""
from __future__ import annotations
import sys, pathlib, subprocess
from .ast import Fn, Impl, Emit, NameT, PrimT, Prim, TVar
from .types import (fits, infer_block, ret_type, show, scope_with_bounds, subst,
                    TypeErr, Private, Unresolved, Located)        # Private/Unresolved re-exported
from .lower import c_name
from .parser import parse
from .astdump import dump, ast_hash
from .comptime import fold_comptime, evaluate, reify_decl
from .resolve import build_namespace, build_scopes, resolve, _resolve_fn, is_prelude_ns
from .emit import emit_c
from .build import interpret_build, load_uses, compile_if_changed, is_test_fn, _TARGETS

# ───────────────────────── front end (loading) ──────────────────────────────
_PRELUDE_DIR = pathlib.Path(__file__).parent / "prelude"
_STD_DIR = pathlib.Path(__file__).parent / "std"


def load_prelude():
    """The compiler's bundled Zen prelude (the self-hosted Ast model + derives),
    always available under the `prelude.*` namespace, importable from any file."""
    return {f"prelude.{p.stem}": parse(p.read_text(), f"prelude.{p.stem}")
            for p in sorted(_PRELUDE_DIR.glob("*.zen"))}


def load_std():
    """The bundled standard library — ordinary runtime Zen under `std.*`, importable
    from any file. Unlike the prelude (comptime-only, never lowered), std IS checked
    and lowered like user code. But its helpers are templates/generics, so nothing is
    emitted unless a program imports AND uses them — the stdlib is zero-cost ambient."""
    if not _STD_DIR.exists():
        return {}
    # `@self-hosted-only` modules use features only the self-hosted frontend parses (e.g. generic
    # struct literals); the Python reference can't load them, so skip them here. They are compiled
    # by the self-hosted toolchain only (and self-tested via self-contained programs).
    return {f"std.{p.stem}": parse(src, f"std.{p.stem}")
            for p in sorted(_STD_DIR.glob("*.zen"))
            for src in [p.read_text()] if "@self-hosted-only" not in src}


def load(root, skip=()):
    skip = set(skip) | {"build.zen"}        # build.zen is a build script, never a module
    files = dict(load_prelude())
    files.update(load_std())
    for path in sorted(pathlib.Path(root).rglob("*.zen")):
        if path.name in skip:
            continue
        ns = ".".join(path.relative_to(root).with_suffix("").parts)
        files[ns] = parse(path.read_text(), ns)
    return files


# ───────────────────────── @emit splice pass + type check ───────────────────
def _graft_impl(d, f, namespace):
    """Register a generated trait impl exactly like resolve() does for a written
    one: resolve its methods and record it in the impls registry."""
    trait_path = f.scope.get(d.trait, d.trait)
    type_path = f.scope.get(d.type, d.type)
    namespace.walk(trait_path); namespace.walk(type_path)        # both must exist
    for m in d.methods:
        _resolve_fn(m, f.scope, namespace)
    namespace.impls[(trait_path, type_path)] = {m.name: (m, f.scope) for m in d.methods}


def run_emits(files, namespace):
    """The splice pass: evaluate each `emit` generator at comptime, reify the
    Zen `Ast` value it returns into a real declaration (a free fn or a trait
    impl), and graft it into the module — so check + lower meet it as ordinary
    code. Runs after resolve, before check (VISION step 4: prelude `Ast → Ast`)."""
    for f in files.values():
        grafted = []
        for d in f.decls:
            if not isinstance(d, Emit):
                continue
            out = evaluate(d.value, namespace, f.scope)
            for g in (out if isinstance(out, list) else [out]):
                g = reify_decl(g)                        # Zen Ast value -> host Fn / Impl
                if isinstance(g, Impl):
                    _graft_impl(g, f, namespace)
                else:
                    f.scope[g.name] = f"{f.ns}.{g.name}"     # same dict the siblings see
                    namespace.insert(f"{f.ns}.{g.name}", g)
                    _resolve_fn(g, f.scope, namespace)
                grafted.append(g)
        if grafted:
            f.decls = [d for d in f.decls if not isinstance(d, Emit)] + grafted


def _check_fn(qual, ns, d, namespace, results, passing):
    if d.body is None:               # a foreign binding (bodyless) — nothing to check or emit.
        return                       # NB: `not d.body` would also skip an EMPTY body [] (e.g. a
                                     # `() void {}`), dropping it from `passing` -> never emitted -> link error.
    locals_ = {p.name: p.type for p in d.params}
    try:
        want = d.ret if d.ret is not None else ret_type(qual, namespace)   # declared or inferred
        # tparams are TVars in the body scope, so `sizeof(T)` (a value-position type name) resolves
        bscope = {**scope_with_bounds(d.scope, d.bounds), **{tp: TVar(tp) for tp in d.tparams}}
        bt = infer_block(d.body, locals_, namespace, bscope, want)
        void = isinstance(want, PrimT) and want.prim is Prim.VOID
        if want is not None and not void and not fits(bt, want):        # void discards the body value
            raise TypeErr("return type", bt, want)
        results.append((qual, True, "ok")); passing.add(qual)
    except TypeErr as ex:
        core = (f"{show(ex.given)}  ⊀  {show(ex.want)}"
                if ex.given is not None else str(ex))
        loc = f"{ns}:{ex.pos[0] + 1}:{ex.pos[1] + 1}: " if ex.pos else ""
        results.append((qual, False, Located(loc + core, ns, ex.pos)))


def check(files, namespace):
    results, passing = [], set()
    for f in files.values():
        if is_prelude_ns(f.ns):                            # the prelude runs at comptime; never checked
            continue
        for d in f.decls:
            if isinstance(d, Fn):
                _check_fn(f"{f.ns}.{d.name}", f.ns, d, namespace, results, passing)
            elif isinstance(d, Impl):
                _check_impl(d, f, namespace, results, passing)
    return results, passing


def _check_impl(d, f, namespace, results, passing):
    trait_path = f.scope.get(d.trait, d.trait)
    type_path = f.scope.get(d.type, d.type)
    trait = namespace.walk(trait_path).value
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
        _check_fn(tag, f.ns, m, namespace, results, passing)
        if tag in passing:                          # record the codegen key in `passing` too
            passing.add((trait_path, type_path, m.name))
    missing = [name for name in sigs if name not in {m.name for m in d.methods}]
    if missing:
        results.append((f"{d.trait} for {d.type}", False,
                        f"missing method(s): {', '.join(missing)}"))


# ───────────────────────── commands ─────────────────────────────────────────
def run_test_root(root, test_rel, cc_extra=()):
    """Compile the test root together with the project modules and run each
    bool-returning no-arg test, reporting PASS/FAIL from its return value.
    `cc_extra` are extra cc args (the Executable's cflags + `-l` links).
    Returns the number of FAILED tests (a false return, a crash, or a test that
    didn't type-check) so the caller can make the build fail honestly."""
    test_ns = pathlib.Path(test_rel).with_suffix("").as_posix().replace("/", ".")
    files = load(root)                       # includes the test root (skips only build.zen)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace); fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)

    tf = files.get(test_ns)
    tests = [d for d in (tf.decls if tf else []) if is_test_fn(d)]
    runnable = [d for d in tests if f"{test_ns}.{d.name}" in passing]

    calls = "\n".join(
        f'    {{ int ok = {c_name(f"{test_ns}.{d.name}")}(); '
        f'printf("   %s  {test_ns}.{d.name}\\n", ok ? "PASS \\u2713" : "FAIL \\u2717"); '
        f'if (!ok) fails++; }}'
        for d in runnable)
    harness = (f'\n#include <stdio.h>\nint main(void) {{\n    int fails = 0;\n'
               f'{calls}\n    return fails;\n}}\n')         # exit code = number of failed tests

    out_dir = pathlib.Path(root) / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath, bpath = out_dir / f"{test_ns}_test.c", out_dir / f"{test_ns}_test"
    compile_if_changed(cpath, bpath, emit_c(files, passing, namespace, harness), cc_extra)
    print(f"\n── tests: {test_rel} ──")
    skipped = [d.name for d in tests if d not in runnable]
    res = subprocess.run([str(bpath)], capture_output=True, text=True, timeout=120)
    print(res.stdout, end="")
    for name in skipped:
        print(f"   SKIP    {test_ns}.{name}  (did not type-check)")
    rc = res.returncode                                    # >0: that many FAILs; <0: crashed
    return (rc if rc > 0 else (0 if rc == 0 else 1)) + len(skipped)


def caret(root, why):
    """The offending source line + a caret under the column, built straight from a
    Located diagnostic's structured `(ns, pos)` — no message re-parsing. '' if the
    location is absent or the source can't be read."""
    ns, pos = getattr(why, "ns", None), getattr(why, "pos", None)
    if not ns or not pos:
        return ""
    try:
        line = (pathlib.Path(root) / (ns.replace(".", "/") + ".zen")).read_text().splitlines()[pos[0]]
    except (OSError, IndexError):
        return ""
    return f"\n        {line}\n        {' ' * pos[1]}^"


def report(results, root):
    """Print the PASS/FAIL table; under each failure, show its source line + caret."""
    for qual, ok, why in results:
        print(f"   {'PASS ✓' if ok else 'FAIL ✗'}  {qual:<14} {'' if ok else why}"
              + ("" if ok else caret(root, why)))


def cmd_check(root, emit=False):
    files = load(root)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace); fold_comptime(files, namespace); run_emits(files, namespace)
    results, passing = check(files, namespace)
    print(f"── check {root} ──")
    report(results, root)
    if emit:                                             # `check` is report-only unless asked to emit
        pathlib.Path("out.c").write_text(emit_c(files, passing, namespace))
        print("   -> wrote out.c")


def cmd_build(root):
    bf = parse((pathlib.Path(root) / "build.zen").read_text(), "build")
    cfg = interpret_build(bf)
    if cfg["target"] not in _TARGETS:
        raise SystemExit(f"build.zen: target {cfg['target']!r} is not supported yet "
                         f"(have: {', '.join(sorted(_TARGETS))}; wasm is the next backend)")
    print(f"── build.zen graph ──\n   Executable {cfg['name']}  "
          f"(main={cfg['main']}, out={cfg['out_dir']}, target={cfg['target']})")
    if cfg["cflags"] or cfg["links"]:
        print(f"   cc flags {cfg['cflags']}  links {cfg['links']}")
    for u in cfg["uses"]:
        print(f"   use \"{u['module']}\"  -> namespace `{u['ns']}`")
    for t in cfg["tests"]:
        print(f"   Test {t}  (declared)")

    files = load(root, skip={"build.zen"} | set(cfg["tests"]))
    load_uses(cfg, files)                          # install foreign-binding namespaces (b.use)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace); fold_comptime(files, namespace); run_emits(files, namespace)
    results, passing = check(files, namespace)
    print("\n── type checks ──")
    report(results, root)

    entry_ns = pathlib.Path(cfg["main"]).with_suffix("").as_posix().replace("/", ".")
    entry = f"{entry_ns}.main"
    if entry not in passing:
        raise SystemExit(f"\nentry '{entry}' did not type-check — nothing to run")

    # The entry must return i32 (printed) or void (run for effect) — anything else
    # has no sensible harness, so reject it rather than misformat (e.g. %d on a ptr).
    entry_ret = namespace.walk(entry).value.ret
    if entry_ret == PrimT(Prim.VOID):
        harness = (f'\nint main(void) {{\n    {c_name(entry)}();\n'
                   f'    return 0;\n}}\n')
    elif entry_ret == PrimT(Prim.I32):
        harness = (f'\n#include <stdio.h>\nint main(void) {{\n'
                   f'    printf("{cfg["name"]} -> %d\\n", {c_name(entry)}());\n'
                   f'    return 0;\n}}\n')
    else:
        raise SystemExit(f"\nentry '{entry}' must return i32 or void, not {show(entry_ret)}")
    out_dir = pathlib.Path(root) / cfg["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath, bpath = out_dir / f"{cfg['name']}.c", out_dir / cfg["name"]
    cc_extra = [*cfg["cflags"], *(f"-l{lib}" for lib in cfg["links"])]   # build.zen flags
    exe_c = emit_c(files, passing, namespace, harness, roots={entry})        # DCE from the entry
    if compile_if_changed(cpath, bpath, exe_c, cc_extra):
        print(f"\n── compiled {cpath} ──")
    else:
        print(f"\n── {bpath} up to date (cached) ──")
    print(f"── running {bpath} ──")
    print(subprocess.run([str(bpath)], capture_output=True, text=True, timeout=120).stdout, end="")

    failures = sum(run_test_root(root, t, cc_extra) for t in cfg["tests"])
    if failures:
        raise SystemExit(f"\n{failures} zen test(s) failed or did not type-check")


def cmd_dump(root):
    """Print the canonical, structural AST dump + hash of each .zen module under `root` —
    the reference a future Zen-written parser is diffed against (see zen/astdump.py)."""
    paths = sorted(pathlib.Path(root).glob("*.zen"))
    if not paths:
        raise SystemExit(f"no .zen files in {root!r}")
    for p in paths:
        try:
            f = parse(p.read_text(), p.stem)
        except SyntaxError as e:
            print(f"── {p.name} ──  PARSE ERROR: {e}")
            continue
        print(f"── {p.name} ──  [{ast_hash(f)}]")
        print(dump(f))


def cli(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "build"
    rest = argv[1:]
    root = next((a for a in rest if not a.startswith("-")), "examples")
    if cmd == "build":
        cmd_build(root)
    elif cmd == "check":
        cmd_check(root, emit="--emit" in rest)           # check is report-only; --emit writes out.c
    elif cmd == "dump":
        cmd_dump(root)
    else:
        raise SystemExit(f"usage: zen [build|check|dump] <root> [--emit]   (unknown command {cmd!r})")


if __name__ == "__main__":
    cli()
