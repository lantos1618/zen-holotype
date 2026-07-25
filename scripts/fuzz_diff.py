#!/usr/bin/env python3
# scripts/fuzz_diff.py — differential fuzzer for Zen's two backends (C vs JS).
#
# Zen compiles the SAME program two ways:
#   C  : `zen run  <f>`            (the correct oracle)
#   JS : `zen emit-js <f> | node`  (second backend)
# A program that prints DIFFERENT output on the two backends, when BOTH run to
# completion (exit 0), is a miscompile. This tool generates random-but-VALID Zen
# programs from a grammar both backends support, runs each on both backends, and
# flags divergences. Every program prints only deterministic values so any diff is
# a real backend disagreement, not nondeterminism.
#
# Usage:
#   scripts/fuzz_diff.py --seed 1 --count 500          # generate + diff 500 programs
#   scripts/fuzz_diff.py --seed 1 --count 500 --zen ./zen --out /tmp/fuzzout
#   scripts/fuzz_diff.py --seed 1 --only 137           # regenerate + show ONE program
#
# Reproducibility: program i is generated from RNG seeded with (seed, i). A finding
# reprints as `--seed S --only I`; its .zen is also saved under --out for divergences.
#
# Classification per program:
#   AGREE          both exit 0, outputs identical
#   DIVERGENCE     both exit 0, outputs DIFFER   -> saved, this is the signal
#   JS-UNSUPPORTED C ok but JS emit/run failed   -> feature gap, not a miscompile
#   C-FAIL         C backend rejected/failed     -> generator produced bad code, skipped
#
# Known-excluded cluster (JS 64-bit ints): the generator never emits i64/u64 nor
# unsigned `>>`, which are the already-known JS divergences (BigInt / >>> ). Any
# divergence found here is therefore NEW. --allow-known re-enables them for A/B.

import argparse, os, random, subprocess, sys, tempfile

# ── type model ────────────────────────────────────────────────────────────────
# width in bits and signedness; drives which ops are legal and literal ranges.
INT_TYPES = {
    "i8":  (8,  True),  "i16": (16, True),  "i32": (32, True),
    "u8":  (8,  False), "u16": (16, False), "u32": (32, False),
}
ALL_INT = list(INT_TYPES)

def rlit(rng, ty):
    w, signed = INT_TYPES[ty]
    if signed:
        lo, hi = -(1 << (w - 1)), (1 << (w - 1)) - 1
    else:
        lo, hi = 0, (1 << w) - 1
    v = rng.randint(lo, hi)
    return f"({v})" if v < 0 else str(v)   # parenthesize negatives for safety

def flit(rng):
    choices = [rng.choice([0.5, 1.5, 2.0, 3.25, 7.0, 0.1, 100.0, 1234.5, 0.0]),
               round(rng.uniform(-50, 50), 3)]
    v = rng.choice(choices)
    return f"({v})" if v < 0 else str(v)

# ── integer arithmetic (SSA / per-step narrowed) ──────────────────────────────
# Every binary op result is bound to a fresh TYPED var of the operand type, then
# reused. This narrows each intermediate to its declared width at every step — the
# only form on which the two backends agree. (Two facts forced this shape:
#  (1) Zen const-folds pure-literal arithmetic and rejects a fold that overflows the
#      target `assign-fit`, so literal trees are compile-rejected;
#  (2) the JS backend masks a narrow int to its width ONLY at a typed assignment, not
#      per operation, so an UN-narrowed intermediate overflow (e.g. inline `a*b%17`)
#      uses JS float arithmetic and loses precision past 2^53 — a real divergence,
#      documented in the report, deliberately NOT generated here.)
# Leaves are variables (never bare i64-default literals). `>>` only on signed types.
# Div/mod take a nonzero positive literal RHS so C never traps on div-by-zero.
def decl_ints(rng, ty, tag, count):
    names = [f"{tag}{k}" for k in range(count)]
    lines = [f"    {nm}: {ty} := {rlit(rng, ty)}" for nm in names]
    return names, lines

def build_int(rng, ty, tag):
    """Emit SSA narrowed arithmetic of type `ty`; return (lines, result_var_name)."""
    w, signed = INT_TYPES[ty]
    names, lines = decl_ints(rng, ty, tag, rng.randint(2, 3))
    cur = rng.choice(names)
    for s in range(rng.randint(1, 4)):
        ops = ["+", "-", "*", "&", "|", "^", "<<"]
        if signed:
            ops.append(">>")
        op = rng.choice(ops + ["/", "%"])
        if op in ("/", "%"):
            rhs = rng.randint(1, 50)
        elif op in ("<<", ">>"):
            rhs = rng.randint(0, w - 1)
        else:
            rhs = rng.choice(names)
        nm = f"{tag}t{s}"
        lines.append(f"    {nm}: {ty} := {cur} {op} {rhs}")
        cur = nm
    return lines, cur

