"""Phase 4 — impl blocks (and pointer field auto-deref), through the self-hosted toolchain.

`Type.impl(Trait, { m = (s: Ptr<Type>, …) R { … } })` — the methods become ordinary top-level
functions named by the method, so a UFCS call `x.m(a)` (which the parser desugars to `m(x, a)`)
resolves to one. A method's `s.field` on a `Ptr<Type>` receiver auto-derefs to `s->field`.
"""
import pytest

from _selfhost import run_value, check_errors


@pytest.mark.parametrize("prog,want", [
    # one impl method, called via UFCS; field access on the Ptr receiver auto-derefs
    ("Point*: { x: i32, y: i32 }\n"
     "Point.impl(Show, { sumk = (p: Ptr<Point>, k: i32) i32 { p.x + p.y + k } })\n"
     "test* = () i32 { p := Point { x: 3, y: 4 }\n p.addr().sumk(10) }", 17),
    # two methods in one impl block
    ("Counter*: { n: i32 }\n"
     "Counter.impl(Inc, { bump = (c: Ptr<Counter>) i32 { c.n + 1 }  get = (c: Ptr<Counter>) i32 { c.n } })\n"
     "test* = () i32 { c := Counter { n: 41 }\n c.addr().bump() }", 42),
    # an impl method that chains another UFCS call
    ("Box*: { v: i32 }\n"
     "Box.impl(B, { val = (b: Ptr<Box>) i32 { b.v }  twice = (b: Ptr<Box>) i32 { b.val() + b.val() } })\n"
     "test* = () i32 { b := Box { v: 21 }\n b.addr().twice() }", 42),
])
def test_impl_method_runs(tmp_path, prog, want):
    run_value(tmp_path, prog, want)


@pytest.mark.parametrize("prog,want", [
    # a DECLARED trait (`Show*: { render: (Ptr<Self>) R }`) — parses but is skipped from codegen
    # (no runtime form); the impl provides the method, called via UFCS.
    ("Show*: { render: (Ptr<Self>) i32 }\n"
     "Point*: { x: i32, y: i32 }\n"
     "Point.impl(Show, { render = (p: Ptr<Point>) i32 { p.x * 10 + p.y } })\n"
     "test* = () i32 { p := Point { x: 4, y: 2 }\n p.addr().render() }", 42),
])
def test_declared_trait_with_impl_runs(tmp_path, prog, want):
    run_value(tmp_path, prog, want)


# Trait conformance: an impl must DEFINE every method its trait declares. The check is tied to the
# impl's OWN methods (recorded in DImpl), not a global function search — so an unrelated same-named
# function elsewhere does NOT make a deficient impl conform.
def test_conformance_accepts_complete_impl(tmp_path):
    assert check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>) i32, area: (Ptr<Self>) i32 }\nPoint*: { x: i32 }\n"
        "Point.impl(Show, { render = (p: Ptr<Point>) i32 { p.x }  area = (p: Ptr<Point>) i32 { p.x } })") == 0


def test_conformance_rejects_missing_method(tmp_path):
    assert check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>) i32, area: (Ptr<Self>) i32 }\nPoint*: { x: i32 }\n"
        "Point.impl(Show, { render = (p: Ptr<Point>) i32 { p.x } })") == 1


def test_conformance_unrelated_global_does_not_satisfy(tmp_path):
    # a top-level `area` exists, but Point's impl doesn't DEFINE area -> still non-conforming
    assert check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>) i32, area: (Ptr<Self>) i32 }\nPoint*: { x: i32 }\n"
        "area* = (n: i32) i32 { n }\n"
        "Point.impl(Show, { render = (p: Ptr<Point>) i32 { p.x } })") == 1


# Signature conformance (Goal Arc 2): an impl method must match the trait's declared signature, with
# `Self` read as the implementing type — not just exist by name. Verdicts match the Python frontend
# ("signature does not match the trait").
def test_conformance_accepts_matching_signature(tmp_path):
    # Self -> Point: the impl's `Ptr<Point>` matches the trait's `Ptr<Self>`, ret i32 == i32.
    # (an FnT param list is bare TYPES: `(Ptr<Self>, i32)`; the impl's params may be named.)
    assert check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>, i32) i32 }\nPoint*: { x: i32 }\n"
        "Point.impl(Show, { render = (p: Ptr<Point>, k: i32) i32 { p.x + k } })") == 0


def test_conformance_rejects_arity_mismatch(tmp_path):
    # trait declares one param (the Self receiver); impl takes an extra -> non-conforming
    assert check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>) i32 }\nPoint*: { x: i32 }\n"
        "Point.impl(Show, { render = (p: Ptr<Point>, k: i32) i32 { p.x } })") == 1


def test_conformance_rejects_return_mismatch(tmp_path):
    # trait declares ret i32; impl returns bool -> non-conforming
    assert check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>) i32 }\nPoint*: { x: i32 }\n"
        "Point.impl(Show, { render = (p: Ptr<Point>) bool { p.x < 1 } })") == 1


def test_conformance_rejects_param_type_mismatch(tmp_path):
    # trait declares the second param i32; impl takes u8 -> non-conforming (not the Self param)
    assert check_errors(tmp_path,
        "Show*: { render: (Ptr<Self>, i32) i32 }\nPoint*: { x: i32 }\n"
        "Point.impl(Show, { render = (p: Ptr<Point>, k: u8) i32 { p.x } })") == 1
