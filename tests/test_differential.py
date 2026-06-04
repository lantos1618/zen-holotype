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
    # NESTED block comments: the inner `*/` must NOT close the outer comment (was stopping early → 1)
    ("test* = () i32 {\n  1 + /* outer /* inner */ still-comment */ 41\n}", 42),
    ("test* = () i32 { 3 + /* plain */ 4 }", 7),
    # char literals must not desync the token stream — a malformed 'ab' used to corrupt the NEXT decl
    ("bad* = () i32 { 'ab' }\ntest* = () i32 { 5 }", 5),
    ("test* = () i32 { 'A' }", 65),
    # slice-literal STATEMENT must not glue onto the previous statement as an index (`x := 7` ⨯ `[1]`)
    ("test* = () i32 {\n  x := 7\n  [1]\n  x\n}", 7),
    ("test* = () i32 {\n  [9, 9]\n  1 + 2\n}", 3),
    # same-line indexing must still work (regression guard for the newline-aware fix)
    ("test* = () i32 {\n  s := [10, 20, 30]\n  s[2]\n}", 30),
    # generic CONSTRUCTOR called with a non-literal (Var) arg: T must be inferred from the local's
    # type (was → `Box_void` miscompile because light_ty couldn't type a Var without an env)
    ("Box<T>: { v: T }\nwrap<T> = (x: T) Box<T> { Box<T>{ v: x } }\nget<T> = (b: Box<T>) i32 { b.v }\ntest* = () i32 {\n  n := 5\n  get(wrap(n))\n}", 5),
    ("Box<T>: { v: T }\nwrap<T> = (x: T) Box<T> { Box<T>{ v: x } }\nget<T> = (b: Box<T>) i32 { b.v }\ntest* = () i32 {\n  n := 9\n  w := wrap(n)\n  get(w)\n}", 9),
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


# Member-target assignment `p.x = v` — was dropped entirely (the `= v` glued onto the next line),
# silently corrupting the return value. (Python's reference grammar lacks reassignment, so we assert
# the self-hosted value directly.)
@pytest.mark.parametrize("src,want", [
    # the write is a dead store; trailing 5 is returned (was miscompiled to 99)
    ("P*: { x: i32 }\nf* = (p: P) i32 {\n p.x = 99\n 5\n}\ntest* = () i32 { f(P{ x: 0 }) }", 5),
    # the write happens, then read it back
    ("P*: { x: i32 }\nf* = (p: P) i32 {\n p.x = 99\n p.x\n}\ntest* = () i32 { f(P{ x: 0 }) }", 99),
    # bare-variable reassignment still works (regression)
    ("test* = () i32 {\n x := 5\n x = 7\n x\n}", 7),
    # write through a Ptr receiver (auto-deref -> p->x)
    ("P*: { x: i32 }\nbump* = (p: Ptr<P>) i32 {\n p.x = 42\n p.x\n}\ntest* = () i32 { q := P{ x: 0 }\n bump(addr(q)) }", 42),
    # nested field write a.b.c = v
    ("I*: { n: i32 }\nO*: { i: I }\nf* = (o: O) i32 {\n o.i.n = 42\n o.i.n\n}\ntest* = () i32 { f(O{ i: I{ n: 0 } }) }", 42),
])
def test_member_assignment(src, want):
    from _difftest import self_side
    assert self_side(src)["value"] == want


# Large constructs (bug-hunt #15/#16): parser buffers were fixed at cap 64 (params/fields/arms/
# variants) and cap 16 (type args) and overflowed the heap with no bounds check. Caps are now
# generous (1024 / 256) so any plausible program fits safely.
def test_many_params():
    from _difftest import self_side
    ps = ", ".join(f"p{i}: i32" for i in range(80))
    args = ", ".join(str(i) for i in range(80))
    assert self_side(f"f* = ({ps}) i32 {{ p79 }}\ntest* = () i32 {{ f({args}) }}")["value"] == 79

def test_many_fields():
    from _difftest import self_side
    fs = ", ".join(f"x{i}: i32" for i in range(80))
    inits = ", ".join(f"x{i}: {i}" for i in range(80))
    assert self_side(f"S*: {{ {fs} }}\ntest* = () i32 {{ S{{ {inits} }}.x79 }}")["value"] == 79

def test_many_match_arms():
    from _difftest import self_side
    arms = ", ".join(f"{i} => {i*2}" for i in range(80)) + ", _ => 999"
    assert self_side(f"test* = () i32 {{ (50).match({{ {arms} }}) }}")["value"] == 100
