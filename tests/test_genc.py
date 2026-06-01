"""std.genc — a C backend written IN Zen, run at RUNTIME. A zen program builds an AST
value and calls genC(f) -> String to emit C source while it runs. This is the
self-hosting seed: codegen is the language's own lowered code, not the host's.

The AST is recursive (Bin holds Ptr<Expr> children, walked with match-deref); a body
is a [Stmt] (Let / Return); a Func has typed parameters (`[Param]`) and a return Ty.

The decisive tests close the loop: the C the zen program emits at runtime is itself
compiled and executed, and computes the right answer."""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve, fold_comptime,
                      run_emits, check, emit_c)

_IMPORTS = """
{ Func, Param, Ty, Decl, StructDecl, Field, lit, vref, bin, call, cond, member, slet, sret, sassign, sif, swhile, param, tnamed, ti32, ti64, tu8, tbool, field, sdef, vdef, edef, dfunc, dstruct, denum, draw, tvoid, genC, genModule } = std.genc
{ String, bytes } = std.string
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
"""


def emit_via_zen(tmp_path, main_body):
    """Compile + run a zen program whose main builds an AST and prints genC(it).
    Returns the C source the zen program produced at runtime."""
    (tmp_path / "main.zen").write_text(_IMPORTS + "main* = () i32 {\n%s\n}\n" % main_body)
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


def compile_and_run(tmp_path, generated, call):
    """cc the GENERATED C with a `main` that prints `call`, return its stdout."""
    (tmp_path / "gen.c").write_text(
        "#include <stdint.h>\n#include <stdbool.h>\n" + generated +
        f'\n#include <stdio.h>\nint main(void){{ printf("%d\\n", {call}); return 0; }}\n')
    r = subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", str(tmp_path / "gen.c"), "-o", str(tmp_path / "gen")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                 # the GENERATED C is valid C
    return subprocess.run([str(tmp_path / "gen")], capture_output=True, text=True).stdout.strip()


def test_genc_emits_a_single_return(tmp_path):
    body = """
    x := vref("x")
    five := lit(5)
    e := bin("+", addr(x), addr(five))
    emit(genC(Func { name: "addk", params: [param("x", ti32())], ret: ti32(), body: [sret(addr(e))] }))
    0"""
    assert emit_via_zen(tmp_path, body) == "int32_t addk(int32_t x) { return (x + 5); }"


def test_genc_emits_a_nested_expression(tmp_path):
    body = """
    five := lit(5)
    x1 := vref("x")
    xp5 := bin("+", addr(x1), addr(five))
    x2 := vref("x")
    e := bin("*", addr(xp5), addr(x2))
    emit(genC(Func { name: "f", params: [param("x", ti32())], ret: ti32(), body: [sret(addr(e))] }))
    0"""
    assert emit_via_zen(tmp_path, body) == "int32_t f(int32_t x) { return ((x + 5) * x); }"


def test_genc_emits_multiple_typed_params(tmp_path):
    # int32_t add(int32_t a, int32_t b) { return (a + b); }  — and it runs: add(3,4) == 7
    body = """
    a := vref("a")
    b := vref("b")
    sum := bin("+", addr(a), addr(b))
    ps := [param("a", ti32()), param("b", ti32())]
    emit(genC(Func { name: "add", params: ps, ret: ti32(), body: [sret(addr(sum))] }))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert generated == "int32_t add(int32_t a, int32_t b) { return (a + b); }"
    assert compile_and_run(tmp_path, generated, "add(3, 4)") == "7"


def test_genc_maps_scalar_types(tmp_path):
    # the Ty enum maps to C type names in both the return and the parameters
    body = """
    z := lit(0)
    ps := [param("flag", tbool()), param("byte", tu8())]
    emit(genC(Func { name: "f", params: ps, ret: ti64(), body: [sret(addr(z))] }))
    0"""
    assert emit_via_zen(tmp_path, body) == "int64_t f(bool flag, uint8_t byte) { return 0; }"


def test_genc_emits_a_recursive_factorial_that_runs(tmp_path):
    # The capstone: zen builds the AST for a RECURSIVE function with a conditional,
    # genC emits it at runtime, the generated C compiles and computes fact(5) == 120.
    body = """
    n_a := vref("n")
    one_a := lit(1)
    nle1 := bin("<=", addr(n_a), addr(one_a))
    thenE := lit(1)
    n_b := vref("n")
    one_b := lit(1)
    nm1 := bin("-", addr(n_b), addr(one_b))
    fcall := call("fact", addr(nm1))
    n_c := vref("n")
    nfact := bin("*", addr(n_c), addr(fcall))
    e := cond(addr(nle1), addr(thenE), addr(nfact))
    emit(genC(Func { name: "fact", params: [param("n", ti32())], ret: ti32(), body: [sret(addr(e))] }))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert generated == "int32_t fact(int32_t n) { return ((n <= 1) ? 1 : (n * fact((n - 1)))); }"
    assert compile_and_run(tmp_path, generated, "fact(5)") == "120"


