"""T4-T5: expression inference and its failure paths.

infer() returns the type of an expression and raises TypeErr at any call/field
mismatch — it's where fits() actually gets triggered on real programs.
"""
import pytest

from holotype.ast import (Dir, Prim, PrimT, Lit, Var, Bin, Field, Call,
                          StructLit)
from holotype.types import infer, TypeErr
from conftest import I32, VEC, ptr, option


def locals_with_v(d=Dir.READ):
    return {"v": ptr(VEC, d)}


# ── T4: the happy paths ─────────────────────────────────────────────────────
def test_literal_is_i32(space, scope):
    assert infer(Lit(7), {}, space, scope) == I32


def test_var_returns_its_local_type(space, scope):
    assert infer(Var("v"), locals_with_v(), space, scope) == ptr(VEC)


def test_binary_is_i32(space, scope):
    assert infer(Bin("*", Lit(3), Lit(4)), {}, space, scope) == I32


def test_field_autoderefs_through_pointer(space, scope):
    # v : Ptr<Vec>, v.len reaches through the pointer to the struct field.
    assert infer(Field(Var("v"), "len"), locals_with_v(), space, scope) == I32


def test_call_returns_fn_ret_type(space, scope):
    e = Call("len", (Var("v"),))
    assert infer(e, locals_with_v(), space, scope) == I32


def test_addr_yields_mutptr(space, scope):
    # addr(x) takes the most capable pointer; MutPtr then fits anywhere Ptr is asked.
    e = Call("addr", (StructLit("Vec", (("len", Lit(3)), ("cap", Lit(4)))),))
    t = infer(e, {}, space, scope)
    assert t == ptr(VEC, Dir.MUT)


def test_structlit_typechecks_fields(space, scope):
    e = StructLit("Vec", (("len", Lit(3)), ("cap", Lit(4))))
    assert infer(e, {}, space, scope) == VEC


def test_mutptr_arg_fits_ptr_param(space, scope):
    # ops.len wants Ptr<Vec>; passing a MutPtr<Vec> is allowed (MutPtr ≤ Ptr).
    assert infer(Call("len", (Var("v"),)), locals_with_v(Dir.MUT), space, scope) == I32


# ── T5: the failure paths ───────────────────────────────────────────────────
def test_unbound_var_raises(space, scope):
    with pytest.raises(TypeErr):
        infer(Var("nope"), {}, space, scope)


def test_call_arity_mismatch_raises(space, scope):
    with pytest.raises(TypeErr):
        infer(Call("len", ()), locals_with_v(), space, scope)


def test_readonly_into_mut_param_raises(space, scope):
    # ops.bump wants MutPtr<Vec>; passing a read-only Ptr must be rejected.
    e = Call("bump", (Var("v"),))
    with pytest.raises(TypeErr) as ei:
        infer(e, locals_with_v(Dir.READ), space, scope)
    assert ei.value.given == ptr(VEC, Dir.READ)
    assert ei.value.want == ptr(VEC, Dir.MUT)


def test_nullable_into_nonnull_param_raises(space, scope):
    e = Call("len", (Var("v"),))
    with pytest.raises(TypeErr):
        infer(e, {"v": option(ptr(VEC))}, space, scope)


def test_unknown_field_raises(space, scope):
    with pytest.raises(TypeErr):
        infer(Field(Var("v"), "missing"), locals_with_v(), space, scope)


def test_field_on_non_struct_raises(space, scope):
    with pytest.raises(TypeErr):
        infer(Field(Lit(1), "len"), {}, space, scope)


def test_structlit_unknown_field_raises(space, scope):
    with pytest.raises(TypeErr):
        infer(StructLit("Vec", (("bogus", Lit(1)),)), {}, space, scope)
