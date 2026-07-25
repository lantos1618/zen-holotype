#!/usr/bin/env bash
# ASan-instrumented allocator stress run (Angle 2).
#
# `zen build` hard-codes host `cc` for native targets (ZENC_TARGET_CC is cross-only), so it cannot add
# sanitizer flags. Instead we `zen emit` the C, replicate the driver's HEAD -> zenrt.h swap, and compile
# it ourselves with AddressSanitizer + UndefinedBehaviorSanitizer + LeakSanitizer against zenrt.c. Then
# run alloc-stress.zen, whose seeds each drive valid acquire/resize/release + rc/arc clone/drop
# sequences — so any sanitizer hit is a real allocator bug (UAF / double-free / overflow / leak).
#
#   scripts/alloc-fuzz/run-stress.sh                 # build + run the stress harness under ASan
#   SRC=path/to/other.zen scripts/alloc-fuzz/run-stress.sh   # ASan-run any Zen program
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ZEN="$ROOT/zen"
SRC="${SRC:-$ROOT/scripts/alloc-fuzz/alloc-stress.zen}"
OUT="$ROOT/fuzz-out/stress"; mkdir -p "$OUT"
CC="${CC:-cc}"
BIN="$OUT/$(basename "${SRC%.zen}").asan"

# 1. emit C, 2. swap the emitted HEAD typedef line for the zenrt.h include (see driver.zen write_runnable_c).
HEAD='typedef struct { void* ptr; int64_t len; } zslice; '
HLEN=$(printf '%s' "$HEAD" | wc -c)
"$ZEN" emit "$SRC" > "$OUT/emit.c"
{ printf '#define ZEN_NO_STRING 1\n#define ZEN_NO_MALLOC 1\n#include "zenrt.h"\n'
  tail -c "+$((HLEN + 1))" "$OUT/emit.c"; } > "$OUT/stress.c"

# 3. compile instrumented.
$CC -std=gnu11 -O1 -g -fno-omit-frame-pointer -fno-strict-aliasing -fwrapv -w \
    -fsanitize=address,undefined -fno-sanitize-recover=all \
    -I"$ROOT/bootstrap" "$OUT/stress.c" "$ROOT/bootstrap/zenrt.c" -lm -o "$BIN"

# 4. run. LeakSanitizer ON (the harness frees everything), UBSan fatal.
echo "running $BIN under ASan+UBSan+LSan ..."
ASAN_OPTIONS="detect_leaks=1:abort_on_error=1:halt_on_error=1:detect_stack_use_after_return=1" \
UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1" \
  "$BIN"
echo "stress: clean (exit $?)"
