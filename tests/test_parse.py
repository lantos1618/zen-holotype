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


# parse_module reads EVERY top-level function declaration (decl boundaries found by
# brace-matching), into a [Decl] genModule lowers to a whole translation unit.
MODULE_DRIVER = """
{ Malloc } = std.alloc
{ parse_module } = std.parse
{ genModule } = std.genc
{ String, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(genModule(addr(m).parse_module("%s")))
    0
}
"""


def gen_module(tmp_path, src):
    (tmp_path / "main.zen").write_text(MODULE_DRIVER % src)
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


# parse -> std.check (resolve enum match enames) -> genModule. The check pass is what fills
# each multi-variant match's enum type name, which the parser can't know on its own.
CHECKED_DRIVER = """
{ Malloc } = std.alloc
{ parse_module } = std.parse
{ resolve_module } = std.check
{ genModule } = std.genc
{ String, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    m := Malloc { _: 0 }
    emit(genModule(addr(m).resolve_module(addr(m).parse_module("%s"))))
    0
}
"""


def gen_checked_module(tmp_path, src):
    (tmp_path / "main.zen").write_text(CHECKED_DRIVER % src)
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


def _compile_run(tmp_path, generated, call):
    """cc the generated C with `int main(){ return <call>; }`; return the exit code."""
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + generated + f"\nint main(void){{ return {call}; }}\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "g")]).returncode


def test_parse_decl_recursive_factorial(tmp_path):
    # a boolean `.match` lowers to genc's ternary Cond, so the self-hosted compiler handles
    # BRANCHING — and therefore RECURSION. The whole thing is parsed + lowered in Zen.
    gen = gen_decl(tmp_path, r"fact* = (n: i32) i32 { (n <= 1).match { true => 1, false => n * fact(n - 1) } }")
    assert gen == "int32_t fact(int32_t n) { return ((n <= 1) ? 1 : (n * fact((n - 1)))); }"
    assert _compile_run(tmp_path, gen, "fact(5)") == 120


def test_parse_decl_recursive_fibonacci(tmp_path):
    gen = gen_decl(tmp_path, r"fib* = (n: i32) i32 { (n < 2).match { true => n, false => fib(n - 1) + fib(n - 2) } }")
    assert gen == "int32_t fib(int32_t n) { return ((n < 2) ? n : (fib((n - 1)) + fib((n - 2)))); }"
    assert _compile_run(tmp_path, gen, "fib(10)") == 55   # 0,1,1,2,3,5,8,13,21,34,55


def test_parse_decl_recursive_gcd(tmp_path):
    # Euclid's gcd: recursion + `%` + a boolean `.match` (-> ternary), all self-hosted. The
    # headline — a Zen program reads gcd's source as a string and emits a running native gcd.
    gen = gen_decl(tmp_path, r"gcd* = (a: i32, b: i32) i32 { (b == 0).match { true => a, false => gcd(b, a % b) } }")
    assert gen == "int32_t gcd(int32_t a, int32_t b) { return ((b == 0) ? a : gcd(b, (a % b))); }"
    assert _compile_run(tmp_path, gen, "gcd(48, 36)") == 12


def test_parse_module_multiple_functions(tmp_path):
    # two function decls in one source -> a whole translation unit; one calls the other.
    gen = gen_module(tmp_path, r"inc* = (x: i32) i32 { x + 1 }\ndbl* = (x: i32) i32 { x + x }")
    assert gen == ("int32_t inc(int32_t x) { return (x + 1); } "
                   "int32_t dbl(int32_t x) { return (x + x); } ")
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return inc(dbl(5)); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 11   # dbl(5)=10, inc(10)=11


def test_parse_module_with_recursion(tmp_path):
    # the full picture: a whole module with a RECURSIVE function + a plain one, parsed and
    # lowered entirely in Zen, then compiled and run.
    gen = gen_module(tmp_path, r"sq* = (n: i32) i32 { n * n }\nfact* = (n: i32) i32 { (n <= 1).match { true => 1, false => n * fact(n - 1) } }")
    assert "int32_t sq(int32_t n) { return (n * n); }" in gen
    assert "int32_t fact(int32_t n) { return ((n <= 1) ? 1 : (n * fact((n - 1)))); }" in gen
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return fact(4) + sq(3); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 33   # fact(4)=24, sq(3)=9


