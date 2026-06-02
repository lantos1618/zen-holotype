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


# ── identifiers + let: a whole function, source -> C -> run ──────────────────────
# parse_fn parses `x := <expr>` then a return `<expr>` into a whole function. This
# crosses the runtime-string wall: an identifier is a SPAN into the source, so its
# lexeme is copied out and NUL-terminated (cstr) to become a genc name. The body lives
# on the heap (a stack slice literal would dangle once the Func is returned).
FN_DRIVER = """
{ Malloc } = std.alloc
{ parse_fn } = std.parse
{ genC } = std.genc
{ String, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(genC(addr(m).parse_fn("%s", "f")))
    0
}
"""


def gen_fn(tmp_path, src):
    (tmp_path / "main.zen").write_text(FN_DRIVER % src)
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


def test_parse_fn_lowers_a_whole_function(tmp_path):
    # let-bind x, return an expression that USES x — the identifier survives as a runtime
    # name, the whole fn lowers, compiles, and runs.
    gen = gen_fn(tmp_path, r"x := 1 + 2\nx * 3")
    assert gen == "int32_t f() { int32_t x = (1 + 2); return (x * 3); }"
    assert run_generated(tmp_path, gen) == 9


def test_parse_fn_another_binding(tmp_path):
    gen = gen_fn(tmp_path, r"total := 10 - 1\ntotal * total")
    assert gen == "int32_t f() { int32_t total = (10 - 1); return (total * total); }"
    assert run_generated(tmp_path, gen) == 81


def test_parse_fn_dynamic_statement_list(tmp_path):
    # N lets (not a fixed count), each able to reference earlier ones. The body is built
    # as a cons-list while parsing, then materialized to a HEAP [Stmt] — if it were a
    # stack slice literal it would dangle once the Func is returned and genC would crash.
    gen = gen_fn(tmp_path, r"a := 2\nb := a + 3\nc := b * b\nc - 1")
    assert gen == ("int32_t f() { int32_t a = 2; int32_t b = (a + 3); "
                   "int32_t c = (b * b); return (c - 1); }")
    assert run_generated(tmp_path, gen) == 24          # a=2, b=5, c=25, c-1=24


def test_parse_fn_zero_lets_is_just_a_return(tmp_path):
    # the degenerate case: no lets, the whole source is the returned expression.
    gen = gen_fn(tmp_path, r"7 * 6")
    assert gen == "int32_t f() { return (7 * 6); }"
    assert run_generated(tmp_path, gen) == 42


def test_parse_fn_assignment_statement(tmp_path):
    # `name = value` (single =, not := ) reassigns a binding — distinct from a let
    gen = gen_fn(tmp_path, r"x := 1\nx = x + 5\nx")
    assert gen == "int32_t f() { int32_t x = 1; x = (x + 5); return x; }"
    assert run_generated(tmp_path, gen) == 6


# parse_decl reads a whole function DECLARATION from real source — the name comes from the
# source (not a caller arg), the `* = () i32` head is skipped, and the brace body is parsed.
DECL_DRIVER = """
{ Malloc } = std.alloc
{ parse_decl } = std.parse
{ genC } = std.genc
{ String, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(genC(addr(m).parse_decl("%s")))
    0
}
"""


def gen_decl(tmp_path, src):
    (tmp_path / "main.zen").write_text(DECL_DRIVER % src)
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


def test_parse_decl_reads_a_whole_function(tmp_path):
    # the name is taken from the source; the body lowers and runs.
    gen = gen_decl(tmp_path, r"f* = () i32 { x := 4\n x + 3 }")
    assert gen == "int32_t f() { int32_t x = 4; return (x + 3); }"
    assert run_generated(tmp_path, gen) == 7


def test_parse_decl_typed_parameters(tmp_path):
    # a typed parameter list parses into genc's [Param]; the params lower as C parameters
    # and the body references them. Call it with arguments.
    gen = gen_decl(tmp_path, r"add* = (x: i32, y: i32) i32 { x + y }")
    assert gen == "int32_t add(int32_t x, int32_t y) { return (x + y); }"
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return add(3, 4); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 7


def test_parse_decl_return_type(tmp_path):
    # the return-type token after `)` maps via ty_of (here i64 -> int64_t)
    gen = gen_decl(tmp_path, r"wide* = (x: i64) i64 { x + 1 }")
    assert gen == "int64_t wide(int64_t x) { return (x + 1); }"