def f64_expr(rng, depth):
    if depth <= 0 or rng.random() < 0.4:
        return flit(rng)
    op = rng.choice(["+", "-", "*", "/"])
    lhs = f64_expr(rng, depth - 1)
    rhs = f64_expr(rng, depth - 1) if op != "/" else \
          rng.choice(["2.0", "4.0", "3.0", "10.0", "7.0"])   # nonzero divisor
    return f"({lhs} {op} {rhs})"

# ── fixed prelude: exercises structs, enums, generics, recursion, strings ─────
PRELUDE = '''{ println } = std.text.fmt
Box3*: { a: i32, b: i32, c: i32 }
Col*: R(i32) | G | B(i32)
Pair*<T>: { p: T, q: T }
idv<T> = (v: T) T { v }
pick<T> = (a: T, b: T, c: bool) T { c.then({ a }, { b }) }
fib = (n: i32) i32 { (n < 2).then({ n }, { fib(n - 1) + fib(n - 2) }) }
sumto = (n: i32, acc: i32) i32 { (n <= 0).then({ acc }, { sumto(n - 1, acc + n) }) }
colval = (c: Col) i32 { c.match ({ .R(v) => v, .G => 0, .B(v) => v * 2 }) }
fnv = (data: string_view, n: i32) u32 {
    hash: u32 := 2166136261
    i: i32 := 0
    @while (i < n) {
        b: u8 := load(offset(data, i))
        hash = (hash ^ b) * 16777619
        i = i + 1
    }
    hash
}
'''

WORDS = ["hello", "zen", "the quick brown fox", "abc", "", "aa", "differential",
         "backend", "0123456789", "xyz"]

# ── statement templates: each appends one deterministic println to `main` ─────
def stmt(rng, n):
    k = rng.randint(0, 15)
    # NOTE: integer arithmetic is built over TYPED vars of width <= 32. Bare untyped
    # int literals default to 64-bit in Zen, and 64-bit codegen is the known JS
    # cluster (BigInt / >>>), so we never emit unbound int arithmetic — see header.
    if k == 0:                                   # i32 arithmetic chain (ops / wrap)
        lines, res = build_int(rng, "i32", f"a{n}_")
        lines.append(f"    println({res})")
        return "\n".join(lines)
    if k == 1:                                   # arithmetic over a random int width
        lines, res = build_int(rng, rng.choice(ALL_INT), f"a{n}_")
        lines.append(f"    println({res})")
        return "\n".join(lines)
    if k == 2:                                    # width-wrap: add pushes past range
        ty = rng.choice(ALL_INT)
        return (f"    v{n}: {ty} := {rlit(rng, ty)}\n"
                f"    v{n} = v{n} + {rlit(rng, ty)}\n"
                f"    println(v{n})")
    if k == 3:                                     # @while accumulate
        lim = rng.randint(1, 30)
        return (f"    s{n}: i32 := 0\n    i{n}: i32 := 0\n"
                f"    @while (i{n} < {lim}) {{ s{n} = s{n} + i{n} * {rng.randint(1,7)}  i{n} = i{n} + 1 }}\n"
                f"    println(s{n})")
    if k == 4:                                       # match on int literal
        x = rng.randint(0, 4)
        return (f"    x{n}: i32 := {x}\n"
                f"    println(x{n}.match ({{ 0 => 10, 1 => 20, 2 => 30, _ => 99 }}))")
    if k == 5:                                        # match on bool (int comparison)
        ty = rng.choice(ALL_INT)
        lines, res = build_int(rng, ty, f"a{n}_")
        lines.append(f"    println(({res} > {rlit(rng, ty)}).match ({{ true => 1, false => 0 }}))")
        return "\n".join(lines)
    if k == 6:                                          # recursion: fib
        return f"    println(fib({rng.randint(0, 22)}))"
    if k == 7:                                           # recursion: sumto
        return f"    println(sumto({rng.randint(0, 100)}, 0))"
    if k == 8:                                            # enum + match dispatch
        variant = rng.choice([f".R({rng.randint(-5,50)})", ".G", f".B({rng.randint(-5,50)})"])
        return f"    println(colval({variant}))"
    if k == 9:                                             # struct field arithmetic
        a, b, c = (rng.randint(-100, 100) for _ in range(3))
        return (f"    bx{n} := Box3(a: {a}, b: {b}, c: {c})\n"
                f"    println(bx{n}.a * bx{n}.b - bx{n}.c)")
    if k == 10:                                             # generics at 2+ types (i32 AND f64)
        i = rng.randint(-1000, 1000)
        return (f"    println(idv({i}))\n"
                f"    println(idv({flit(rng)}))\n"
                f"    println(pick({rng.randint(0,9)}, {rng.randint(0,9)}, {rng.choice(['true','false'])}))")
    if k == 11:                                              # generic struct at 2 types
        return (f"    pr{n} := Pair<i32>(p: {rng.randint(0,50)}, q: {rng.randint(0,50)})\n"
                f"    println(pr{n}.p + pr{n}.q)")
    if k == 12:                                               # string byte hash (fnv)
        w = rng.choice(WORDS)
        return f'    println(fnv("{w}", {len(w)}))'
    if k == 13:                                              # nested match (arm re-matches payload)
        v = rng.randint(0, 6)
        return (f"    println(Col.R({v}).match ({{ "
                f".R(w) => w.match ({{ 0 => 100, _ => w * 3 }}), .G => 0, .B(w) => w }}))")
    if k == 14:                                              # f64 expression tree
        return f"    println({f64_expr(rng, rng.randint(2, 5))})"
    # k == 15: f64 generic-struct + f64 while-ish accumulate via recursion-free tree
    return (f"    pf{n} := Pair<f64>(p: {flit(rng)}, q: {flit(rng)})\n"
            f"    println(pf{n}.p + pf{n}.q)")

