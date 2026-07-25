#!/usr/bin/env bash
# Build the ASan+UBSan-instrumented Zen compiler used by the crash fuzzer.
#
# Mirrors bootstrap/Makefile's cc invocation (same sources, -fwrapv, aliasing flags) but adds
# AddressSanitizer + UndefinedBehaviorSanitizer at -O1 -g so silent out-of-bounds / use-after-free
# / integer-UB surface as hard errors instead of being tolerated by the normal -O2 build.
#
#   ./scripts/fuzz-build.sh            # writes ./zen-asan
#   CC=clang ./scripts/fuzz-build.sh  # pick a compiler
#
# The compiler is a bump/arena allocator that never frees before exit, so LeakSanitizer would drown
# real bugs in expected "leaks" — callers run it with ASAN_OPTIONS=detect_leaks=0 (see fuzz-run.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CC="${CC:-cc}"
OUT="${1:-$ROOT/zen-asan}"

exec $CC -std=gnu11 -O1 -g -fno-strict-aliasing -fno-omit-frame-pointer \
  -fsanitize=address,undefined -fno-sanitize-recover=all \
  -Wno-error=implicit-function-declaration -fwrapv -Wno-builtin-declaration-mismatch \
  "$ROOT/bootstrap/zenc.gen.c" "$ROOT/bootstrap/zenrt.c" -o "$OUT"
