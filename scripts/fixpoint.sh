#!/bin/sh
# The strongest oracle in the project, and it costs this file.
#
#   cc         seed/zen.c   -> zen-0
#   zen-0      src/  -> stage1/  -> cc -j -> zen-1
#   zen-1      src/  -> stage2/  -> cc -j -> zen-2
#   zen-2      src/  -> stage3/
#   assert stage2/ == stage3/, file for file
#   assert stage2.c == stage3.c
#
# A compiler that reproduces its own output byte for byte is almost
# certainly correct across an enormous surface. Requires gen_c to be
# deterministic; run `make determinism` first if this ever surprises you.
#
# STAGE 0 USED TO BE THE PYTHON BOOTSTRAPPER, and is now the committed seed.
# That trades one property away: the chain no longer starts from a second
# implementation, so a bug the seed and src share is invisible here. It also
# buys one back -- the bootstrapper's zen-1 miscompiled src's own range check
# and healed at stage 2, so stage 1 was never a compiler you could trust.
# What still holds is the assertion below, which is about src alone.
#
# TWO EMISSIONS PER STAGE, AND BOTH ARE ASSERTED. The backend writes one
# translation unit with `--emit-c -o` and one file per module with
# `--emit-c-dir`, and `make build` compiles the second -- so a per-file
# comparison is what the chain actually stands on now, and asserting only
# the single file would leave the shipping path unchecked. The single file
# stays asserted too, because seed/zen.c IS one and `make seed` writes it.
# The stage binaries are built from the SPLIT, so every stage of this chain
# is also a test that the split links into a working compiler.
#
# seed/zen.c == stage1.c additionally means the committed seed is current --
# what zen-0 emits for today's src IS what is checked in. This IS asserted,
# and last: a stale seed is not a compiler bug -- stage2 == stage3 below has
# already said the compiler is a fixed point -- but it is a lie the repo tells
# about itself, and a122b99f shipped one to main under an OK banner. It exits
# 1 and `make seed` repairs it. NOT stage1 vs stage2: those are two compilers
# reading the same src, so they agree whenever zen-0 is a fixed point, whatever
# src does.
set -eu
ROOT=${ROOT:-src}
OUT=${OUT:-.fixpoint}
CC=${CC:-cc}
CFLAGS=${CFLAGS:--O2 -std=c99}
J=${J:-$(nproc 2>/dev/null || echo 4)}
# A `-c` compile is the only kind a cache can serve; see the Makefile.
CACHE=${CACHE:-$(command -v ccache 2>/dev/null || true)}

if [ ! -f seed/zen.c ]; then
    echo "fixpoint: seed/zen.c is missing, so there is nothing to start from." >&2
    echo "  This is a setup error, not a verdict about the compiler." >&2
    exit 2
fi

rm -rf "$OUT" && mkdir -p "$OUT"

# link <dir> <binary> -- every unit in <dir>, compiled in parallel, linked.
link() {
    ls "$1"/*.c | xargs -P "$J" -I{} $CACHE $CC $CFLAGS -c {} -o {}.o
    $CC "$1"/*.o -o "$2"
}

$CACHE $CC $CFLAGS -c seed/zen.c -o "$OUT/zen-0.o"
$CC "$OUT/zen-0.o" -o "$OUT/zen-0"

mkdir -p "$OUT/stage1"
"$OUT/zen-0" build "$ROOT" --emit-c -o "$OUT/stage1.c"
"$OUT/zen-0" build "$ROOT" --emit-c-dir "$OUT/stage1"
link "$OUT/stage1" "$OUT/zen-1"

mkdir -p "$OUT/stage2"
"$OUT/zen-1" build "$ROOT" --emit-c -o "$OUT/stage2.c"
"$OUT/zen-1" build "$ROOT" --emit-c-dir "$OUT/stage2"
link "$OUT/stage2" "$OUT/zen-2"

mkdir -p "$OUT/stage3"
"$OUT/zen-2" build "$ROOT" --emit-c -o "$OUT/stage3.c"
"$OUT/zen-2" build "$ROOT" --emit-c-dir "$OUT/stage3"

if ! cmp -s "$OUT/stage2.c" "$OUT/stage3.c"; then
    echo "fixpoint: FAILED — the compiler does not reproduce its own output" >&2
    diff -u "$OUT/stage2.c" "$OUT/stage3.c" | head -50 >&2
    exit 1
fi

# A COMPARISON THAT CANNOT BE VACUOUS. `diff -r` over two empty directories
# is silent, and `--emit-c-dir` writing nothing at all would pass it -- so
# the count is asserted first, against the number of modules the single
# file's own emission proves are there.
units=$(ls "$OUT/stage3"/*.c 2>/dev/null | wc -l | tr -d ' ')
if [ "$units" -lt 2 ]; then
    echo "fixpoint: --emit-c-dir produced $units unit(s); nothing to compare." >&2
    echo "  This is a setup error, not a verdict about the compiler." >&2
    exit 2
fi

# `-x '*.o'` because `link` above put its object files inside stage2/.
if ! diff -r -x '*.o' "$OUT/stage2" "$OUT/stage3" >"$OUT/split.diff" 2>&1; then
    echo "fixpoint: FAILED — the split does not reproduce itself" >&2
    head -50 "$OUT/split.diff" >&2
    exit 1
fi

if cmp -s seed/zen.c "$OUT/stage1.c"; then
    echo "fixpoint: OK  (stage2 == stage3 over $units units and one file; seed is current)"
else
    echo "fixpoint: FAILED — seed/zen.c is stale: what zen-0 emits is not what is checked in" >&2
    echo "  The compiler itself is fine (stage2 == stage3 over $units units and one file)." >&2
    echo "  Regenerate with \`make seed\`, then commit seed/zen.c." >&2
    exit 1
fi
