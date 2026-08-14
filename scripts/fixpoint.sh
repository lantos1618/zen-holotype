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

# THE BOOTSTRAPPER CANNOT PARSE WITHOUT THE GRAMMAR, and `grammar/zen.so` is
# generated and untracked -- so a fresh checkout, or any worktree, has none.
# Without this check the tree-sitter failure falls into the branch below and
# is reported as "stage 1 is not finished", which sends a reader to look for
# missing compiler phases that are all present. A setup error must not be
# able to impersonate a result. `make fixpoint` depends on `grammar` and
# never sees this; running this script directly is what does, which is how
# every agent runs it.
if [ ! -f grammar/zen.so ]; then
    echo "fixpoint: grammar/zen.so is missing, so the bootstrapper cannot parse." >&2
    echo "  It is generated and untracked. Run \`make grammar\` first." >&2
    echo "  This is a setup error, not a verdict about the compiler." >&2
    exit 2
fi

# `-m bootstrap.bootstrap`, never the script path: bootstrap/ast.py shares its
# name with the standard library's, and running the file directly makes
# `dataclasses` import the wrong one and kill the interpreter. `--root` is not
# optional either -- without it the compilation root is the inputs' common
# ancestor, which for a single argument is the argument's parent.
if ! python3 -m bootstrap.bootstrap "$ROOT" --root "$ROOT" --emit-c -o "$OUT/stage1.c"; then
    echo "fixpoint: the bootstrapper could not compile $ROOT into a compiler." >&2
    echo "  stage 1 is not finished. See docs/PLAN.md 'Stage 1 - self-host':" >&2
    echo "  src/ needs lex, parse (both under std/), sema, gen AND a src/zen.zen
#  CLI that wires" >&2
    echo "  them together, because zen-1 is invoked as \`zen-1 build <root>\`." >&2
    exit 1
fi
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
