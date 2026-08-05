#!/bin/sh
# The strongest oracle in the project, and it costs this file.
#
#   bootstrap  src/  -> stage1.c -> cc -> zen-1
#   zen-1      src/  -> stage2.c -> cc -> zen-2
#   zen-2      src/  -> stage3.c
#   assert stage2.c == stage3.c
#
# A compiler that reproduces its own output byte for byte is almost
# certainly correct across an enormous surface. Requires gen_c to be
# deterministic; run `make determinism` first if this ever surprises you.
set -eu
ROOT=${ROOT:-src}
OUT=${OUT:-.fixpoint}
CC=${CC:-cc}
CFLAGS=${CFLAGS:--O2 -std=c99}

rm -rf "$OUT" && mkdir -p "$OUT"

python3 bootstrap/bootstrap.py "$ROOT" --emit-c -o "$OUT/stage1.c"
$CC $CFLAGS "$OUT/stage1.c" -o "$OUT/zen-1"

"$OUT/zen-1" build "$ROOT" --emit-c -o "$OUT/stage2.c"
$CC $CFLAGS "$OUT/stage2.c" -o "$OUT/zen-2"

"$OUT/zen-2" build "$ROOT" --emit-c -o "$OUT/stage3.c"

if cmp -s "$OUT/stage2.c" "$OUT/stage3.c"; then
    echo "fixpoint: OK  (stage2.c == stage3.c)"
    exit 0
fi
echo "fixpoint: FAILED — the compiler does not reproduce its own output" >&2
diff -u "$OUT/stage2.c" "$OUT/stage3.c" | head -50 >&2
exit 1
