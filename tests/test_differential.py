"""Differential regression tests — guard against bugs found by the bug-hunt (the self-hosted
toolchain miscompiling or mis-checking vs the Python reference). Each entry is a minimal program
that previously diverged; we assert the self-hosted side now computes the right value / verdict.

`self_side(src)` runs the program through the self-hosted toolchain and returns
{verdict: accept|reject, value: int|None}. The Python reference (`py_side`) is a useful oracle but
its grammar lags on a few constructs (hex literals, prefix `-`, `!=`), so for those we assert the
self-hosted *value* directly rather than cross-frontend agreement.
"""
import pytest

from _difftest import self_side, compare


# Value-correctness: the self-hosted toolchain must compute these exactly (silent-miscompile guards).
@pytest.mark.parametrize("src,want", [
    # i64 integer literals (were truncated through an i32 accumulator / gen_int)
    ("test* = () i64 { 10000000000 / 10 }", 1000000000),     # was 141006540
    ("test* = () i64 { 9999999999 - 9999999990 }", 9),
    ("test* = () i64 { 5000000000 + 5000000000 }", 10000000000),
])
def test_self_hosted_computes_value(src, want):
    assert self_side(src)["value"] == want


# Cross-frontend agreement on a corpus where the Python reference is a valid oracle (no hex / prefix
# `-` / `!=`, which its grammar lacks). Catches accept/reject and value divergences broadly.
@pytest.mark.parametrize("src", [
    "test* = () i32 { 1 + 2 * 3 - 4 }",
    "test* = () i32 { (17 / 5) + (17 % 5) }",
    "test* = () i32 { (3 < 5).match({ true => 7, false => 0 }) }",
    "fib* = (n: i32) i32 { (n < 2).match({ true => n, false => fib(n - 1) + fib(n - 2) }) }\ntest* = () i32 { fib(12) }",
    "P*: { x: i32, y: i32 }\ntest* = () i32 { P{ x: 19, y: 23 }.x + P{ x: 19, y: 23 }.y }",
    "E*: A(i32) | B(i32)\nf* = (e: E) i32 { e.match({ .A(x) => x, .B(x) => x * x }) }\ntest* = () i32 { f(.B(6)) + f(.A(6)) }",
    "Box<T>: { v: T }\nget<T> = (b: Box<T>) i32 { b.v }\ntest* = () i32 { get(Box<i32>{ v: 42 }) }",
])
def test_no_divergence(src):
    d = compare(src)
    assert not d["verdict_div"], d["summary"]
    assert not d["value_div"], d["summary"]
