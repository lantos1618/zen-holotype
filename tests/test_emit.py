"""P4 slice 1: comptime generators emit real declarations.

A function over `Ast` is a *prelude generator* — run at comptime, never checked
or lowered. `emit gen(reflect(T))` evaluates the generator, splices the
declaration it returns into the module, and that declaration then flows through
the same check + lower as hand-written code. This is the hinge for self-hosting
impl/derive (VISION step 4).
"""
import subprocess
import pytest

from holotype.main import (load, build_space, build_scopes, resolve, fold_comptime,
                           run_emits, check, emit_c, is_prelude)
from holotype.comptime import ComptimeErr
from holotype.ast import Fn


def frontend(tmp_path, src):
    (tmp_path / "m.zen").write_text(src)
    files = load(tmp_path)
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    fold_comptime(files, space)
    run_emits(files, space)                  # the splice pass under test
    results, passing = check(files, space)
    return files, space, results, passing


def test_emit_splices_a_real_checked_lowered_decl(tmp_path):
    files, space, results, passing = frontend(tmp_path, """
Point: { x: i32, y: i32, z: i32 }
arity_of = (T: Ast) Ast { fn_const(concat(name_of(T), "_arity"), field_count(T)) }
emit arity_of(reflect(Point))
pub main = () i32 { Point_arity() }
""")
    # the generated decl exists, type-checked, and is reachable in the trie
    assert ("m.Point_arity", True, "ok") in results
    assert "m.Point_arity" in passing
    assert isinstance(space.walk("m.Point_arity").value, Fn)
    # the generator itself is prelude: never checked, never in results
    assert not any(q == "m.arity_of" for q, _, _ in results)
    # it lowers like any function, and main calls it
    c = emit_c(files, passing, space)
    assert "int32_t m_Point_arity(void) { return 3; }" in c
    assert "m_main(void) { return m_Point_arity(); }" in c


def test_emitted_decl_runs(tmp_path):
    files, space, _, passing = frontend(tmp_path, """
Rgb: { r: u8, g: u8, b: u8, a: u8 }
arity_of = (T: Ast) Ast { fn_const(concat(name_of(T), "_n"), field_count(T)) }
emit arity_of(reflect(Rgb))
pub main = () i32 { Rgb_n() }
""")
    c = emit_c(files, passing, space)
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return m_main(); }\n")
    subprocess.run(["cc", str(cfile), "-o", str(tmp_path / "o")], check=True)
    assert subprocess.run([str(tmp_path / "o")]).returncode == 4   # Rgb has 4 fields


_DERIVE_ZERO = """
zero_build = (T: Ast, sl: Ast, i: i32) Ast {
    match (field_count(T) - i) {
        0 => sl,
        _ => zero_build(T, with_field(sl, field_name_at(T, i), ast_int(0)), i + 1)
    }
}
derive_zero = (T: Ast) Ast {
    fn_of(concat(name_of(T), "_zero"), zero_build(T, struct_start(name_of(T)), 0))
}
"""


def test_derive_zero_iterates_every_field(tmp_path):
    # a real derive: comptime tail-recursion walks ALL fields and builds a
    # constructor that zeroes each one.
    files, space, results, passing = frontend(tmp_path, """
Point: { x: i32, y: i32, z: i32 }
""" + _DERIVE_ZERO + """
emit derive_zero(reflect(Point))
pub main = () i32 { p := Point_zero()  p.x + p.y + p.z }
""")
    assert ("m.Point_zero", True, "ok") in results
    c = emit_c(files, passing, space)
    assert ".x = 0, .y = 0, .z = 0" in c                  # every field, in order
    assert "m_Point m_Point_zero(void)" in c


def test_derived_constructor_runs_over_mixed_widths(tmp_path):
    files, space, _, passing = frontend(tmp_path, """
Mixed: { a: i32, b: u8, c: i64 }
""" + _DERIVE_ZERO + """
emit derive_zero(reflect(Mixed))
pub main = () i32 { m := Mixed_zero()  m.a }
""")
    c = emit_c(files, passing, space)
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return m_main(); }\n")
    r = subprocess.run(["cc", "-Wall", str(cfile), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr                    # int literal adapts to u8/i64 field
    assert subprocess.run([str(tmp_path / "o")]).returncode == 0


_DERIVE_EQ = """
field_eq = (T: Ast, i: i32) Ast {
    ast_bin("==", ast_field(ast_var("a"), field_name_at(T, i)),
                  ast_field(ast_var("b"), field_name_at(T, i)))
}
eq_body = (T: Ast, acc: Ast, i: i32) Ast {
    match (field_count(T) - i) {
        0 => acc,
        _ => eq_body(T, ast_bin("&&", acc, field_eq(T, i)), i + 1)
    }
}
derive_eq = (T: Ast) Ast {
    fn_eq(concat(name_of(T), "_eq"), name_of(T), eq_body(T, ast_bool(true), 0))
}
"""


def test_derive_eq_builds_a_function_from_general_constructors(tmp_path):
    # a second, non-trivial derive over the GENERAL expr constructors (ast_bin /
    # ast_field / ast_var / ast_bool) — no bespoke ast_eq/ast_and helpers.
    files, space, results, passing = frontend(tmp_path, """
Point: { x: i32, y: i32 }
""" + _DERIVE_EQ + """
emit derive_eq(reflect(Point))
""")
    assert ("m.Point_eq", True, "ok") in results
    c = emit_c(files, passing, space)
    assert "bool m_Point_eq(m_Point const * a, m_Point const * b)" in c
    assert "((true && (a->x == b->x)) && (a->y == b->y))" in c


def test_derived_eq_runs(tmp_path):
    files, space, _, passing = frontend(tmp_path, """
Point: { x: i32, y: i32 }
""" + _DERIVE_EQ + """
emit derive_eq(reflect(Point))
pub main = () i32 {
    a := Point { x: 1, y: 2 }
    b := Point { x: 1, y: 2 }
    c := Point { x: 9, y: 2 }
    g := match (Point_eq(addr(a), addr(b))) { true => 10, false => 0 }
    h := match (Point_eq(addr(a), addr(c))) { true => 1, false => 0 }
    g + h
}
""")
    c = emit_c(files, passing, space)
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return m_main(); }\n")
    subprocess.run(["cc", str(cfile), "-o", str(tmp_path / "o")], check=True)
    assert subprocess.run([str(tmp_path / "o")]).returncode == 10   # equal -> 10, unequal -> +0


def test_is_prelude_flags_ast_functions(tmp_path):
    files, space, _, _ = frontend(tmp_path, """
gen   = (T: Ast) Ast { fn_const("k", field_count(T)) }
plain = (n: i32) i32 { n }
S: { a: i32 }
emit gen(reflect(S))
""")
    decls = {d.name: d for d in files["m"].decls if isinstance(d, Fn)}
    assert is_prelude(decls["gen"]) and not is_prelude(decls["plain"])


def test_emit_rejects_runtime_op_in_generator(tmp_path):
    with pytest.raises(ComptimeErr):           # a generator can't touch runtime ops
        frontend(tmp_path, """
S: { a: i32 }
bad = (T: Ast) Ast { fn_const("k", load(T)) }
emit bad(reflect(S))
""")


def test_reflect_requires_a_type(tmp_path):
    with pytest.raises(ComptimeErr):
        frontend(tmp_path, """
nope = (T: Ast) Ast { fn_const("k", field_count(T)) }
emit nope(reflect(missing))
""")
