"""Inspect the C the self-hosted toolchain emits and assert it's clean — not just that it
compiles + runs, but that it has no known smells. (Reviewing the emitted C is how the
void-deref and the un-monomorphized `T`-leak bugs were first caught; this guards against
their return.) Each smell below was a real bug or wart at some point.
"""
import tempfile
from pathlib import Path

from _selfhost import emit_c_for

# feature-heavy programs whose emitted C exercises the inline/monomorphize machinery
_PROGRAMS = [
    "apply* = (f: (i32) i32, x: i32) i32 { f(x) }\ntest* = () i32 { apply((n) { n + 1 }, 5) }",
    "fold*<T> = (xs: [T], init: T, f: (T, T) T) T {\n acc := init\n xs.loop((h, i, x) { acc = f(acc, x) })\n acc\n}\n"
    "test* = () i32 { fold([3, 4, 5], 0, (a, x) { a + x }) }",
    "Counter*: { n: i32 }\nCounter.impl(Inc) { bump = (c: Ptr<Counter>) i32 { c.n + 1 } }\n"
    "test* = () i32 { c := Counter { n: 41 }\n c.addr().bump() }",
]


def _emit_all():
    with tempfile.TemporaryDirectory() as td:
        return [emit_c_for(Path(td), p) for p in _PROGRAMS]


def test_no_void_pointer_deref():
    # a `void*` (heap's result) dereferenced directly — the old byte-store bug
    for c in _emit_all():
        assert "*((void*)" not in c, c


def test_no_leaked_lambda_stub():
    # gen_expr's Lambda arm emits a bare `0` — it must NEVER reach codegen (lambdas are inlined)
    for c in _emit_all():
        assert "/*lambda*/" not in c and "lambda" not in c, c


def test_no_unmonomorphized_type_param_cast():
    # a generic `<T>` that leaked into codegen as `(T*)` instead of the concrete element type
    for c in _emit_all():
        for bad in ("(T*)", "(T)", "(A*)", "struct T ", "struct A "):
            assert bad not in c, f"{bad!r} in {c}"


def test_single_expr_lambda_not_double_wrapped():
    # `f(acc, x)` where the lambda is `(a, x) { a + x }` must inline to `acc = (acc + x);`,
    # NOT the redundant `acc = ({ (acc + x); });` statement-expression wrapper.
    with tempfile.TemporaryDirectory() as td:
        c = emit_c_for(Path(td), _PROGRAMS[1])
    assert "acc = (acc + x);" in c, c
    assert "({ (acc + x); })" not in c, c
