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
    # generic ENUMS (Opt<T>) — monomorphized by use like generic structs. Values + matching across
    # the realistic patterns: direct ctor, let-bound, producer (Some/None/conditional), consumer.
    ("Opt<T>: Some(T) | None\ntest* = () i32 { (.Some(5)).match({ .Some(x) => x, .None => 0 }) }", 5),
    ("Opt<T>: Some(T) | None\ntest* = () i32 {\n  o := .Some(7)\n  o.match({ .Some(x) => x, .None => 0 })\n}", 7),
    ("Opt<T>: Some(T) | None\nmk<T> = (x: T) Opt<T> { .Some(x) }\ntest* = () i32 { mk(8).match({ .Some(x) => x, .None => 0 }) }", 8),
    ("Opt<T>: Some(T) | None\none<T> = (x: T) Opt<T> { .None }\ntest* = () i32 { one(5).match({ .Some(x) => x, .None => 3 }) }", 3),
    ("Opt<T>: Some(T) | None\npick<T> = (x: T, b: i32) Opt<T> { (b == 1).match({ true => .Some(x), false => .None }) }\ntest* = () i32 { pick(9, 0).match({ .Some(x) => x, .None => 3 }) }", 3),
    ("Opt<T>: Some(T) | None\nunwrap<T> = (o: Opt<T>, d: T) T { o.match({ .Some(x) => x, .None => d }) }\ntest* = () i32 {\n  o := .Some(7)\n  unwrap(o, 0)\n}", 7),
    # a generic fn's tparam inferred from a SLICE-LITERAL argument (`[T]` param vs `[i32]` arg → T=i32);
    # without it light_ty returned void → a `void`-element miscompile
    ("first<T> = (xs: [T]) T { xs[0] }\ntest* = () i32 { first([7, 8]) }", 7),
    ("pick2<T> = (xs: [T], a: T) T { xs[1] + a }\ntest* = () i32 { pick2([3, 4], 5) }", 9),
    # a generic CALL's return type is inferred + substituted, so a let bound to it (and a downstream
    # generic call on it) carries the concrete instance — `mk(...)` returns Box<i32>, not the leaked Box<T>
    ("Box<T>: { v: T }\nmk<T> = (x: T) Box<T> { Box<T>{ v: x } }\nget<T> = (b: Box<T>) T { b.v }\ntest* = () i32 {\n  b := mk(42)\n  b.get()\n}", 42),
    # a generic container round-trip (the Vec<T> substrate): build from a slice, read back through a
    # second generic call — exercises generic-call return inference + element-type preservation on inline
    ("Vec<T>: { ptr: RawPtr<u8>, len: i64, cap: i64 }\nmalloc = (n: i64) RawPtr<u8>\nbuf<T> = (v: Vec<T>) [T] { slice(v.ptr, v.cap) }\nget<T> = (v: Vec<T>, i: i64) T { v.buf()[i] }\nof<T> = (xs: [T]) Vec<T> {\n  v := Vec<T>{ ptr: malloc(xs.len * sizeof(T)), len: xs.len, cap: xs.len }\n  b := v.buf()\n  xs.loop((h, i, x) { b[i] = x })\n  v\n}\ntest* = () i32 {\n  v := of([10, 20, 30])\n  v.get(0) + v.get(2)\n}", 40),
    # bug-hunt #11: a bare ctor passed DIRECTLY as a generic-consumer arg (T inferred from the payload)
    ("Opt<T>: Some(T) | None\nu<T> = (o: Opt<T>) i32 { o.match({ .Some(x) => 1, .None => 0 }) }\ntest* = () i32 { u(.Some(42)) }", 1),
    ("Opt<T>: Some(T) | None\nunwrap<T> = (o: Opt<T>, d: T) T { o.match({ .Some(x) => x, .None => d }) }\ntest* = () i32 { unwrap(.Some(7), 0) }", 7),
    # MULTI-IMPLEMENTOR traits (#5-full): two types implementing the same trait method now emit
    # DISTINCT C functions (impl_<Trait>_<Type>_<m>) and `x.m()` dispatches on x's type — previously
    # both emitted `int32_t area(...)` and cc rejected with "conflicting types".
    ("A*: { v: i32 }\nB*: { v: i32 }\nShow*: { area: (Ptr<Self>) i32 }\nA.impl(Show, { area = (a: Ptr<A>) i32 { a.v } })\nB.impl(Show, { area = (b: Ptr<B>) i32 { b.v * b.v } })\ntest* = () i32 {\n  a := A { v: 5 }\n  b := B { v: 6 }\n  addr(a).area() + addr(b).area()\n}", 41),
    # a single trait method with two implementors taking an extra arg, both reached + dispatched
    ("P*: { x: i32 }\nQ*: { x: i32 }\nDbl*: { f: (Ptr<Self>, i32) i32 }\nP.impl(Dbl, { f = (p: Ptr<P>, k: i32) i32 { p.x + k } })\nQ.impl(Dbl, { f = (q: Ptr<Q>, k: i32) i32 { q.x * k } })\ntest* = () i32 {\n  p := P { x: 10 }\n  q := Q { x: 3 }\n  addr(p).f(2) + addr(q).f(4)\n}", 24),
    # MODULE-LEVEL MUTABLE GLOBALS (Goal Z E1): `counter := 0` emits `static int32_t counter = 0;`
    # and a function reads/assigns it across calls (state persists). Was: mis-parsed as an enum.
    ("counter := 0\nbump* = () i32 { counter = counter + 1  counter }\ntest* = () i32 { bump() + bump() }", 3),
    ("total := 100\nadd* = (n: i32) i32 { total = total + n  total }\ntest* = () i32 { add(5)  add(20) }", 125),
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