def test_parse_module_n_arg_calls(tmp_path):
    # N-arg function calls: a 3-arg function, called with 3 args — the self-hosted compiler
    # can now parse a call to a multi-arg function (which all its own helpers are).
    gen = gen_module(tmp_path, r"add3* = (a: i32, b: i32, c: i32) i32 { a + b + c }\nfn* = () i32 { add3(1, 2, 3) }")
    assert "int32_t add3(int32_t a, int32_t b, int32_t c) { return ((a + b) + c); }" in gen
    assert "int32_t fn() { return add3(1, 2, 3); }" in gen
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return fn(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 6


# ── struct declarations: the self-hosted parser reads user-defined TYPES ──────────────
# `name*: { field: Type, … }` parses into genc's StructDecl (a `typedef struct`). The decl
# dispatch branches on the token after the name (`:` -> struct, `=` -> function), so a
# module mixes structs and functions freely.
def test_parse_module_struct_declaration(tmp_path):
    gen = gen_module(tmp_path, r"Pt*: { x: i32, y: i32 }")
    assert gen == "typedef struct Pt Pt; struct Pt { int32_t x; int32_t y; }; "


def test_parse_module_struct_and_function(tmp_path):
    # one module mixing a struct decl and a function decl -> a single translation unit
    gen = gen_module(tmp_path, r"V3*: { x: i32, y: i32, z: i32 }\nsum3* = (a: i32, b: i32, c: i32) i32 { a + b + c }")
    assert "typedef struct V3 V3; struct V3 { int32_t x; int32_t y; int32_t z; };" in gen
    assert "int32_t sum3(int32_t a, int32_t b, int32_t c) { return ((a + b) + c); }" in gen
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return sum3(1, 2, 3); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 6


# ── named types: a type token that isn't a primitive becomes a Named type ─────────────
# ty_of materializes the lexeme into genc's Named (a `Pt` -> `struct Pt`), so struct types
# flow through parameter, field and return positions instead of defaulting to i32.
def test_parse_named_type_param_and_field_and_return(tmp_path):
    gen = gen_module(tmp_path, r"Pt*: { x: i32, y: i32 }\nLine*: { a: Pt, b: Pt }\nfx* = (p: Pt) i32 { 0 }\norigin* = (p: Pt) Pt { p }")
    assert "struct Pt { int32_t x; int32_t y; };" in gen          # primitives still primitive
    assert "struct Line { Pt a; Pt b; };" in gen                  # a field typed by another struct
    assert "int32_t fx(Pt p) { return 0; }" in gen                # a struct PARAMETER
    assert "Pt origin(Pt p) { return p; }" in gen                 # a struct RETURN type
    # the whole translation unit compiles (struct passed by value, returned by value)
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen +
                                  "\nint main(void){ Pt p = {3, 4}; return origin(p).x; }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 3


# ── field access + struct literals: the self-hosted parser reads/builds struct VALUES ──
# `p.x` parses to genc's Member (a postfix on an atom, chainable). `Pt { x: 1, y: 2 }`
# parses to genc's MakeStruct (a C compound literal `(Pt){ .x = 1, .y = 2 }`).
def test_parse_field_access(tmp_path):
    gen = gen_module(tmp_path, r"Pt*: { x: i32, y: i32 }\nnorm_sq* = (p: Pt) i32 { p.x * p.x + p.y * p.y }")
    assert "int32_t norm_sq(Pt p) { return ((p.x * p.x) + (p.y * p.y)); }" in gen


def test_parse_struct_literal(tmp_path):
    gen = gen_module(tmp_path, r"Pt*: { x: i32, y: i32 }\nmk* = (a: i32, b: i32) Pt { Pt { x: a, y: b } }")
    assert "Pt mk(int32_t a, int32_t b) { return (Pt){ .x = a, .y = b }; }" in gen


def test_parse_struct_milestone(tmp_path):
    # THE MILESTONE: a struct DECLARED, CONSTRUCTED (literal), PASSED (by value), and
    # FIELD-ACCESSED — the whole module lexed -> parsed -> lowered -> compiled -> run in Zen.
    gen = gen_module(tmp_path, r"Pt*: { x: i32, y: i32 }\nmk* = (a: i32, b: i32) Pt { Pt { x: a, y: b } }\nnorm_sq* = (p: Pt) i32 { p.x * p.x + p.y * p.y }")
    assert "struct Pt { int32_t x; int32_t y; };" in gen
    assert "Pt mk(int32_t a, int32_t b) { return (Pt){ .x = a, .y = b }; }" in gen
    assert "int32_t norm_sq(Pt p) { return ((p.x * p.x) + (p.y * p.y)); }" in gen
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return norm_sq(mk(3, 4)); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 25   # 3*3 + 4*4 = 25


# ── char literals: `'c'` / `'\n'` parse to their byte value (an integer) ──────────────
# This is the self-hosted parser's OWN idiom — its byte tests read `b == ':'`, not `b == 58`.
def test_parse_char_literal(tmp_path):
    gen = gen_module(tmp_path, r"is_colon* = (b: u8) bool { b == ':' }")
    assert "bool is_colon(uint8_t b) { return (b == 58); }" in gen   # ':' is byte 58


def test_parse_char_literal_escape(tmp_path):
    # the runtime source must contain a genuine backslash escape `'\n'`; through the driver's
    # Zen-string layer that takes a doubled backslash here (`\\n` -> `\n` in the source).
    gen = gen_module(tmp_path, r"nl* = () i32 { '\\n' }")
    assert "int32_t nl() { return 10; }" in gen      # '\n' -> byte 10 via esc_byte


# ── imports: `{ A, B } = std.x` is recognized and skipped (it emits no code) ──────────
def test_parse_imports_are_skipped(tmp_path):
    # a real file starts with imports; the parser skips them and parses the decls that follow.
    gen = gen_module(tmp_path, r"{ Expr, Func } = std.genc\n{ scan } = std.lex\ninc* = (x: i32) i32 { x + 1 }")
    assert gen == "int32_t inc(int32_t x) { return (x + 1); } "   # only the function, no import noise


# ── if statements: `if (c) { … } else { … }` -> genc If (sibling to @while) ───────────
def test_parse_if_else(tmp_path):
    gen = gen_module(tmp_path, r"sign* = (x: i32) i32 { r := 0\n if (x > 0) { r = 1 } else { r = 2 }\n r }")
    assert "if ((x > 0)) { r = 1; } else { r = 2; }" in gen
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return sign(5) * 10 + sign(-3); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 12   # sign(5)=1, sign(-3)=2 -> 12


def test_parse_if_nested_in_while(tmp_path):
    # an if (no else) inside a @while body — block_stmt recurses into both forms
    gen = gen_module(tmp_path, r"cnt* = (n: i32) i32 { c := 0\n i := 0\n @while(i < n) { if (i > 2) { c = c + 1 }\n i = i + 1 }\n c }")
    assert "while ((i < n)) { if ((i > 2)) { c = (c + 1); } else { } i = (i + 1); }" in gen
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return cnt(7); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 4    # i = 3,4,5,6 are > 2


# ── string literals: `"…"` parse to genc StrLit; escapes are resolved then re-escaped ────
# (The `\"` here escapes the quotes through the driver's own Zen-string layer.)
def test_parse_string_literal(tmp_path):
    gen = gen_module(tmp_path, r'greet* = () str { \"hello\" }')
    assert 'const char* greet() { return "hello"; }' in gen


def test_parse_string_literal_escape(tmp_path):
    # source `"a\nb"` -> unescaped to a real newline byte -> genc re-escapes it back to \n
    gen = gen_module(tmp_path, r'bang* = () str { \"a\\nb\" }')
    assert r'const char* bang() { return "a\nb"; }' in gen


# ── Ptr<T> types: a type can be a pointer (in params, fields, returns, recursively) ──────
# `Ptr<T>` parses via a position-returning parse_ty (a single-token ty_of can't span the
# `< … >`), recursing so `Ptr<Ptr<T>>` works. genc lowers Ptr(T) to `T*`.
def test_parse_ptr_param_and_field(tmp_path):
    gen = gen_module(tmp_path, r"Node*: { v: i32, next: Ptr<Node> }\nhead* = (p: Ptr<Node>) i32 { 0 }")
    assert "struct Node { int32_t v; Node* next; };" in gen     # a self-referential pointer field
    assert "int32_t head(Node* p) { return 0; }" in gen          # a pointer parameter


def test_parse_ptr_nested_and_return(tmp_path):
    gen = gen_module(tmp_path, r"Node*: { v: i32, next: Ptr<Node> }\nderef2* = (pp: Ptr<Ptr<i32>>) i32 { 0 }\nself* = (p: Ptr<Node>) Ptr<Node> { p }")
    assert "int32_t deref2(int32_t** pp) { return 0; }" in gen   # nested Ptr<Ptr<…>> -> **
    assert "Node* self(Node* p) { return p; }" in gen            # a pointer RETURN type


# ── enum declarations: the self-hosted parser reads SUM types ─────────────────────────
# `name*: A | B | C` (or `Circle(i32) | Square(i32)`) parses into genc's EnumDecl (a tagged
# union). The decl dispatch picks struct vs enum by the token after `:` (`{` -> struct,
# else a variant list -> enum). Variants are `|`-separated; a `Name(Type)` carries a payload.
def test_parse_module_enum_no_payload(tmp_path):
    gen = gen_module(tmp_path, r"Color*: Red | Green | Blue")
    assert "typedef struct Color Color;" in gen
    assert "struct Color { int32_t tag; };" in gen
    assert "enum { Color_Red, Color_Green, Color_Blue };" in gen


def test_parse_module_enum_with_payloads(tmp_path):
    gen = gen_module(tmp_path, r"Shape*: Circle(i32) | Square(i32)")
    assert "struct Shape { int32_t tag; union { int32_t Circle; int32_t Square; } u; };" in gen
    assert "enum { Shape_Circle, Shape_Square };" in gen


def test_parse_module_enum_struct_function_mix(tmp_path):
    # one module with an enum, a struct, and a function -> a single translation unit that compiles
    gen = gen_module(tmp_path, r"Color*: Red | Green | Blue\nPt*: { x: i32, y: i32 }\nf* = (n: i32) i32 { n }")
    assert "enum { Color_Red, Color_Green, Color_Blue };" in gen
    assert "struct Pt { int32_t x; int32_t y; };" in gen
    assert "int32_t f(int32_t n) { return n; }" in gen
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return f(7); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 7


# ── THE ENUM WALL FALLS: multi-variant match (parse -> std.check -> genc) ──────────────
# A `subject.match { .Variant(bind) => body, … }` parses into a genc Match with an EMPTY
# ename (the parser has no types). std.check fills the ename by looking up the subject's
# declared type among the function's params, so genc can emit the `subj.tag == E_V` chain.
# This is the wall that blocked multi-variant match since #131 — it needed the enum's name.
def test_parse_enum_match_resolves_ename(tmp_path):
    gen = gen_checked_module(tmp_path, r"Shape*: Circle(i32) | Square(i32)\narea* = (s: Shape) i32 { s.match { .Circle(r) => r * r * 3, .Square(w) => w * w } }")
    # the match lowered to a tag-test ternary with payload binding — and ename is "Shape"
    assert "int32_t area(Shape s) { return (s.tag == Shape_Circle ? " in gen
    assert "({ __auto_type r = s.u.Circle; ((r * r) * 3); })" in gen
    assert "({ __auto_type w = s.u.Square; (w * w); })" in gen
    # construct each variant and run the self-hosted-compiled match
    (tmp_path / "g.c").write_text(
        "#include <stdint.h>\n" + gen +
        "\nint main(void){ Shape c = { .tag = Shape_Circle, .u.Circle = 3 };"
        " Shape q = { .tag = Shape_Square, .u.Square = 5 };"
        " return area(c) + area(q); }\n")   # 27 + 25 = 52
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 52


def test_parse_enum_constructor(tmp_path):
    # `.Variant(payload)` -> genc MakeEnum, `.Variant` -> Tag. The parser leaves the enum type
    # "" ; std.check fills it by looking the variant up among the module's enum decls.
    gen = gen_checked_module(tmp_path, r"Shape*: Circle(i32) | Square(i32)\nmk* = (n: i32) Shape { .Circle(n) }")
    assert "Shape mk(int32_t n) { return (Shape){ .tag = Shape_Circle, .u.Circle = n }; }" in gen


def test_parse_enum_milestone(tmp_path):
    # 🏁 THE MILESTONE: an enum DECLARED, CONSTRUCTED (.Circle), passed, and MATCHED — the
    # whole module lexed -> parsed -> CHECKED -> lowered -> compiled -> run, entirely in Zen.
    gen = gen_checked_module(tmp_path, r"Shape*: Circle(i32) | Square(i32)\nmk* = (n: i32) Shape { .Circle(n) }\narea* = (s: Shape) i32 { s.match { .Circle(r) => r * r * 3, .Square(w) => w * w } }")
    assert "Shape mk(int32_t n) { return (Shape){ .tag = Shape_Circle, .u.Circle = n }; }" in gen
    assert "int32_t area(Shape s) { return (s.tag == Shape_Circle ? " in gen
    (tmp_path / "g.c").write_text("#include <stdint.h>\n" + gen + "\nint main(void){ return area(mk(3)); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 27   # Circle(3) -> 3*3*3


def test_parse_enum_match_no_payload(tmp_path):
    # variants without payloads: the arms are bare bodies, no __auto_type binding
    gen = gen_checked_module(tmp_path, r"Bit*: Lo | Hi\nval* = (b: Bit) i32 { b.match { .Lo => 0, .Hi => 1 } }")
    assert "int32_t val(Bit b) { return (b.tag == Bit_Lo ? (0) : (1)); }" in gen
    (tmp_path / "g.c").write_text(
        "#include <stdint.h>\n" + gen +
        "\nint main(void){ Bit h = { .tag = Bit_Hi }; return val(h); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 1


# ── @while loops: the self-hosted parser handles ITERATION, not just recursion ───────
# `@while(cond) { stmts }` parses into genc's While. The loop body is a brace block of
# let / assign / nested-@while statements with NO trailing return (a loop yields no value).
# These are real iterative algorithms — lexed, parsed and lowered entirely in Zen.
def test_parse_while_iterative_factorial(tmp_path):
    gen = gen_decl(tmp_path, r"fact* = (n: i32) i32 { acc := 1\n i := 1\n @while(i <= n) { acc = acc * i\n i = i + 1 }\n acc }")
    assert gen == ("int32_t fact(int32_t n) { int32_t acc = 1; int32_t i = 1; "
                   "while ((i <= n)) { acc = (acc * i); i = (i + 1); } return acc; }")
    assert _compile_run(tmp_path, gen, "fact(5)") == 120


def test_parse_while_power(tmp_path):
    gen = gen_decl(tmp_path, r"powi* = (base: i32, n: i32) i32 { acc := 1\n i := 0\n @while(i < n) { acc = acc * base\n i = i + 1 }\n acc }")
    assert gen == ("int32_t powi(int32_t base, int32_t n) { int32_t acc = 1; int32_t i = 0; "
                   "while ((i < n)) { acc = (acc * base); i = (i + 1); } return acc; }")
    assert _compile_run(tmp_path, gen, "powi(3, 4)") == 81   # exit codes are 8-bit, so keep it < 256


def test_parse_while_digit_sum(tmp_path):
    gen = gen_decl(tmp_path, r"digit_sum* = (n: i32) i32 { acc := 0\n m := n\n @while(m > 0) { acc = acc + (m % 10)\n m = m / 10 }\n acc }")
    assert gen == ("int32_t digit_sum(int32_t n) { int32_t acc = 0; int32_t m = n; "
                   "while ((m > 0)) { acc = (acc + (m % 10)); m = (m / 10); } return acc; }")
    assert _compile_run(tmp_path, gen, "digit_sum(12345)") == 15


def test_parse_while_is_prime(tmp_path):
    # the loop body ASSIGNS a value computed by a boolean `.match` (-> ternary); the result
    # type is bool, so the harness pulls in <stdbool.h>.
    gen = gen_decl(tmp_path, r"is_prime* = (n: i32) bool { d := 2\n ok := true\n @while((d * d) <= n) { ok = ((n % d) == 0).match { true => false, false => ok }\n d = d + 1 }\n (n >= 2) && ok }")
    assert gen == ("bool is_prime(int32_t n) { int32_t d = 2; int32_t ok = true; "
                   "while (((d * d) <= n)) { ok = (((n % d) == 0) ? false : ok); d = (d + 1); } "
                   "return ((n >= 2) && ok); }")
    (tmp_path / "g.c").write_text("#include <stdint.h>\n#include <stdbool.h>\n" + gen +
                                  "\nint main(void){ return is_prime(7) + is_prime(9) * 2; }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 1   # is_prime(7)=1, is_prime(9)=0


def test_parse_while_nested_loops(tmp_path):
    # a @while inside a @while — the loop-body block parser recurses (the inner `j :=` is a
    # let inside the outer block). Counts the n*n pairs.
    gen = gen_decl(tmp_path, r"grid* = (n: i32) i32 { total := 0\n i := 0\n @while(i < n) { j := 0\n @while(j < n) { total = total + 1\n j = j + 1 }\n i = i + 1 }\n total }")
    assert gen == ("int32_t grid(int32_t n) { int32_t total = 0; int32_t i = 0; "
                   "while ((i < n)) { int32_t j = 0; while ((j < n)) { total = (total + 1); j = (j + 1); } "
                   "i = (i + 1); } return total; }")
    assert _compile_run(tmp_path, gen, "grid(4)") == 16
