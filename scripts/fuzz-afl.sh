#!/usr/bin/env bash
# Coverage-guided crash fuzzer for the Zen compiler using AFL++ with ASan instrumentation.
# Preferred over the blind mutation loop (fuzz-run.sh) when afl-fuzz is installed: AFL evolves inputs
# toward new code paths, finding deeper bugs per CPU-second.
#
#   ./scripts/fuzz-afl.sh [SECONDS]        # default 900s (15 min); needs afl-fuzz on PATH
#
# Builds an AFL-instrumented + ASan binary (zen-afl), seeds from the fixture corpus, and runs a
# time-boxed campaign. The compiler reads the fuzz input as a file arg (@@). Crashes land in
# ./fuzz-out/afl/default/crashes/. Install AFL with: sudo apt-get install -y afl++
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
command -v afl-fuzz >/dev/null || { echo "afl-fuzz not on PATH; run: sudo apt-get install -y afl++"; exit 1; }
SECS="${1:-900}"
AFLBIN="$ROOT/zen-afl"; OUT="$ROOT/fuzz-out/afl"; IN="$ROOT/fuzz-out/afl-seeds"

# AFL's compiler wrapper instruments for coverage; AFL_USE_ASAN layers AddressSanitizer on top.
AFL_USE_ASAN=1 afl-cc -O1 -g -fno-strict-aliasing -fwrapv \
  -Wno-error=implicit-function-declaration -Wno-builtin-declaration-mismatch \
  "$ROOT/bootstrap/zenc.gen.c" "$ROOT/bootstrap/zenrt.c" -o "$AFLBIN"

mkdir -p "$IN"
# Small, distinct seeds keep AFL's queue lean; take a spread of the fixtures.
i=0; for f in $(find "$ROOT/tests/fixtures/zen" -name '*.zen' | sort | awk 'NR%4==1'); do
  cp "$f" "$IN/seed_$i.zen"; i=$((i+1)); done
# Zero seeds means the fixture path moved; afl-fuzz would abort and the `|| true` below would hide it.
[ "$i" -gt 0 ] || { echo "fuzz-afl: FAIL — no seeds found under tests/fixtures/zen"; exit 2; }
rm -rf "$OUT"; mkdir -p "$OUT"

export ASAN_OPTIONS="detect_leaks=0:abort_on_error=1:symbolize=0"
export AFL_SKIP_CPUFREQ=1 AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1 AFL_BENCH_UNTIL_CRASH=0
echo "AFL campaign: ${SECS}s -> $OUT"
timeout "$SECS" afl-fuzz -i "$IN" -o "$OUT" -m none -t 5000 -- "$AFLBIN" check @@ || true
# The old last line was `ls … | grep -v README || echo "(none)"`: grep's no-match exit 1 was converted
# to 0 by the `||`, and a successful grep is 0 too — both branches exited 0, so the campaign could
# never report that it had found crashes. Count them and make that the status.
echo "=== crashes ==="
ncrash=$(ls -1 "$OUT/default/crashes" 2>/dev/null | grep -cv README || true)
if [ "${ncrash:-0}" -gt 0 ]; then
  ls -1 "$OUT/default/crashes" | grep -v README
  echo "FAIL: $ncrash AFL crash input(s) in $OUT/default/crashes"
  exit 1
fi
echo "(none)"
