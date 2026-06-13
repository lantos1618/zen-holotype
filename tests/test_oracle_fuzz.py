"""Property/fuzz coverage for the CHECK + CHECK-KIND binaries (Diagnostics arc, BONUS).

Cheap coverage-widening over the golden corpus: synthesize SIMPLE malformed programs from templates
that each have a KNOWN defect, and assert the self-hosted checker REJECTS them — crash-free, with a
nonzero error count AND a classified KIND. The point is not to re-prove a specific case (the golden
corpus does that) but to fuzz MANY shapes through the validator and catch a crash / silent-accept
regression on inputs the curated corpus doesn't enumerate. NO Python frontend — only the committed
`zenc` binary + cc, exactly like the rest of the oracle.

Each generator produces (src, expected_kind_or_None): when the defect pins a single deterministic kind
we assert it; when a template can produce several plausible first-errors we only require reject+kind.
Every src is run through BOTH binaries; the run must not crash (returncode is the count/kind, never a
signal) and must report an error.
"""
import random

import pytest

import _oracle
from _oracle import check_count, check_kind, verdict_kind, emit_rc


# ── malformed-program generators: each returns a list of (src, kind|None) ──────────────────────────
def _arity_calls():
    """A local fn called with the wrong number of args -> 'arity'."""
    out = []
    for nparams in (0, 1, 2, 3):
        ps = ", ".join("p%d: i32" % i for i in range(nparams))
        body = "0" if nparams == 0 else "p0"
        fn = "f* = (%s) i32 { %s }\n" % (ps, body)
        for nargs in range(0, 5):
            if nargs == nparams:
                continue  # the correct arity would ACCEPT — skip
            args = ", ".join("1" for _ in range(nargs))
            out.append((fn + "test* = () i32 { f(%s) }" % args, "arity"))
    return out


def _undefined_calls():
    """A call to a name with no decl/intrinsic/import -> 'undefined-name'."""
    out = []
    for nm in ("ghost", "missing", "nope", "zzz", "qq42"):
        out.append(("test* = () i32 { %s() }" % nm, "undefined-name"))
        out.append(("test* = () i32 { 1 + %s() }" % nm, "undefined-name"))      # nested in an operand
        out.append(("use* = (n: i32) i32 { n }\ntest* = () i32 { use(%s()) }" % nm, "undefined-name"))  # nested in an arg
    return out


def _struct_field_lits():
    """A struct literal naming a field the struct doesn't have -> 'struct-field'."""
    out = []
    for bad in ("y", "z", "w", "nope", "k0"):
        out.append(("P*: { x: i32 }\ntest* = () i32 { p := P(%s: 0)  0 }" % bad, "struct-field"))
        out.append(("P*: { x: i32 }\ntest* = () i32 { p := P(x: 0, %s: 1)  p.x }" % bad, "struct-field"))
    return out


def _member_access():
    """A member access on a known struct naming no real field -> 'struct-field'."""
    out = []
    for bad in ("nope", "bad", "qq", "zz"):
        out.append(("P*: { x: i32 }\ntest* = () i32 { p := P(x: 5)  p.%s }" % bad, "struct-field"))
    return out


def _exhaustiveness():
    """A non-wildcard enum match missing a variant -> 'exhaustiveness'."""
    out = []
    # C with N variants, match only the first one (and nothing else) -> non-exhaustive
    for n in (2, 3, 4):
        names = ["V%d" % i for i in range(n)]
        decl = "C*: " + " | ".join(names) + "\n"
        arms = ", ".join(".%s => %d" % (names[0], 0) for _ in [0])  # only the first variant
        fn = "f* = (c: C) i32 { c.match({ %s }) }\n" % arms
        out.append((decl + fn + "test* = () i32 { f(.%s()) }" % names[0], "exhaustiveness"))
    return out


def _dup_variant():
    """A match arm repeating a variant -> 'dup-variant'."""
    out = []
    for n in (2, 3):
        names = ["V%d" % i for i in range(n)]
        decl = "C*: " + " | ".join(names) + "\n"
        # cover all variants but DUPLICATE the first -> exhaustive yet dup
        arms = ".%s => 0, " % names[0] + ", ".join(".%s => %d" % (nm, i + 1) for i, nm in enumerate(names))
        fn = "f* = (c: C) i32 { c.match({ %s }) }\n" % arms
        out.append((decl + fn + "test* = () i32 { f(.%s()) }" % names[0], "dup-variant"))
    return out


