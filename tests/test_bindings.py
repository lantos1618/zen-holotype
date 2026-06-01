"""Foreign bindings wired through the build object.

A foreign binding is a Zen module of declarations. `c = b.use("libc")` in
build.zen installs the bundled `bindings/libc.zen` (bodyless functions = C
symbols) under the namespace `c`; program modules then `{ malloc, free } = c`
and call them — they lower to bare C calls (the symbols are bodyless bindings,
declared by the libc headers). The kernel knows only how to load a binding
module as a namespace — nothing C-specific lives in Python; the signatures are
Zen. A real *generating* adapter (translate-c / wasm / python) would run through
the same `b.use` seam, producing `[Decl]` instead of being a static module."""
import subprocess

from zen.main import (parse, interpret_build, load, load_uses, build_namespace,
                           build_scopes, resolve, fold_comptime, run_emits, check, emit_c)


def build(root, build_src, main_src):
    (root / "build.zen").write_text(build_src)
    (root / "main.zen").write_text(main_src)
    cfg = interpret_build(parse(build_src, "build"))
    files = load(root, skip={"build.zen"})
    load_uses(cfg, files)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    return cfg, files, namespace, passing


_BUILD = """
{ Builder, Executable } = @builtin.build
build = (b: Builder) i32 {
    c = b.use("libc")
    b.add(Executable { name: "demo", main: "main.zen", out_dir: "build" })
    0
}
"""


def test_use_is_read_from_build():
    cfg = interpret_build(parse(_BUILD, "build"))
    assert cfg["uses"] == [{"module": "libc", "ns": "c"}]


def test_binding_module_installs_an_importable_namespace(tmp_path):
    _, files, namespace, passing = build(tmp_path, _BUILD, """
{ malloc, free } = c
main* = () i32 { free(malloc(64))  0 }
""")
    assert "c" in files                                  # the namespace was installed
    assert namespace.walk("c.malloc").value.extern is True   # bundled binding, bodyless
    assert "main.main" in passing


def test_program_using_a_binding_compiles_and_runs(tmp_path):
    _, files, namespace, passing = build(tmp_path, _BUILD, """
{ malloc, free, putchar } = c
main* = () i32 {
    p := malloc(64)
    free(p)
    putchar(72) putchar(105)        // "Hi"
    0
}
""")
    c = emit_c(files, passing, namespace)
    cpath = tmp_path / "o.c"
    cpath.write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cpath), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                   # warning-clean (libc via headers)
    run = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True)
    assert run.stdout == "Hi"


def test_unknown_binding_module_is_rejected(tmp_path):
    cfg = interpret_build(parse(_BUILD.replace('"libc"', '"nope"'), "build"))
    files = load(tmp_path, skip={"build.zen"})
    try:
        load_uses(cfg, files)
        assert False, "expected SystemExit for an unknown binding module"
    except SystemExit as e:
        assert "no binding module" in str(e)


# ── generating adapters (goal #19): b.use a module that GENERATES its bindings ─
_GEN_BUILD = """
{ Builder, Executable } = @builtin.build
build = (b: Builder) i32 {
    c = b.use("gen_demo")          // a *generating* adapter (emits .Extern via @emit)
    b.add(Executable { name: "demo", main: "main.zen", out_dir: "build" })
    0
}
"""


def test_generating_adapter_installs_emitted_bindings(tmp_path):
    cfg, files, namespace, passing = build(tmp_path, _GEN_BUILD, """
{ putchar } = c
main* = () i32 { putchar(90)  putchar(10)  0 }    // "Z\\n" via a GENERATED binding
""")
    assert namespace.walk("c.putchar").value.extern is True   # generated, bodyless C binding
    assert "main.main" in passing
    c = emit_c(files, passing, namespace)
    cpath = tmp_path / "o.c"
    cpath.write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", str(cpath), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = subprocess.run([str(tmp_path / "o")], capture_output=True, text=True)
    assert out.stdout == "Z\n"