def test_genc_module_of_two_functions_compiles_and_runs(tmp_path):
    # a whole translation unit: dbl + calc (which CALLS dbl). calc(4) == dbl(5) == 10.
    body = """
    n1 := vref("n")
    n2 := vref("n")
    nn := bin("+", addr(n1), addr(n2))
    dbl := Func { name: "dbl", params: [param("n", ti32())], ret: ti32(), body: [sret(addr(nn))] }
    x := vref("x")
    one := lit(1)
    xp1 := bin("+", addr(x), addr(one))
    dc := call("dbl", addr(xp1))
    calc := Func { name: "calc", params: [param("x", ti32())], ret: ti32(), body: [sret(addr(dc))] }
    emit(genModule([dfunc(dbl), dfunc(calc)]))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert "int32_t dbl(int32_t n) { return (n + n); }" in generated
    assert "int32_t calc(int32_t x) { return dbl((x + 1)); }" in generated
    assert compile_and_run(tmp_path, generated, "calc(4)") == "10"


def test_genc_module_with_a_struct_and_a_function(tmp_path):
    # a real translation unit: a struct typedef + a function, both valid C.
    body = """
    pt := sdef("Point", [field("x", ti32()), field("y", ti32())])
    a := vref("a")
    b := vref("b")
    sum := bin("+", addr(a), addr(b))
    add := Func { name: "add", params: [param("a", ti32()), param("b", ti32())], ret: ti32(), body: [sret(addr(sum))] }
    emit(genModule([dstruct(pt), dfunc(add)]))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert "typedef struct { int32_t x; int32_t y; } Point;" in generated
    assert "int32_t add(int32_t a, int32_t b) { return (a + b); }" in generated
    # the emitted struct + function are valid C used together
    assert compile_and_run(tmp_path, generated, "({ Point p = {3, 4}; add(p.x, p.y); })") == "7"


def test_genc_multi_statement_body_compiles_and_runs(tmp_path):
    # a Let + a Return: int32_t f(int32_t x) { int32_t y = (x + 5); return (y * y); } -> f(10)==225
    body = """
    five := lit(5)
    x := vref("x")
    xp5 := bin("+", addr(x), addr(five))
    y1 := vref("y")
    y2 := vref("y")
    ysq := bin("*", addr(y1), addr(y2))
    stmts := [slet("y", addr(xp5)), sret(addr(ysq))]
    emit(genC(Func { name: "f", params: [param("x", ti32())], ret: ti32(), body: stmts }))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert generated == "int32_t f(int32_t x) { int32_t y = (x + 5); return (y * y); }"
    assert compile_and_run(tmp_path, generated, "f(10)") == "225"


def test_genc_raw_escape_emits_verbatim_c(tmp_path):
    # the escape hatch: a DRaw decl emits arbitrary C unchanged, so anything the AST
    # doesn't model (qualifiers, attributes, pragmas, intrinsics) is still reachable.
    body = """
    emit(genModule([
        draw("typedef int32_t Word;"),
        draw(" static inline int32_t inc(int32_t x) { return x + 1; }")
    ]))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert "typedef int32_t Word;" in generated
    assert "static inline int32_t inc(int32_t x) { return x + 1; }" in generated
    assert compile_and_run(tmp_path, generated, "inc(41)") == "42"


