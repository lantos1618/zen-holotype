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
