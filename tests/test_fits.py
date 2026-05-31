"""T1-T3: the pointer/null lattice — fits(given, want).

This is the entire safety argument of the project, so it gets the most cases.
"""
from holotype.ast import Dir, Prim, PrimT, NameT
from holotype.types import fits, dir_fits, is_option
from conftest import I32, VEC, ptr, option


# ── T1: direction lattice ───────────────────────────────────────────────────
def test_mutptr_fits_where_ptr_wanted():
    # MutPtr ≤ Ptr — a writable pointer can stand in for a read-only one.
    assert fits(ptr(VEC, Dir.MUT), ptr(VEC, Dir.READ))


def test_ptr_does_not_fit_where_mutptr_wanted():
    # direction locked: read-only cannot satisfy a mutate-required slot.
    assert not fits(ptr(VEC, Dir.READ), ptr(VEC, Dir.MUT))


def test_ptr_fits_ptr_and_mut_fits_mut():
    assert fits(ptr(VEC, Dir.READ), ptr(VEC, Dir.READ))
    assert fits(ptr(VEC, Dir.MUT), ptr(VEC, Dir.MUT))


def test_raw_only_fits_raw():
    # RAW is an isolated escape hatch — no silent coercion in either direction.
    assert fits(ptr(VEC, Dir.RAW), ptr(VEC, Dir.RAW))
    assert not fits(ptr(VEC, Dir.RAW), ptr(VEC, Dir.READ))
    assert not fits(ptr(VEC, Dir.READ), ptr(VEC, Dir.RAW))
    assert not fits(ptr(VEC, Dir.MUT), ptr(VEC, Dir.RAW))
    assert not fits(ptr(VEC, Dir.RAW), ptr(VEC, Dir.MUT))


def test_dir_fits_unit():
    assert dir_fits(Dir.MUT, Dir.READ)
    assert not dir_fits(Dir.READ, Dir.MUT)
    assert dir_fits(Dir.RAW, Dir.RAW)
    assert not dir_fits(Dir.RAW, Dir.READ)


# ── T2: nullability lattice ─────────────────────────────────────────────────
def test_nonnull_fits_option():
    # T ≤ Option<T> — a value that is never null is accepted where null is allowed.
    assert fits(ptr(VEC), option(ptr(VEC)))
    assert fits(I32, option(I32))


def test_option_does_not_fit_nonnull():
    # the null guard: Option<T> ⊀ T.
    assert not fits(option(ptr(VEC)), ptr(VEC))
    assert not fits(option(I32), I32)


def test_option_fits_option_when_inner_fits():
    assert fits(option(ptr(VEC, Dir.MUT)), option(ptr(VEC, Dir.READ)))
    assert not fits(option(ptr(VEC, Dir.READ)), option(ptr(VEC, Dir.MUT)))


def test_is_option_predicate():
    assert is_option(NameT("Option", (I32,)))
    assert not is_option(VEC)
    assert not is_option(I32)


# ── T3: pointee recursion + primitive equality ──────────────────────────────
def test_pointee_must_match():
    other = NameT("core.vec.Other", ())
    assert not fits(ptr(VEC), ptr(other))


def test_direction_and_pointee_both_checked():
    other = NameT("core.vec.Other", ())
    # right direction, wrong pointee → reject
    assert not fits(ptr(other, Dir.MUT), ptr(VEC, Dir.READ))


def test_primitive_equality():
    assert fits(I32, PrimT(Prim.I32))
    assert not fits(PrimT(Prim.BOOL), I32)
    assert not fits(PrimT(Prim.I64), I32)        # narrowing rejected


def test_i32_widens_to_i64():
    assert fits(I32, PrimT(Prim.I64))            # widening is value-preserving
    assert not fits(PrimT(Prim.I64), I32)        # but not the other way


def test_nominal_identity_by_path():
    # same path == same type; different path == different type (holotype principle).
    assert fits(NameT("a.b.C", ()), NameT("a.b.C", ()))
    assert not fits(NameT("a.b.C", ()), NameT("a.b.D", ()))


# ── variance: writable pointers are INVARIANT in their pointee ───────────────
def test_mutptr_pointee_is_invariant():
    # MutPtr<Vec> must NOT fit MutPtr<Option<Vec>>: the callee could write null
    # through it into a slot the caller guaranteed non-null (array-covariance hole).
    assert not fits(ptr(VEC, Dir.MUT), ptr(option(VEC), Dir.MUT))
    assert not fits(ptr(option(VEC), Dir.MUT), ptr(VEC, Dir.MUT))
    assert fits(ptr(VEC, Dir.MUT), ptr(VEC, Dir.MUT))        # equal pointee still fits


def test_readonly_pointee_stays_covariant():
    # downgrading to read-only is safe, so Ptr pointee may be covariant.
    assert fits(ptr(VEC, Dir.READ), ptr(option(VEC), Dir.READ))


def test_mutptr_downgraded_to_readonly_is_covariant():
    # MutPtr<Vec> -> Ptr<Option<Vec>>: target is read-only, so covariance is fine.
    assert fits(ptr(VEC, Dir.MUT), ptr(option(VEC), Dir.READ))


# ── algebraic laws of the subtyping relation (property tests) ───────────────
def _type_zoo():
    """A spread of types to check lattice laws over."""
    base = [I32, PrimT(Prim.I64), PrimT(Prim.BOOL), VEC, NameT("a.b.Other", ())]
    out = list(base)
    for t in base:
        out += [ptr(t, Dir.READ), ptr(t, Dir.MUT), ptr(t, Dir.RAW), option(t)]
    out += [option(ptr(VEC, Dir.MUT)), ptr(option(VEC), Dir.READ)]
    return out


def test_fits_is_reflexive():
    for t in _type_zoo():
        assert fits(t, t), f"reflexivity failed for {t}"


def test_fits_is_transitive():
    zoo = _type_zoo()
    for a in zoo:
        for b in zoo:
            if not fits(a, b):
                continue
            for c in zoo:
                if fits(b, c):
                    assert fits(a, c), f"transitivity: {a} ≤ {b} ≤ {c} but not {a} ≤ {c}"


def test_fits_is_antisymmetric():
    zoo = _type_zoo()
    for a in zoo:
        for b in zoo:
            if fits(a, b) and fits(b, a):
                assert a == b, f"antisymmetry: {a} ≤ {b} ≤ {a} but {a} != {b}"