def test_genc_emits_explicit_simd_via_raw(tmp_path):
    # explicit SIMD: a GCC vector type + a 4-wide add, emitted verbatim by genc.
    # The emitted C compiles and computes a real vector add (portable GCC vector ext).
    body = """
    emit(genModule([
        draw("typedef int32_t v4i __attribute__((vector_size(16)));"),
        draw(" v4i vadd(v4i a, v4i b) { return a + b; }")
    ]))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert "__attribute__((vector_size(16)))" in generated
    call = "({ v4i a = {1,2,3,4}, b = {10,20,30,40}; v4i c = vadd(a, b); c[3]; })"
    assert compile_and_run(tmp_path, generated, call) == "44"


def test_genc_emits_a_while_loop_that_runs(tmp_path):
    # an iterative sum: while + assign. sum_to(5) == 15.
    body = """
    zero := lit(0)
    one := lit(1)
    i1 := vref("i")
    n1 := vref("n")
    c := bin("<=", addr(i1), addr(n1))
    acc1 := vref("acc")
    i2 := vref("i")
    accpi := bin("+", addr(acc1), addr(i2))
    i3 := vref("i")
    one2 := lit(1)
    ip1 := bin("+", addr(i3), addr(one2))
    loopbody := [sassign("acc", addr(accpi)), sassign("i", addr(ip1))]
    accret := vref("acc")
    stmts := [slet("acc", addr(zero)), slet("i", addr(one)), swhile(addr(c), loopbody), sret(addr(accret))]
    emit(genC(Func { name: "sum_to", params: [param("n", ti32())], ret: ti32(), body: stmts }))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert "while ((i <= n)) {" in generated
    assert compile_and_run(tmp_path, generated, "sum_to(5)") == "15"


def test_genc_emits_an_if_else_that_runs(tmp_path):
    # int32_t clamp(int32_t x) { if ((x < 0)) { return 0; } else { return x; } } -> clamp(7)==7
    body = """
    zero := lit(0)
    x1 := vref("x")
    neg := bin("<", addr(x1), addr(zero))
    z2 := lit(0)
    x2 := vref("x")
    e := sif(addr(neg), [sret(addr(z2))], [sret(addr(x2))])
    emit(genC(Func { name: "clamp", params: [param("x", ti32())], ret: ti32(), body: [e] }))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert generated == "int32_t clamp(int32_t x) { if ((x < 0)) { return 0; } else { return x; } }"
    assert compile_and_run(tmp_path, generated, "clamp(7)") == "7"


def test_genc_named_struct_param_and_field_access(tmp_path):
    # int32_t sumxy(Point p) { return (p.x + p.y); }  over a struct passed by value.
    body = """
    pt := sdef("Point", [field("x", ti32()), field("y", ti32())])
    p1 := vref("p")
    mx := member(addr(p1), "x")
    p2 := vref("p")
    my := member(addr(p2), "y")
    sum := bin("+", addr(mx), addr(my))
    fn := Func { name: "sumxy", params: [param("p", tnamed("Point"))], ret: ti32(), body: [sret(addr(sum))] }
    emit(genModule([dstruct(pt), dfunc(fn)]))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert "int32_t sumxy(Point p) { return (p.x + p.y); }" in generated
    assert compile_and_run(tmp_path, generated, "({ Point p = {3, 4}; sumxy(p); })") == "7"


def test_genc_emits_enum_typedefs(tmp_path):
    # a tagged-union enum (with payloads) and a no-payload enum (no union), both valid C.
    body = """
    shape := edef("Shape", [vdef("Circle", ti32()), vdef("Square", ti32()), vdef("Dot", tvoid())])
    color := edef("Color", [vdef("Red", tvoid()), vdef("Green", tvoid()), vdef("Blue", tvoid())])
    emit(genModule([denum(shape), denum(color)]))
    0"""
    generated = emit_via_zen(tmp_path, body)
    assert "typedef struct { int32_t tag; union { int32_t Circle; int32_t Square; } u; } Shape;" in generated
    assert "enum { Shape_Circle, Shape_Square, Shape_Dot };" in generated
    assert "typedef struct { int32_t tag; } Color;" in generated          # no union: all variants are void
    assert "enum { Color_Red, Color_Green, Color_Blue };" in generated
    # the emitted enums are valid C, used together
    call = "({ Shape s = {.tag=Shape_Circle, .u.Circle=5}; Color c = {.tag=Color_Green}; s.u.Circle + c.tag; })"
    assert compile_and_run(tmp_path, generated, call) == "6"
