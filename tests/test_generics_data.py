"""Goal Arc 3 (Slice 1) — generic DATA structures RUN via backend monomorphization.

genc has no type parameters, so a `Box<T>: { v: T }` is a DGenStruct template that emits no C of its
own. The monomorphize pass (genModule's pass 0) discovers each concrete `Box<i32>` used in a typed
position and emits a specialized C struct `Box_i32` with `T` substituted, mangling the name; the
generic struct literal `Box<i32>{…}` carries that mangled name. End-to-end through the self-hosted
toolchain: source -> parse -> resolve -> genModule -> C -> compile -> run.
"""
import pytest

from _selfhost import run_value, emit_c_for


def test_generic_struct_runs(tmp_path):
    src = ("Box<T>: { v: T }\n"
           "get* = (b: Box<i32>) i32 { b.v }\n"
           "test* = () i32 { get(Box<i32>{ v: 42 }) }")
    run_value(tmp_path, src, 42)


def test_monomorphized_name_is_emitted(tmp_path):
    # the concrete struct + its mangled name appear in the emitted C; the bare `Box`/`T` do not.
    c = emit_c_for(tmp_path, "Box<T>: { v: T }\nget* = (b: Box<i32>) i32 { b.v }")
    assert "struct Box_i32 { int32_t v; }" in c
    assert "Box_i32 b" in c
    assert " T " not in c                        # the type param never leaks into C


def test_generic_struct_extra_concrete_field(tmp_path):
    # a field whose type is NOT the type param stays as-is under substitution
    run_value(tmp_path,
        "W<T>: { a: T, b: i32 }\n"
        "f* = (w: W<i32>) i32 { w.a + w.b }\n"
        "test* = () i32 { f(W<i32>{ a: 40, b: 2 }) }", 42)


def test_two_type_params(tmp_path):
    run_value(tmp_path,
        "Pair<A, B>: { x: A, y: B }\n"
        "f* = (p: Pair<i32, i32>) i32 { p.x + p.y }\n"
        "test* = () i32 { f(Pair<i32, i32>{ x: 20, y: 22 }) }", 42)


def test_two_distinct_instantiations(tmp_path):
    # Box<i32> and Box<u8> each monomorphize to their own struct (and uses of one type dedupe).
    src = ("B<T>: { v: T }\n"
           "gi* = (b: B<i32>) i32 { b.v }\n"
           "gu* = (b: B<u8>) i32 { b.v }\n"
           "test* = () i32 { gi(B<i32>{ v: 40 }) + gu(B<u8>{ v: 2 }) }")
    c = emit_c_for(tmp_path, src)
    assert "struct B_i32 { int32_t v; }" in c
    assert "struct B_u8 { uint8_t v; }" in c
    run_value(tmp_path, src, 42)


def test_plain_struct_still_works(tmp_path):
    # a non-generic struct literal is unaffected by the monomorphize pass
    run_value(tmp_path, "P*: { x: i32, y: i32 }\ntest* = () i32 { P{ x: 19, y: 23 }.x + P{ x: 19, y: 23 }.y }", 42)


def test_comparison_not_mistaken_for_generic(tmp_path):
    # `a < b` in expression position must still parse as a comparison, not a generic literal
    run_value(tmp_path, "test* = () i32 { x := 5\n (x < 9).match({ true => 42, false => 0 }) }", 42)
