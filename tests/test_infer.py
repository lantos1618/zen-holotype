"""T4-T5: expression inference and its failure paths.

infer() returns the type of an expression and raises TypeErr at any call/field
mismatch — it's where fits() actually gets triggered on real programs.
"""
import pytest

from zen.ast import Dir, Lit, Var, Bin, Field, Call, StructLit
from zen.types import infer, TypeErr
from conftest import I32, VEC, ptr, option


def locals_with_v(d=Dir.READ):
    return {"v": ptr(VEC, d)}


# ── T4: the happy paths ─────────────────────────────────────────────────────
def test_literal_is_i32(namespace, scope):
    assert infer(Lit(7), {}, namespace, scope) == I32


def test_var_returns_its_local_type(namespace, scope):
    assert infer(Var("v"), locals_with_v(), namespace, scope) == ptr(VEC)


def test_binary_is_i32(namespace, scope):
    assert infer(Bin("*", Lit(3), Lit(4)), {}, namespace, scope) == I32


def test_field_autoderefs_through_pointer(namespace, scope):
    # v : Ptr<Vec>, v.len reaches through the pointer to the struct field.
    assert infer(Field(Var("v"), "len"), locals_with_v(), namespace, scope) == I32


def test_call_returns_fn_ret_type(namespace, scope):
    e = Call("len", (Var("v"),))
    assert infer(e, locals_with_v(), namespace, scope) == I32


def test_addr_yields_mutptr(namespace, scope):
    # addr(x) takes the most capable pointer; MutPtr then fits anywhere Ptr is asked.
    e = Call("addr", (StructLit("Vec", (("len", Lit(3)), ("cap", Lit(4)))),))
    t = infer(e, {}, namespace, scope)
    assert t == ptr(VEC, Dir.MUT)


def test_structlit_typechecks_fields(namespace, scope):
    e = StructLit("Vec", (("len", Lit(3)), ("cap", Lit(4))))
    assert infer(e, {}, namespace, scope) == VEC


def test_mutptr_arg_fits_ptr_param(namespace, scope):
    # ops.len wants Ptr<Vec>; passing a MutPtr<Vec> is allowed (MutPtr ≤ Ptr).
    assert infer(Call("len", (Var("v"),)), locals_with_v(Dir.MUT), namespace, scope) == I32


# ── T5: the failure paths ───────────────────────────────────────────────────
def test_unbound_var_raises(namespace, scope):
    with pytest.raises(TypeErr):
        infer(Var("nope"), {}, namespace, scope)


def test_call_arity_mismatch_raises(namespace, scope):
    with pytest.raises(TypeErr):
        infer(Call("len", ()), locals_with_v(), namespace, scope)


def test_readonly_into_mut_param_raises(namespace, scope):
    # ops.bump wants MutPtr<Vec>; passing a read-only Ptr must be rejected.
    e = Call("bump", (Var("v"),))
    with pytest.raises(TypeErr) as ei:
        infer(e, locals_with_v(Dir.READ), namespace, scope)
    assert ei.value.given == ptr(VEC, Dir.READ)
    assert ei.value.want == ptr(VEC, Dir.MUT)


def test_nullable_into_nonnull_param_raises(namespace, scope):
    e = Call("len", (Var("v"),))
    with pytest.raises(TypeErr):
        infer(e, {"v": option(ptr(VEC))}, namespace, scope)


def test_unknown_field_raises(namespace, scope):
    with pytest.raises(TypeErr):
        infer(Field(Var("v"), "missing"), locals_with_v(), namespace, scope)


def test_field_on_non_struct_raises(namespace, scope):
    with pytest.raises(TypeErr):
        infer(Field(Lit(1), "len"), {}, namespace, scope)


def test_structlit_unknown_field_raises(namespace, scope):
    with pytest.raises(TypeErr):
        infer(StructLit("Vec", (("bogus", Lit(1)),)), {}, namespace, scope)


# ── robustness: a builtin/non-enum used as an enum is a clean error, not a crash ─
def _check_program(tmp_path, src):
    """Run the front-end + checker over a program; return the (qual, ok, why) results.
    The point is that ill-formed enum use is *reported*, never an uncaught crash."""
    from zen.main import (load, build_namespace, build_scopes, resolve,
                          fold_comptime, run_emits, check)
    (tmp_path / "main.zen").write_text(src)
    files = load(tmp_path)
    ns = build_namespace(files)
    build_scopes(files); resolve(files, ns); fold_comptime(files, ns); run_emits(files, ns)
    results, _ = check(files, ns)
    return results


def test_constructing_option_is_a_clean_error_not_a_crash(tmp_path):
    # Option is a builtin coercion target (nullable pointers), not a constructible
    # enum — `.None()` against it must report, not raise Unresolved.
    results = _check_program(tmp_path,
        "find* = (n: i32) Option<i32> { (n > 0).match { true => n, false => .None() } }")
    assert any(q == "main.find" and not ok and "not a constructible enum" in why
               for q, ok, why in results)


def test_matching_on_option_is_a_clean_error_not_a_crash(tmp_path):
    results = _check_program(tmp_path,
        "g* = (o: Option<i32>) i32 { o.match { .Some(v) => v, .None => 0 } }")
    assert any(q == "main.g" and not ok and "non-enum" in why for q, ok, why in results)
