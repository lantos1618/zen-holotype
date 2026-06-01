"""std.genc — a C backend written IN Zen, run at RUNTIME. A zen program builds an AST
value and calls genC(f) -> String to emit C source while it runs. This is the
self-hosting seed: codegen is the language's own lowered code, not the host's.

The decisive test closes the loop: the C that the zen program emits at runtime is
itself compiled and executed, and computes the right answer."""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def emit_via_zen(tmp_path, ast_src):
    """Compile + run a zen program that builds `ast_src` and prints genC(ast). Returns
    the C source string the zen program produced at runtime."""
    prog = """
{ Func, Expr, Term, VarData, genC } = std.genc
{ String, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 { emit(genC(%s))\n 0 }
""" % ast_src
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


def test_genc_emits_expected_c_source(tmp_path):
    # int32_t addk(int32_t x) { return x + 5; }
    ast = 'Func { name: "addk", param: "x", body: Expr { op: "+", lhs: .Var(VarData { name: "x" }), rhs: .Int(5) } }'
    assert emit_via_zen(tmp_path, ast) == "int32_t addk(int32_t x) { return x + 5; }"


def test_genc_handles_vars_and_multidigit_ints(tmp_path):
    # int32_t f(int32_t n) { return n * 100; }  — multi-digit int via the itoa path
    ast = 'Func { name: "f", param: "n", body: Expr { op: "*", lhs: .Var(VarData { name: "n" }), rhs: .Int(100) } }'
    assert emit_via_zen(tmp_path, ast) == "int32_t f(int32_t n) { return n * 100; }"


def test_generated_c_compiles_and_runs(tmp_path):
    # THE LOOP: the C that the zen program emits at runtime is compiled and executed.
    ast = 'Func { name: "addk", param: "x", body: Expr { op: "+", lhs: .Var(VarData { name: "x" }), rhs: .Int(5) } }'
    generated = emit_via_zen(tmp_path, ast)
    (tmp_path / "gen.c").write_text(
        "#include <stdint.h>\n" + generated +
        '\n#include <stdio.h>\nint main(void){ printf("%d\\n", addk(10)); return 0; }\n')
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(tmp_path / "gen.c"), "-o", str(tmp_path / "gen")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                      # the GENERATED C is valid C
    assert subprocess.run([str(tmp_path / "gen")], capture_output=True, text=True).stdout.strip() == "15"