def _operand_type():
    """An arithmetic op on non-numeric operands -> 'operand-type'."""
    out = []
    out.append(('test* = () i32 { ("a" + "b")  0 }', "operand-type"))
    out.append(('test* = () i32 { ("a" - "b")  0 }', "operand-type"))
    out.append(("test* = () bool { 1 && 2 }", "operand-type"))
    out.append(("test* = () bool { 0 || 1 }", "operand-type"))
    out.append(("P*: { x: i32 }\ntest* = () i32 { a := P(x: 1)  b := P(x: 2)  (a + b).x }", "operand-type"))
    return out


def _index_type():
    """seq[idx] with a non-slice seq -> 'index'."""
    out = []
    out.append(("test* = () i32 { x := 5  x[0] }", "index"))
    out.append(("test* = () i32 { x := 7  y := 1  x[y] }", "index"))
    out.append(("P*: { x: i32 }\ntest* = () i32 { s := [1, 2]  p := P(x: 0)  s[p] }", "index"))
    return out


def _return_fit():
    """A trailing value of the wrong category / a body that produces no value -> 'return-fit'."""
    out = []
    out.append(("test* = () i32 {  }", "return-fit"))                # empty
    out.append(("test* = () i32 { x := 5 }", "return-fit"))          # trailing let
    out.append(('test* = () i32 { "s" }', "return-fit"))             # str ⊀ i32
    out.append(("test* = () bool { 5 }", "return-fit"))              # numeric ⊀ bool
    out.append(("test* = () i32 { 1 < 2 }", "return-fit"))           # bool ⊀ i32
    out.append(("P*: { x: i32 }\ntest* = () i32 { P(x: 5) }", "return-fit"))  # struct ⊀ i32
    return out


def _dup_fn():
    """Two top-level fns sharing a name -> 'dup-fn'."""
    out = []
    out.append(("foo* = () i32 { 1 }\nfoo* = () i32 { 2 }\ntest* = () i32 { foo() }", "dup-fn"))
    out.append(("g* = (a: i32) i32 { a }\ng* = (a: i32, b: i32) i32 { a }\ntest* = () i32 { g(1) }", "dup-fn"))
    return out


_GENERATORS = [
    _arity_calls, _undefined_calls, _struct_field_lits, _member_access,
    _exhaustiveness, _dup_variant, _operand_type, _index_type, _return_fit, _dup_fn,
]


def _all_cases():
    cases = []
    for g in _GENERATORS:
        cases.extend(g())
    return cases


_CASES = _all_cases()


@pytest.mark.parametrize("src,kind", _CASES)
def test_fuzz_malformed_rejects(src, kind):
    # The synthesized malformed program must REJECT — crash-free (the exit code is the error count, a
    # small non-negative int, never a signal/segfault), with a nonzero count AND a classified KIND
    # that matches the template's known defect.
    cnt = check_count(src)
    assert 0 < cnt < 100, (src, cnt)              # rejects, and didn't blow up into a garbage count
    kd = check_kind(src)
    assert 1 <= kd <= 13, (src, kd)               # a real kind code (crash-free CHECK-KIND)
    if kind is not None:
        assert verdict_kind(src) == kind, (src, verdict_kind(src))


def test_fuzz_corpus_is_broad():
    # Sanity: the generators actually produce a meaningful spread (catches a generator that silently
    # produces nothing), and every distinct defect KIND the templates target is exercised.
    for g in _GENERATORS:
        assert g(), g.__name__
    assert len(_CASES) >= 60
    kinds = {k for _, k in _CASES}
    assert kinds >= {"arity", "undefined-name", "struct-field", "exhaustiveness",
                     "dup-variant", "operand-type", "index", "return-fit", "dup-fn"}


