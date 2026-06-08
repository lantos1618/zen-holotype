"""Heavy crash-hunt over the FIXED binaries: find any malformed input that still signals/hangs.

Drives EMIT + CHECK + CHECK-KIND (the committed-style binaries the oracle builds) with three input
families: (1) random token soup over a grammar-flavored alphabet, (2) targeted deep-recursion
generators for the just-fixed crash classes (type cycles of length 2..5, N-deep unterminated blocks,
self-referential globals through expressions, malformed `<…>` tails), (3) random byte noise. A crash
is a negative returncode (signal) or a TimeoutExpired (hang). Prints every minimal crashing input.

Run:  python3 tests/_fuzz_campaign.py <seed> <iters>
"""
import random
import subprocess
import sys

import _oracle

EMIT = str(_oracle._build_emit())
CHECK = str(_oracle._build_check())
KIND = str(_oracle._build_check_kind())
PRELUDE = _oracle._PRELUDE

ALPHA = ["test*", "f*", "=", "(", ")", "i32", "i64", "bool", "str", "{", "}", "x", "y", "p",
         ":=", ":", "5", "0", "1", ".match", "[", "]", "+", "-", "*", "/", "P", "C", "T",
         "x:", "0", "}", "f", "1", "<", ">", "2", "return", "_", "=>", ",", ".", ".Some",
         ".None", "|", "impl", "Drop", "loop", "addr", "slice", "void", "Ptr", "MutPtr",
         "&&", "||", "==", "!=", "g", "h", ".Ok", ".Err", "@while", "sizeof"]


def crashed(exe, src, with_prelude=False):
    """Return (tag, returncode) — tag in {'ok','CRASH','HANG'}. CRASH = signal (rc<0)."""
    inp = (PRELUDE + src) if with_prelude else src
    try:
        rc = subprocess.run([exe], input=inp, capture_output=True, text=True, timeout=20).returncode
    except subprocess.TimeoutExpired:
        return ("HANG", None)
    return ("CRASH", rc) if rc < 0 else ("ok", rc)


def soup(rng):
    n = rng.randint(1, 30)
    return " ".join(rng.choice(ALPHA) for _ in range(n))


def byte_noise(rng):
    n = rng.randint(1, 60)
    return "".join(chr(rng.randint(32, 126)) for _ in range(n))


def targeted(rng):
    """Grammar-aware malformed programs aimed at the fixed (and nearby) recursion sites."""
    pick = rng.randint(0, 11)
    if pick == 0:                                   # N-length by-value type cycle (struct)
        n = rng.randint(2, 6)
        nm = ["A%d" % i for i in range(n)]
        return "".join("%s*: { f: %s }\n" % (nm[i], nm[(i + 1) % n]) for i in range(n))
    if pick == 1:                                   # by-value cycle through enum payloads
        n = rng.randint(2, 5)
        nm = ["E%d" % i for i in range(n)]
        return "".join("%s*: V%d: %s\n" % (nm[i], i, nm[(i + 1) % n]) for i in range(n))
    if pick == 2:                                   # self-referential global through an expression
        depth = rng.randint(1, 4)
        rhs = "g" + " + g" * depth
        return "g := %s\ntest* = () i32 { 0 }" % rhs
    if pick == 3:                                   # mutually-referential globals
        return "a := b\nb := a\ntest* = () i32 { 0 }"
    if pick == 4:                                   # N-deep unterminated blocks
        n = rng.randint(1, 8)
        return "test* = () i32 { " * 1 + "{ " * n
    if pick == 5:                                   # N-deep unterminated match arms
        n = rng.randint(1, 6)
        return "test* = () i32 { 0 .match ({ " + ".V => ".join("0" for _ in range(n))
    if pick == 6:                                   # unterminated impl body, varying nesting
        n = rng.randint(0, 4)
        return "T*: { x: i32 }\nT.impl(Tr, { m = () void { " + "{ " * n
    if pick == 7:                                   # malformed `<…>` tails on a decl name
        return rng.choice(["Foo<", "Bar<T", "Baz<<<", "Q<,>", "W< = ()", "Z<T,,>: {"])
    if pick == 8:                                   # truncations of a real program (off-by-token)
        full = "P*: { x: i32 }\nf* = (p: P) i32 { p.x .match ({ 0 => 1, _ => 2 }) }\ntest* = () i32 { f(P(x: 5)) }"
        return full[: rng.randint(1, len(full))]
    if pick == 9:                                   # deep nested parens / brackets unterminated
        n = rng.randint(1, 20)
        return "test* = () i32 { " + rng.choice(["(", "[", ".match (("]) * n
    if pick == 10:                                  # self / mutually-recursive generic FUNCTIONS (inliner)
        forms = [
            "f<T> = (x: T) T { f(x) }",
            "f<T> = (x: T) T { f(x) }  test* = () i32 { f(1) }",
            "a<T> = (x: T) T { b(x) }  b<T> = (x: T) T { a(x) }  test* = () i32 { a(1) }",
            "f<T> = (x: T) T { g(f(x)) }  g<T> = (x: T) T { f(x) }  test* = () i32 { f(1) }",
        ]
        return rng.choice(forms)
    # pick == 11: polymorphic-recursive generic TYPES (monomorphizer) — ever-deeper instances
    forms = [
        "Box<T>: { next: Box<Box<T>> }  use* = (b: Box<i32>) i32 { 0 }",
        "L<T>: V: L<L<T>>  use* = (b: L<i32>) i32 { 0 }",
        "P<T>: { a: T, n: P<P<T>> }  test* = () i32 { 0 }  use* = (b: P<i32>) i32 { 0 }",
    ]
    return rng.choice(forms)


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    iters = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
    rng = random.Random(seed)
    gens = [lambda: soup(rng), lambda: byte_noise(rng), lambda: targeted(rng)]
    found = []
    for i in range(iters):
        src = rng.choice(gens)()
        for exe, wp, name in ((EMIT, False, "EMIT"), (CHECK, True, "CHECK"), (KIND, True, "KIND")):
            tag, rc = crashed(exe, src, wp)
            if tag != "ok":
                found.append((name, tag, rc, src))
                print("!! %s %s rc=%s :: %r" % (name, tag, rc, src), flush=True)
    print("seed=%d iters=%d crashes=%d" % (seed, iters, len(found)))
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
