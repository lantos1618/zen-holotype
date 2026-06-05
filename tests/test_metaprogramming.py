"""Metaprogramming the Zen way — as ordinary VALUES, not an `@emit` pragma.

The AST is reified as plain Zen data (std.genc), and std.genc.genModule emits a module at
runtime. So a code generator is just a function that builds and returns AST; a `derive` is just
a function over a StructDecl; a build is just a program that assembles decls (hand-written +
generated) and calls genModule. std.ast supplies heap-allocating builders so a generator can
RETURN the AST it built (genc's raw ctors return values whose slice/pointer children are
stack-allocated and would dangle across the return).

This replaces `@emit` — no compiler pragma, no comptime evaluator, fully first-class.
"""
import subprocess

from zen.main import (load, build_namespace, build_scopes, resolve,
                      fold_comptime, run_emits, check, emit_c)

# a metaprogram: derive a getter for each field of a struct, then assemble + emit a module —
# entirely as ordinary Zen, using std.ast's builders.
_DERIVE = r'''
{ Malloc } = std.alloc
{ String, new, bytes } = std.string
{ field, param, ti32, Decl } = std.genc
{ genModule } = std.genc_emit
{ resolve_module } = std.check
{ evar, efield, ret, func, struct, named, ptrto, decls } = std.ast
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }

// `derive(getters)` — a generator that BUILDS AND RETURNS a Decl (the case that dangles without
// std.ast's heap builders). `p.<field>` auto-derefs to `p-><field>` once resolve_module runs.
derive_getter = (a: Ptr<Malloc>, sname: str, fname: str) Decl {
    p := a.evar("p")
    a.func(fname, [param("p", a.ptrto(named(sname)))], ti32(), [ret(a.efield(p, fname))])
}

main* = () i32 {
    a    := Malloc { _: 0 }
    pt   := addr(a).struct("Pt", [field("x", ti32()), field("y", ti32())])
    getx := addr(a).derive_getter("Pt", "x")
    gety := addr(a).derive_getter("Pt", "y")
    emit(genModule(addr(a).resolve_module(addr(a).decls([pt, getx, gety]))))
    0
}
'''


def _run(tmp_path, prog):
    (tmp_path / "main.zen").write_text(prog)
    files = load(tmp_path); ns = build_namespace(files)
    build_scopes(files); resolve(files, ns)
    fold_comptime(files, ns); run_emits(files, ns)
    _, passing = check(files, ns)
    c = emit_c(files, passing, ns, roots={"main.main"})
    (tmp_path / "o.c").write_text(c + "\nint main(void){ return main_main(); }\n")
    assert subprocess.run(["cc", "-std=gnu11", str(tmp_path / "o.c"), "-o", str(tmp_path / "o")],
                          capture_output=True, text=True).returncode == 0
    return subprocess.run([str(tmp_path / "o")], capture_output=True, text=True).stdout


def test_derive_generates_getters(tmp_path):
    out = _run(tmp_path, _DERIVE)
    # the generator produced the struct and a getter per field, with the Ptr receiver auto-derefed
    assert "struct Pt { int32_t x; int32_t y; };" in out
    assert "int32_t x(Pt* p) { return p->x; }" in out
    assert "int32_t y(Pt* p) { return p->y; }" in out


def test_generated_getters_compile_and_run(tmp_path):
    out = _run(tmp_path, _DERIVE)
    # the generated C is real, compilable C: build it and call a derived getter
    (tmp_path / "g.c").write_text(
        "#include <stdint.h>\n" + out
        + "\nint main(void){ Pt p = { 3, 4 }; return (x(&p) == 3 && y(&p) == 4) ? 0 : 1; }\n")
    assert subprocess.run(["cc", "-std=gnu11", "-w", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 0


# a real `#[derive]`: one call generates an accessor for EVERY field, each with its own type.
_DERIVE_ALL = r'''
{ Malloc } = std.alloc
{ String, new, bytes } = std.genc
{ String, new, bytes } = std.string
{ field, dstruct, StructDecl, ti32, ti64 } = std.genc
{ genModule } = std.genc_emit
{ resolve_module } = std.check
{ derive_accessors, fields, decls, concat } = std.ast
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    a  := Malloc { _: 0 }
    sd := StructDecl { name: "Pt", fields: addr(a).fields([field("x", ti32()), field("y", ti64())]) }
    mod := addr(a).concat(addr(a).decls([dstruct(sd)]), addr(a).derive_accessors(sd))
    emit(genModule(addr(a).resolve_module(mod)))
    0
}
'''.replace("{ String, new, bytes } = std.genc\n", "")


def test_derive_accessors_covers_every_field_with_its_type(tmp_path):
    out = _run(tmp_path, _DERIVE_ALL)
    assert "int32_t x(Pt* s) { return s->x; }" in out   # i32 field
    assert "int64_t y(Pt* s) { return s->y; }" in out   # i64 field — the derive respects the type


# derive_eq: a structural equality generated field-by-field — another derive on the same foundation.
_DERIVE_EQ = r'''
{ Malloc } = std.alloc
{ String, new, bytes } = std.string
{ field, dstruct, StructDecl, ti32, Decl } = std.genc
{ genModule } = std.genc_emit
{ resolve_module } = std.check
{ derive_eq, fields, decls, concat } = std.ast
putchar = (c: i32) i32
emit = (s: String) void { bytes(s).loop((h, i, b) { putchar(b) }) }
main* = () i32 {
    a  := Malloc { _: 0 }
    sd := StructDecl { name: "Pt", fields: addr(a).fields([field("x", ti32()), field("y", ti32())]) }
    mod := addr(a).concat(addr(a).decls([dstruct(sd)]), addr(a).decls([addr(a).derive_eq("pt_eq", sd)]))
    emit(genModule(addr(a).resolve_module(mod)))
    0
}
'''


def test_derive_eq_generates_field_by_field_equality(tmp_path):
    out = _run(tmp_path, _DERIVE_EQ)
    assert "bool pt_eq(Pt* x, Pt* y)" in out
    assert "(x->x == y->x)" in out and "(x->y == y->y)" in out
    # and it RUNS: equal structs compare equal, differing ones don't
    (tmp_path / "g.c").write_text(
        "#include <stdint.h>\n#include <stdbool.h>\n" + out
        + "\nint main(void){ Pt a={1,2}, b={1,2}, c={1,9};"
          " return (pt_eq(&a,&b) && !pt_eq(&a,&c)) ? 0 : 1; }\n")
    assert subprocess.run(["cc", "-std=gnu11", "-w", str(tmp_path / "g.c"), "-o", str(tmp_path / "g")],
                          capture_output=True, text=True).returncode == 0
    assert subprocess.run([str(tmp_path / "g")]).returncode == 0