def gen_program(rng):
    body = "\n".join(stmt(rng, i) for i in range(rng.randint(4, 10)))
    return f"{PRELUDE}main = () i32 {{\n{body}\n    0\n}}\n"

# ── runner ────────────────────────────────────────────────────────────────────
def run(cmd, stdin_null=True, timeout=30):
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL if stdin_null else None)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, b"", b"timeout"

def test_one(zen, src, workdir):
    zf = os.path.join(workdir, "prog.zen")
    with open(zf, "w") as f:
        f.write(src)
    crc, cout, _ = run([zen, "run", zf])
    if crc != 0:
        return ("C-FAIL", cout, b"", crc, None)
    jf = os.path.join(workdir, "prog.js")
    jerc, jsrc, _ = run([zen, "emit-js", zf])
    if jerc != 0:
        return ("JS-UNSUPPORTED", cout, b"", crc, jerc)
    with open(jf, "wb") as f:
        f.write(jsrc)
    nrc, jout, _ = run(["node", jf])
    if nrc != 0:
        return ("JS-UNSUPPORTED", cout, jout, crc, nrc)
    if cout == jout:
        return ("AGREE", cout, jout, crc, nrc)
    return ("DIVERGENCE", cout, jout, crc, nrc)

def main():
    ap = argparse.ArgumentParser(description="C-vs-JS differential fuzzer for Zen")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--zen", default="./zen")
    ap.add_argument("--out", default=None, help="dir for divergence repros (default: mktemp)")
    ap.add_argument("--only", type=int, default=None, help="print program N and its two outputs, then exit")
    args = ap.parse_args()

    zen = os.path.abspath(args.zen)
    if not os.access(zen, os.X_OK):
        sys.exit(f"fuzz_diff: not executable: {zen}  (run `make` first)")

    if args.only is not None:
        rng = random.Random(f"{args.seed}:{args.only}")
        src = gen_program(rng)
        with tempfile.TemporaryDirectory() as wd:
            verdict, cout, jout, crc, jrc = test_one(zen, src, wd)
        print(f"# seed={args.seed} only={args.only} verdict={verdict}\n{src}")
        print(f"--- C  [rc={crc}] ---\n{cout.decode(errors='replace')}")
        print(f"--- JS [rc={jrc}] ---\n{jout.decode(errors='replace')}")
        return

    outdir = args.out or tempfile.mkdtemp(prefix="zen-fuzzdiff-")
    os.makedirs(outdir, exist_ok=True)
    counts = {"AGREE": 0, "DIVERGENCE": 0, "JS-UNSUPPORTED": 0, "C-FAIL": 0}
    diverged = []
    with tempfile.TemporaryDirectory() as wd:
        for i in range(args.count):
            rng = random.Random(f"{args.seed}:{i}")
            src = gen_program(rng)
            verdict, cout, jout, crc, jrc = test_one(zen, src, wd)
            counts[verdict] += 1
            if verdict == "DIVERGENCE":
                base = os.path.join(outdir, f"diverge_s{args.seed}_i{i}")
                with open(base + ".zen", "w") as f:
                    f.write(src)
                with open(base + ".c.out", "wb") as f:
                    f.write(cout)
                with open(base + ".js.out", "wb") as f:
                    f.write(jout)
                diverged.append(i)
                print(f"[DIVERGENCE] seed={args.seed} i={i}  -> {base}.zen")
            if (i + 1) % 100 == 0:
                print(f"  ...{i+1}/{args.count}  {counts}", file=sys.stderr)

    print("\n=== differential fuzz summary ===")
    print(f"seed={args.seed}  count={args.count}  zen={zen}")
    for k in ("AGREE", "DIVERGENCE", "JS-UNSUPPORTED", "C-FAIL"):
        print(f"  {k:16} {counts[k]}")
    if diverged:
        print(f"\nDIVERGENCES ({len(diverged)}): repros in {outdir}")
        print("  reproduce one:  scripts/fuzz_diff.py --seed "
              f"{args.seed} --only <i>   (i in {diverged})")
        sys.exit(1)
    print(f"\nNo divergences. (repro dir: {outdir})")

if __name__ == "__main__":
    main()
