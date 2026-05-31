"""P4: the reified AST is defined in Zen; derives are self-hosted.

`prelude/derive.zen` defines the `Ast`/`Decl` model AND the derives, entirely in
Zen. A derive runs at comptime, reads a type's structure via the host reflection
kernel (reflect/name_of/field_count/field_name_at), and returns an `Ast` value.
The host's only remaining job is to *reify* that value into a real declaration
(`reify_decl`) and splice it — which then flows through the same check + lower as
hand-written code.
"""
import subprocess
import pytest

from holotype.main import (load, build_space, build_scopes, resolve, fold_comptime,
                           run_emits, check, emit_c, is_prelude_ns)
from holotype.comptime import ComptimeErr, reify_decl
from holotype.ast import Fn


def frontend(tmp_path, src):
    (tmp_path / "m.zen").write_text(src)
    files = load(tmp_path)                    # load() also pulls in the bundled prelude
    space = build_space(files)
    build_scopes(files)
    resolve(files, space)
    fold_comptime(files, space)
    run_emits(files, space)                   # evaluate the derive + reify + splice
    results, passing = check(files, space)
    return files, space, results, passing


def test_prelude_is_loaded_but_never_lowered(tmp_path):
    files, space, results, passing = frontend(tmp_path, """
{ derive_zero } = prelude.derive
Point: { x: i32, y: i32 }
emit derive_zero(reflect(Point))
pub main = () i32 { p := Point_zero()  p.x }
""")
    # the Ast model lives in Zen, under the prelude namespace
    assert "prelude.derive" in files
    assert any(d.name == "Ast" for d in files["prelude.derive"].decls)
    # ...but the prelude is comptime-only: nothing from it is checked or lowered
    assert not any(q.startswith("prelude") for q, _, _ in results)
    c = emit_c(files, passing, space)
    assert "m_Ast" not in c and "m_FList" not in c       # the model never reaches C
    assert is_prelude_ns("prelude.derive") and not is_prelude_ns("m")


def test_derive_zero_self_hosted(tmp_path):
    files, space, results, passing = frontend(tmp_path, """
{ derive_zero } = prelude.derive
Point: { x: i32, y: i32, z: i32 }
emit derive_zero(reflect(Point))
pub main = () i32 { p := Point_zero()  p.x + p.y + p.z }
""")
    assert ("m.Point_zero", True, "ok") in results
    c = emit_c(files, passing, space)
    assert "m_Point m_Point_zero(void) { return (m_Point){ .x = 0, .y = 0, .z = 0 }; }" in c


def test_derive_eq_self_hosted_and_runs(tmp_path):
    files, space, results, passing = frontend(tmp_path, """
{ derive_eq } = prelude.derive
Point: { x: i32, y: i32 }
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
    assert ("m.Point_eq", True, "ok") in results
    c = emit_c(files, passing, space)
    assert "bool m_Point_eq(m_Point const * a, m_Point const * b)" in c
    assert "((true && (a->x == b->x)) && (a->y == b->y))" in c
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return m_main(); }\n")
    subprocess.run(["cc", str(cfile), "-o", str(tmp_path / "o")], check=True)
    assert subprocess.run([str(tmp_path / "o")]).returncode == 10   # equal -> 10, unequal -> +0


def test_reify_decl_turns_a_zen_ast_value_into_a_fn():
    # a hand-built Zen `Decl` value (as comptime produces) reifies to a host Fn
    zero_for_two = ("@enum", "Func", {
        "nm": "P_zero", "ps": ("@enum", "PNil", None), "ret": "P",
        "body": ("@enum", "Struct", {"ty": "P", "inits":
                 ("@enum", "FCons", {"key": "x", "val": ("@enum", "Int", 0),
                  "tail": ("@enum", "FNil", None)})})})
    fn = reify_decl(zero_for_two)
    assert isinstance(fn, Fn) and fn.name == "P_zero" and fn.params == []


def test_emitted_decls_are_reachable_in_the_trie(tmp_path):
    files, space, _, passing = frontend(tmp_path, """
{ derive_zero } = prelude.derive
Rgb: { r: u8, g: u8, b: u8, a: u8 }
emit derive_zero(reflect(Rgb))
pub main = () i32 { c := Rgb_zero()  0 }
""")
    assert isinstance(space.walk("m.Rgb_zero").value, Fn)
    c = emit_c(files, passing, space)
    cfile = tmp_path / "o.c"
    cfile.write_text(c + "\nint main(void){ return m_main(); }\n")
    r = subprocess.run(["cc", "-Wall", str(cfile), "-o", str(tmp_path / "o")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_reflect_requires_a_type(tmp_path):
    with pytest.raises(ComptimeErr):
        frontend(tmp_path, """
{ derive_zero } = prelude.derive
emit derive_zero(reflect(missing))
""")
