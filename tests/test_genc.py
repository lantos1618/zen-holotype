"""std.genc — a C backend written IN Zen, run at RUNTIME. A zen program builds an AST
value and calls genC(f) -> String to emit C source while it runs. This is the
self-hosting seed: codegen is the language's own lowered code, not the host's. The
expression AST is recursive (Bin holds Ptr<Expr> children), walked with match-deref.

The decisive test closes the loop: the C that the zen program emits at runtime is
itself compiled and executed, and computes the right answer."""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def emit_via_zen(tmp_path, main_body):
    """Compile + run a zen program whose main builds an AST and prints genC(it).
    Returns the C source the zen program produced at runtime."""
    prog = """
{ Func, Expr, lit, vref, bin, genC } = std.genc
{ String, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
%s
}
""" % main_body
    (tmp_path / "main.zen").write_text(prog)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace)
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


def test_genc_emits_a_flat_expression(tmp_path):
    # int32_t addk(int32_t x) { return (x + 5); }
    body = """
    x := vref("x")
    five := lit(5)
    e := bin("+", addr(x), addr(five))
    emit(genC(Func { name: "addk", param: "x", body: addr(e) }))
    0"""
    assert emit_via_zen(tmp_path, body) == "int32_t addk(int32_t x) { return (x + 5); }"


def test_genc_emits_a_nested_expression(tmp_path):
    # a recursive AST -> nested C: ((x + 5) * x), with a multi-digit constant too
    body = """
    five := lit(5)
    x1 := vref("x")
    xp5 := bin("+", addr(x1), addr(five))
    x2 := vref("x")
    e := bin("*", addr(xp5), addr(x2))
    emit(genC(Func { name: "f", param: "x", body: addr(e) }))
    0"""
    assert emit_via_zen(tmp_path, body) == "int32_t f(int32_t x) { return ((x + 5) * x); }"


def test_generated_c_compiles_and_runs(tmp_path):
    # THE LOOP: the C that the zen program emits at runtime is compiled and executed.
    body = """
    five := lit(5)
    x1 := vref("x")
    xp5 := bin("+", addr(x1), addr(five))
    x2 := vref("x")
    e := bin("*", addr(xp5), addr(x2))
    emit(genC(Func { name: "f", param: "x", body: addr(e) }))
    0"""
    generated = emit_via_zen(tmp_path, body)          # int32_t f(int32_t x) { return ((x + 5) * x); }
    (tmp_path / "gen.c").write_text(
        "#include <stdint.h>\n" + generated +
        '\n#include <stdio.h>\nint main(void){ printf("%d\\n", f(10)); return 0; }\n')
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(tmp_path / "gen.c"), "-o", str(tmp_path / "gen")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                # the GENERATED C is valid C
    assert subprocess.run([str(tmp_path / "gen")], capture_output=True, text=True).stdout.strip() == "150"
