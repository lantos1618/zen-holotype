"""std.parse — a recursive-descent parser written IN zen. It pulls tokens from the
lexer's pure positional scan() and builds genc's Expr AST (a heap tree of Ptr<Expr>
nodes through an explicit allocator) — the same AST genc lowers, so the front and back
ends meet. This first cut parses arithmetic (integers, + - * /, parens) with the usual
precedence; eval() interprets the tree, so each test is `eval_str(<src>) == <value>`,
computed entirely in zen.
"""
import subprocess

import pytest

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)


def eval_str(tmp_path, expr):
    src = ('{ Malloc } = std.alloc\n{ eval_str } = std.parse\n'
           'main* = () i32 { m := Malloc { _: 0 }\n addr(m).eval_str("%s") }\n' % expr)
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")]).returncode


@pytest.mark.parametrize("expr,want", [
    ("(1 + 2) * 3", 9),       # parens override precedence
    ("1 + 2 * 3", 7),         # * binds tighter than +
    ("10 - 3 - 2", 5),        # - is left-associative
    ("20 / 4 / 5", 1),        # / is left-associative
    ("2 * (3 + 4) - 1", 13),  # a mix
    ("100", 100),             # a multi-digit atom
    ("((1+1))*((2+2))", 8),   # nested parens
])
def test_eval_arithmetic(tmp_path, expr, want):
    assert eval_str(tmp_path, expr) == want


# ── close the loop: source -> AST -> C -> run, all in zen ────────────────────────
# A zen program parses the source into genc's Expr, wraps it in `int32_t f() { return e; }`,
# and calls genC to emit that C as a runtime String. We then compile the EMITTED C and run
# f(): the whole pipeline (lex + parse + lower) is zen; the host only runs the final cc.
LOOP_DRIVER = """
{ Malloc } = std.alloc
{ parse } = std.parse
{ Func, genC, sret, ti32 } = std.genc
{ String, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    e := addr(m).parse("%s")
    emit(genC(Func { name: "f", params: [], ret: ti32(), body: [sret(e)] }))
    0
}
"""


def gen_c(tmp_path, expr):
    """Run the zen pipeline; return the C source it emitted for `f`."""
    (tmp_path / "main.zen").write_text(LOOP_DRIVER % expr)
    files = load(tmp_path)
    namespace = build_namespace(files)
    build_scopes(files); resolve(files, namespace)
    fold_comptime(files, namespace); run_emits(files, namespace)
    _, passing = check(files, namespace)
    assert "main.main" in passing
    c = emit_c(files, passing, namespace, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-std=gnu11",
                        str(tmp_path / "o.c"), "-o", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


def run_generated(tmp_path, generated):
    """cc the GENERATED C and run f(), returning its exit code."""
    (tmp_path / "gen.c").write_text("#include <stdint.h>\n" + generated +
                                    "\nint main(void){ return f(); }\n")
    r = subprocess.run(["cc", "-std=gnu11", str(tmp_path / "gen.c"), "-o", str(tmp_path / "gen")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return subprocess.run([str(tmp_path / "gen")]).returncode


def test_source_to_c_round_trips(tmp_path):
    # the headline: zen lexes+parses+lowers "(1 + 2) * 3" to C, which we compile and run.
    generated = gen_c(tmp_path, "(1 + 2) * 3")
    assert generated == "int32_t f() { return ((1 + 2) * 3); }"
    assert run_generated(tmp_path, generated) == 9


def test_source_to_c_respects_precedence(tmp_path):
    # the emitted C's parens encode the precedence the parser resolved: 1 + 2*3 = 7.
    generated = gen_c(tmp_path, "1 + 2 * 3")
    assert generated == "int32_t f() { return (1 + (2 * 3)); }"
    assert run_generated(tmp_path, generated) == 7
