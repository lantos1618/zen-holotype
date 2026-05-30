"""holotype driver.

    python3 -m holotype build [dir]   # read build.zen, compile + link + run the exe
    python3 -m holotype check [dir]   # type-check report only, emit a C lib

Pipeline: parse -> insert into trie -> resolve refs -> infer/fits -> to_c.
Only well-typed functions are codegen'd.
"""
from __future__ import annotations
import sys, pathlib, subprocess
from .ast import (Struct, EnumDecl, Fn, PrimT, NameT, PtrT,
                  Str, StructLit, MethodCall, EnumCtor)
from .types import Space, fits, infer, TypeErr
from .lower import c_struct, c_proto, c_def, show, c_name
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


def resolve_type(t, scope, space):
    if isinstance(t, PrimT):
        return t
    if isinstance(t, PtrT):
        return PtrT(t.dir, resolve_type(t.pointee, scope, space))
    if isinstance(t, NameT):
        args = tuple(resolve_type(a, scope, space) for a in t.args)
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
                for fld in d.fields:
                    fld.type = resolve_type(fld.type, f.scope, space)
            elif isinstance(d, Fn):
                for p in d.params:
                    p.type = resolve_type(p.type, f.scope, space)
                d.ret = resolve_type(d.ret, f.scope, space)


def check(files, space):
    results, passing = [], set()
    for f in files.values():
        for d in f.decls:
            if not isinstance(d, Fn):
                continue
            qual = f"{f.ns}.{d.name}"
            expr = d.body[-1] if d.body else None
            if expr is None:
                continue
            locals_ = {p.name: p.type for p in d.params}
            try:
                bt = infer(expr, locals_, space, f.scope)
                if not fits(bt, d.ret):
                    raise TypeErr("return type", bt, d.ret)
                results.append((qual, True, "ok")); passing.add(qual)
            except TypeErr as ex:
                why = (f"{show(ex.given)}  ⊀  {show(ex.want)}"
                       if ex.given is not None else str(ex))
                results.append((qual, False, why))
    return results, passing


def emit_c(files, passing, space, extra=""):
    lines = ["#include <stdint.h>", "#include <stdbool.h>", ""]
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Struct):
                lines.append(c_struct(f"{f.ns}.{d.name}", d))
    lines.append("")
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Fn) and f"{f.ns}.{d.name}" in passing:
                lines.append(c_proto(f"{f.ns}.{d.name}", d))
    lines.append("")
    for f in files.values():
        for d in f.decls:
            if isinstance(d, Fn) and f"{f.ns}.{d.name}" in passing:
                lines.append(c_def(f"{f.ns}.{d.name}", d, space, f.scope))
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


def cli(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "build"
    arg = argv[1] if len(argv) > 1 else "examples"
    (cmd_build if cmd == "build" else cmd_check)(arg)


if __name__ == "__main__":
    cli()