# Early `return <value>` + guard / partial matches. A match used as a STATEMENT (its value
# discarded) lowers to `if` STATEMENTS so an arm's `return` actually leaves the function; a terminal
# bare `_` (≡ `_ => {}`) closes a partial match with a void no-op. A VALUE-position match stays the
# exhaustive ternary. Exhaustiveness is still enforced — a partial match WITHOUT `_` is rejected.
@pytest.mark.parametrize("src,want", [
    # bool guard: f(false) takes the `return 9`; f(true) falls through to the trailing 7
    ("f* = (b: bool) i32 {\n b.match({ false => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(false) }", 9),
    ("f* = (b: bool) i32 {\n b.match({ false => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(true) }", 7),
    ("f* = (b: bool) i32 {\n b.match({ true => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(true) }", 9),
    # enum error-guard: an early return out of one variant, the rest a no-op `_`
    ("R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(.Err()) }", 9),
    ("R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 }, _ })\n 7\n}\ntest* = () i32 { f(.Ok(0)) }", 7),
    # enum guard binding the payload: `.Err(e) => { return e }`
    ("R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n r.match({ .Err(e) => { return e }, _ })\n 7\n}\ntest* = () i32 { f(.Err(42)) }", 42),
    # an early `return` mid-body (not inside a match) via an if-statement
    ("f* = (b: bool) i32 {\n if (b) { return 9 }\n 7\n}\ntest* = () i32 { f(true) }", 9),
    ("f* = (b: bool) i32 {\n if (b) { return 9 }\n 7\n}\ntest* = () i32 { f(false) }", 7),
    # literal guard if-chain with assigns + terminal bare `_`
    ("f* = (n: i32) i32 {\n x := 0\n n.match({ 0 => { x = 1 }, 1 => { x = 2 }, _ })\n x\n}\ntest* = () i32 { f(0)*100 + f(1)*10 + f(9) }", 120),
    # a FULLY EXHAUSTIVE statement-position enum match (no `_`) with returns still lowers + works
    ("R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Ok(v) => { return v }, .Err => { return 9 } })\n 0\n}\ntest* = () i32 { f(.Ok(5)) + f(.Err()) }", 14),
])
def test_guard_early_return(src, want):
    from _difftest import self_side
    assert self_side(src)["value"] == want, src


# Exhaustiveness stays enforced: a partial STATEMENT match WITHOUT a terminal `_` must be rejected
# (no implicit fall-through). The `_` is what licenses a subset of cases.
@pytest.mark.parametrize("src", [
    # partial enum match, no `_` — missing .Ok
    "R*: Ok(i32) | Err\nf* = (r: R) i32 {\n r.match({ .Err => { return 9 } })\n 7\n}\ntest* = () i32 { f(.Ok(0)) }",
    # partial bool match, no `_` — only the false arm
    "f* = (b: bool) i32 {\n b.match({ false => { return 9 } })\n 7\n}\ntest* = () i32 { f(false) }",
])
def test_partial_match_without_wildcard_rejected(src):
    from _difftest import self_side
    assert self_side(src)["verdict"] == "reject", src


# A VALUE-position match arm with an early `return` is rejected. A value-position match lowers to a
# `({…})`/ternary, where the emitter turns a trailing `return e` into a bare `e;` — the return is
# silently dropped (wrong value). Guard returns must be STATEMENT-position (those lower to real `if`,
# tested above). So reject value-position returns, matching the Python frontend. (C-audit #7.)
@pytest.mark.parametrize("src", [
    "R*: Ok(i32) | Err(i32)\nf* = (r: R) i32 {\n v := r.match({ .Ok(x) => { return x }, .Err(e) => e })\n v + 1\n}\ntest* = () i32 { f(.Ok(5)) }",
    "f* = (b: bool) i32 {\n v := b.match({ true => { return 7 }, false => 0 })\n v\n}\ntest* = () i32 { f(true) }",
])
def test_value_position_return_rejected(src):
    from _difftest import self_side
    assert self_side(src)["verdict"] == "reject", src


# Two top-level decls with the same FUNCTION name emit colliding C definitions (cc "redefinition" /
# "conflicting types"). The self-hosted backend doesn't mangle plain fn names, so the checker must
# reject a duplicate, matching the Python frontend's Namespace Conflict. Zen has no overloading. (#5.)
@pytest.mark.parametrize("src", [
    "foo* = () i32 { 1 }\nfoo* = () i32 { 2 }\ntest* = () i32 { foo() }",
    "a* = () i32 { 1 }\ndup* = () i32 { 2 }\ndup* = () i32 { 3 }\ntest* = () i32 { a() }",
])
def test_duplicate_function_name_rejected(src):
    from _difftest import self_side
    assert self_side(src)["verdict"] == "reject", src