# ── crash-class regressions: one minimal representative per malformed-input non-termination bug that
#    used to segfault or hang the front-to-back pipeline (parse → resolve → monomorphize → emit). Each
#    must now exit CLEANLY (a non-negative code — an error count / kind, never a signal) through every
#    binary. These are the permanent gate for the hardening; see _fuzz_campaign.py for the fuzz sweep
#    that originally surfaced them. ──
_CRASH_CLASSES = [
    ("cyclic-global",        "g := g"),                                       # self-referential global init
    ("mutual-globals",       "a := b\nb := a"),                               # mutually-referential globals
    ("byvalue-type-cycle",   "A*: { b: B } B*: { a: A }"),                    # struct A↔B by value
    ("unterminated-block",   "f = () i32 {"),                                 # block never closed
    ("unterminated-match",   "f = () i32 { 0 .match ({ 1 => 2"),             # match arms never closed
    ("unterminated-impl",    "T*: { x: i32 } T.impl(Tr, { m = () void {"),   # impl body never closed
    ("unterminated-bracket", "f = () i32 { x := 5  x[0 "),                    # `[` never closed (skip_brackets)
    ("idxset-unterminated",  "f = () i32 { s := [1,2]  s[0 = 3 }"),          # idxset `[` scan past EOF
    ("malformed-tyargs",     "Foo<"),                                         # `<` with no closing `>`
    ("recursive-generic-fn", "f<T> = (x: T) T { f(x) }"),                     # self-recursive generic → inliner
    ("mutual-generic-fn",    "a<T> = (x: T) T { b(x) }  b<T> = (x: T) T { a(x) }  test* = () i32 { a(1) }"),
    ("polyrec-type",         "Box<T>: { next: Box<Box<T>> }  use* = (b: Box<i32>) i32 { 0 }"),
    ("polyrec-type-field",   "P<T>: { a: T, n: P<P<T>> }  use* = (b: P<i32>) i32 { 0 }"),  # by-value cycle in mono'd structs
]


@pytest.mark.parametrize("name,src", _CRASH_CLASSES, ids=[c[0] for c in _CRASH_CLASSES])
def test_fuzz_malformed_no_crash(name, src):
    # Every malformed-input crash class must exit CLEANLY (no signal, no hang) through all three
    # binaries. A negative return code is a signal (segfault); a TimeoutExpired (raised by the helpers'
    # 30s timeout) is a hang — both are robustness failures and fail the test.
    assert check_count(src) >= 0, (name, "CHECK signalled")
    assert check_kind(src) >= 0, (name, "CHECK-KIND signalled")
    assert emit_rc(src) >= 0, (name, "EMIT signalled")


def test_fuzz_random_garbage_terminates():
    # A coarser robustness sweep: feed RANDOM token soup and assert the front-to-back pipeline always
    # exits CLEANLY — no hang (the 30s timeout in the helpers would raise) AND no crash (a negative rc
    # is a signal). The parse→resolve→monomorphize→emit path is hardened against malformed input
    # (see _fuzz_campaign.py + the crash-class regressions above), so arbitrary token soup must never
    # segfault any of the CHECK / CHECK-KIND / EMIT binaries; clean exits are sane non-negative codes.
    rng = random.Random(20260607)
    toks = ["test*", "=", "(", ")", "i32", "{", "}", "x", ":=", "5", ".match", "[", "]",
            "+", "P", "{", "x:", "0", "}", "f", "1", "<", "2", "return", "_", "=>", ",",
            "T", "<T>", ":", "|", ".Some", "impl", "use*", "Box", "n:"]
    for _ in range(120):
        n = rng.randint(1, 16)
        src = " ".join(rng.choice(toks) for _ in range(n))
        cnt = check_count(src)     # raises on timeout/hang — that IS the assertion for "terminates"
        kd = check_kind(src)
        er = emit_rc(src)
        # no binary may crash (negative == signal) on any soup; clean exits are sane non-negative codes.
        assert cnt >= 0, (src, "CHECK signalled", cnt)
        assert kd >= 0, (src, "CHECK-KIND signalled", kd)
        assert er >= 0, (src, "EMIT signalled", er)
        assert cnt < 1000 and kd <= 14, (src, cnt, kd)   # 14 = parse (syntax-error sentinel)
