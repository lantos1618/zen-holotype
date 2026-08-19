#!/bin/sh
# The strongest oracle in the project, and it costs this file.
#
#   cc         seed/zen.c   -> zen-0
#   zen-0      src/  -> stage1.c -> cc -> zen-1
#   zen-1      src/  -> stage2.c -> cc -> zen-2
#   zen-2      src/  -> stage3.c
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
# stage1 == stage2 additionally means the committed seed is current. It is
# reported, not asserted: regenerating the seed is `make seed`, and a stale
# seed is a chore, not a compiler bug.
set -eu
ROOT=${ROOT:-src}
OUT=${OUT:-.fixpoint}
CC=${CC:-cc}
CFLAGS=${CFLAGS:--O2 -std=c99}

if [ ! -f seed/zen.c ]; then
    echo "fixpoint: seed/zen.c is missing, so there is nothing to start from." >&2
    echo "  This is a setup error, not a verdict about the compiler." >&2
    exit 2
fi

rm -rf "$OUT" && mkdir -p "$OUT"

$CC $CFLAGS seed/zen.c -o "$OUT/zen-0"

"$OUT/zen-0" build "$ROOT" --emit-c -o "$OUT/stage1.c"
$CC $CFLAGS "$OUT/stage1.c" -o "$OUT/zen-1"

"$OUT/zen-1" build "$ROOT" --emit-c -o "$OUT/stage2.c"
$CC $CFLAGS "$OUT/stage2.c" -o "$OUT/zen-2"

"$OUT/zen-2" build "$ROOT" --emit-c -o "$OUT/stage3.c"

if ! cmp -s "$OUT/stage2.c" "$OUT/stage3.c"; then
    echo "fixpoint: FAILED — the compiler does not reproduce its own output" >&2
    diff -u "$OUT/stage2.c" "$OUT/stage3.c" | head -50 >&2
    exit 1
fi

if cmp -s "$OUT/stage1.c" "$OUT/stage2.c"; then
    echo "fixpoint: OK  (stage2.c == stage3.c; seed is current)"
else
    echo "fixpoint: OK  (stage2.c == stage3.c; seed/zen.c is stale — \`make seed\`)"
fi
