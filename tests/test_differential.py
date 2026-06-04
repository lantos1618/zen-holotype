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


# Reject-parity: programs the Python frontend rejects that the self-hosted checker must also reject
# (false-accepts that emit UB or wrong C). The self-hosted side must NOT accept these.
@pytest.mark.parametrize("src", [
    "test* = () i32 {  }",                         # empty body, non-void return -> no value (was accepted -> UB)
    "test* = () i32 {\n  x := 5\n}",               # body ends in a let -> no value (was accepted -> UB)
    "test* = () i32 {\n  x := 5\n  x = 6\n}",      # body ends in an assign -> no value
    'test* = () i32 { "hi" }',                     # trailing value is str, not i32
])
def test_self_hosted_rejects(src):
    from _difftest import self_side
    assert self_side(src)["verdict"] == "reject", src


# Integer/literal match `(n).match({ 0 => …, 1 => …, _ => … })` — lowers to an equality-cond chain.
# Was: 3+ arms crashed the parser, 2-arm non-zero labels were silently mis-evaluated.
@pytest.mark.parametrize("src,want", [
    ("test* = () i32 { (2).match({ 0 => 10, 1 => 11, 2 => 12, _ => 99 }) }", 12),   # 4 arms (was SIGSEGV)
    ("test* = () i32 { (1).match({ 0 => 10, 1 => 11, _ => 20 }) }", 11),            # 3 arms (was rejected)
    ("test* = () i32 { (1).match({ 1 => 100, _ => 200 }) }", 100),                  # 2-arm non-zero (was 200)
    ("test* = () i32 { (9).match({ 0 => 10, 1 => 11, _ => 20 }) }", 20),            # default arm
    ("test* = () i32 { (3).match({ 0=>0, 1=>10, 2=>20, 3=>30, _=>99 }) }", 30),     # 5 arms
])
def test_integer_match(src, want):
    from _difftest import self_side
    assert self_side(src)["value"] == want
